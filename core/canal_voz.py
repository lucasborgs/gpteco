"""
core/canal_voz.py

Item C — canal obrigatório de voz.

Regra (seção 8.1 da spec): a cada `CANAL_TEXTO_MAX` pedidos **atendidos** por
texto dentro de uma janela de `CANAL_JANELA_MIN` minutos, o texto fecha por
`CANAL_BLOQUEIO_MIN` minutos; qualquer pedido atendido por voz zera o ciclo.
Sem o cooldown de 6h ativo no cliente (`DISABLE_COOLDOWN=true`), este é o
único freio por ouvinte do sistema.

Só conta pedido **atendido** — o que entrou na fila do ZaraRadio. Pedido
recusado (não identificado, fora do repertório, eleitoral) não aproxima
ninguém do bloqueio: a regra empurra para a voz quem está sendo atendido, não
pune quem não está sendo entendido.

O fold é **derivado** do histórico de `dim_pedidos` a cada chamada — não há
estado em memória. O contêiner do cliente já reiniciou sozinho por OOM, e
qualquer cache por número sumiria no restart, deixando o ouvinte sem o
bloqueio que deveria estar ativo (ou, pior, reaplicando um bloqueio já
expirado se o cache ficasse desatualizado). Por isso este módulo nunca
memoiza por `numero`: cada chamada pública lê `database.pedidos_atendidos_por_canal`
de novo.

Valores de `canal` diferentes de "voz" e "texto" — `None` (linha anterior à
migração da coluna) e `""` (chamada de `registrar_pedido` que não informou o
canal) — são ignorados pelo fold, exatamente como pedidos fora da janela de
histórico: não incrementam o contador, não zeram o bloqueio, não contam como
voz.

Única consulta por pedido
--------------------------
O plano de tasks descreve duas opções para evitar duas consultas ao banco por
pedido de texto (uma para `bloqueado`, outra para `tem_historico_de_voz`):
passar a lista já buscada para as duas funções, ou expor uma função que
devolve as duas respostas de uma vez. Este módulo usa a segunda opção:

- `avaliar(numero)` busca o histórico **uma única vez** e devolve
  `(bloqueado, tem_historico_de_voz)` — é o que um chamador que precisa das
  duas respostas para o mesmo pedido (como o gate do pipeline, que só
  consulta `tem_historico_de_voz` depois de já saber que está bloqueado) deve
  usar, para gastar uma consulta por pedido em vez de duas.
- `bloqueado(numero)` e `tem_historico_de_voz(numero)` são a interface mínima
  pedida pela task C2, com a assinatura `numero: str` da seção 8.1/8.6 da
  spec; cada uma chama `avaliar` internamente e por isso faz sua própria
  consulta quando usada isoladamente (testes, scripts, ou um chamador que só
  precisa de uma das duas respostas).
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta

from core import database

# Desliga o gate inteiro sem rebuild (seção 10 da spec).
CANAL_VOZ_ATIVADO: bool = os.getenv("CANAL_VOZ_ATIVADO", "true").strip().lower() == "true"

# Pedidos atendidos por texto, dentro da janela, antes do texto fechar.
CANAL_TEXTO_MAX: int = int(os.getenv("CANAL_TEXTO_MAX", "3"))

# Duração do bloqueio de texto, em minutos, a partir do pedido que fechou o ciclo.
CANAL_BLOQUEIO_MIN: int = int(os.getenv("CANAL_BLOQUEIO_MIN", "60"))

# Janela deslizante de contagem, em minutos: pedido por texto mais antigo que
# isto não conta mais para fechar o ciclo. Sem ela o contador só zerava num
# pedido por voz, e quem pedia uma música por texto por semana topava no
# bloqueio na terceira semana — acúmulo sem relação com o que a regra quer
# coibir, que é a rajada de pedidos por texto.
CANAL_JANELA_MIN: int = int(os.getenv("CANAL_JANELA_MIN", "60"))

# Janela de consulta do histórico. NÃO é a janela da contagem (essa é
# CANAL_JANELA_MIN, aplicada pelo fold): esta precisa ser longa porque
# `tem_historico_de_voz` olha a vida inteira do ouvinte para escolher entre
# `apenas_voz` e `apenas_voz_retorno` (seção 8.7 da spec).
CANAL_HISTORICO_DIAS: int = int(os.getenv("CANAL_HISTORICO_DIAS", "90"))


def _fold(historico: list[tuple[datetime, str]]) -> tuple[bool, bool]:
    """
    Executa o fold determinístico da seção 8.1 sobre `historico` (já em ordem
    cronológica crescente, só pedidos atendidos) e devolve
    `(bloqueado, tem_historico_de_voz)`.

    Pseudocódigo da spec, com a janela deslizante de CANAL_JANELA_MIN (ver a
    constante) no lugar do contador que só zerava na voz:

        recentes = []            # timestamps dos textos que ainda contam
        bloqueio_ate = None
        for pedido in pedidos_atendidos_asc:
            if pedido.canal == "voz":
                recentes, bloqueio_ate = [], None     # voz zera tudo
            elif pedido.canal == "texto":
                descarta de `recentes` o que for anterior a
                    pedido.timestamp - CANAL_JANELA_MIN
                recentes.append(pedido.timestamp)
                if len(recentes) >= CANAL_TEXTO_MAX:
                    bloqueio_ate = pedido.timestamp + CANAL_BLOQUEIO_MIN
                    recentes = []                     # começa um novo ciclo
        bloqueado = bloqueio_ate is not None and agora < bloqueio_ate

    O corte é relativo ao timestamp de cada pedido, não a `agora`: o fold
    reconstrói se o ciclo fechou quando fechou. Bloqueio que já expirou
    continua aparecendo como expirado, e não como ciclo em aberto.
    """
    recentes: list[datetime] = []
    bloqueio_ate: datetime | None = None
    teve_voz = False
    janela = timedelta(minutes=CANAL_JANELA_MIN)

    for timestamp, canal in historico:
        if canal == "voz":
            recentes, bloqueio_ate = [], None
            teve_voz = True
        elif canal == "texto":
            corte = timestamp - janela
            recentes = [t for t in recentes if t > corte]
            recentes.append(timestamp)
            if len(recentes) >= CANAL_TEXTO_MAX:
                bloqueio_ate = timestamp + timedelta(minutes=CANAL_BLOQUEIO_MIN)
                recentes = []
        # qualquer outro valor — None, "", lixo — é ignorado pelo fold

    agora = datetime.now()
    bloqueado = bloqueio_ate is not None and agora < bloqueio_ate
    return bloqueado, teve_voz


def avaliar(numero: str) -> tuple[bool, bool]:
    """
    Única consulta ao banco para `numero`: devolve
    `(bloqueado, tem_historico_de_voz)`.

    Use esta função quando precisar das duas respostas para o mesmo pedido —
    é o jeito de gastar uma consulta por pedido em vez de duas. Com
    `CANAL_VOZ_ATIVADO=false`, devolve `(False, False)` sem consultar o banco.
    """
    if not CANAL_VOZ_ATIVADO:
        return False, False

    historico = database.pedidos_atendidos_por_canal(numero, CANAL_HISTORICO_DIAS)
    return _fold(historico)


def bloqueado(numero: str) -> bool:
    """
    True se `numero` está, agora, dentro do período de bloqueio de texto.

    Com `CANAL_VOZ_ATIVADO=false`, devolve `False` sem consultar o banco. Uso
    isolado (uma consulta própria); para obter também `tem_historico_de_voz`
    do mesmo pedido sem duplicar a consulta, use `avaliar(numero)`.
    """
    if not CANAL_VOZ_ATIVADO:
        return False
    bloq, _ = avaliar(numero)
    return bloq


def tem_historico_de_voz(numero: str) -> bool:
    """
    True se `numero` tem algum pedido atendido com `canal = "voz"` no
    histórico — define a variante de mensagem (seção 8.7): quem nunca mandou
    áudio recebe `apenas_voz`; quem já mandou recebe `apenas_voz_retorno`.

    Uso isolado (uma consulta própria); para obter também `bloqueado` do
    mesmo pedido sem duplicar a consulta, use `avaliar(numero)`.
    """
    if not CANAL_VOZ_ATIVADO:
        return False
    _, teve_voz = avaliar(numero)
    return teve_voz
