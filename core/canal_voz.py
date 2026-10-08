"""
core/canal_voz.py

Item C — canal obrigatório de voz.

Regra (seção 8.1 da spec): a cada `CANAL_TEXTO_MAX` pedidos **atendidos** por
texto, o texto fecha por `CANAL_BLOQUEIO_MIN` minutos; qualquer pedido
atendido por voz zera o ciclo. Sem o cooldown de 6h ativo no cliente
(`DISABLE_COOLDOWN=true`), este é o único freio por ouvinte do sistema.

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

# Pedidos atendidos por texto, no mesmo ciclo, antes do texto fechar.
CANAL_TEXTO_MAX: int = int(os.getenv("CANAL_TEXTO_MAX", "3"))

# Duração do bloqueio de texto, em minutos, a partir do pedido que fechou o ciclo.
CANAL_BLOQUEIO_MIN: int = int(os.getenv("CANAL_BLOQUEIO_MIN", "60"))

# Janela de consulta do histórico — só limite de consulta, não parte da regra:
# o fold é correto desde que a janela cubra o ciclo corrente do ouvinte.
CANAL_HISTORICO_DIAS: int = int(os.getenv("CANAL_HISTORICO_DIAS", "90"))


def _fold(historico: list[tuple[datetime, str]]) -> tuple[bool, bool]:
    """
    Executa o fold determinístico da seção 8.1 sobre `historico` (já em ordem
    cronológica crescente, só pedidos atendidos) e devolve
    `(bloqueado, tem_historico_de_voz)`.

    Pseudocódigo da spec, seguido ao pé da letra:

        contador = 0
        bloqueio_ate = None
        for pedido in pedidos_atendidos_asc:
            if pedido.canal == "voz":
                contador, bloqueio_ate = 0, None      # voz zera tudo
            elif pedido.canal == "texto":
                contador += 1
                if contador >= CANAL_TEXTO_MAX:
                    bloqueio_ate = pedido.timestamp + CANAL_BLOQUEIO_MIN
                    contador = 0                      # começa um novo ciclo
        bloqueado = bloqueio_ate is not None and agora < bloqueio_ate
    """
    contador = 0
    bloqueio_ate: datetime | None = None
    teve_voz = False

    for timestamp, canal in historico:
        if canal == "voz":
            contador, bloqueio_ate = 0, None
            teve_voz = True
        elif canal == "texto":
            contador += 1
            if contador >= CANAL_TEXTO_MAX:
                bloqueio_ate = timestamp + timedelta(minutes=CANAL_BLOQUEIO_MIN)
                contador = 0
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
