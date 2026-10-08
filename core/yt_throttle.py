"""
core/yt_throttle.py

Throttle das chamadas ao YouTube feitas por core/downloader.py (Etapa 4 do
pipeline). Existe porque bloqueio por volume no YouTube é a falha mais cara do
sistema — derruba 100% dos pedidos novos (foi o incidente de HTTP 403 que
levou ao ajuste de YT_PLAYER_CLIENT + PO Token).

Mecânica (seção 7.3 da spec):

  - Um único `threading.Lock` de módulo serializa as extrações: uma por vez
    no processo inteiro. Seguro porque o contêiner roda `uvicorn --workers 1`
    e o pipeline executa cada pedido numa thread do pool via
    `asyncio.to_thread`. Serializar também reduz pico de RAM, o que importa
    na VM de ~2 GB do cliente.
  - O intervalo mínimo é medido a partir do FIM da chamada anterior (mais
    conservador que medir do início) e vale entre tipos: uma tentativa de
    download conta como "chamada anterior" para a próxima busca.
  - Jitter aditivo (nunca subtrai) de 0 a `YT_THROTTLE_JITTER_PCT` do
    intervalo, sorteado a cada chamada — um intervalo exato é, por si só, um
    sinal de automação.
  - `Orcamento` (um por pedido, acumulado entre a busca principal e qualquer
    fallback do mesmo pedido) soma a espera já gasta; ao estourar
    `YT_THROTTLE_MAX_ESPERA_S`, levanta `EsperaExcedida` em vez de dormir mais.
  - Um contador de pedidos aguardando, protegido por lock próprio e curto,
    recusa o excedente (`YT_THROTTLE_MAX_FILA`) imediatamente, sem entrar na
    fila e sem dormir — é o que protege o pool de threads do cliente (2 vCPU)
    de ficar presas no YouTube.
  - `YT_THROTTLE_ATIVADO=false` desliga tudo: `janela` vira no-op e
    `espera_estimada` sempre devolve 0.0 — rollback sem rebuild.

`FilaCheia` e `EsperaExcedida` sobem como exceção de quem abriu a janela
(`core/downloader.py`); este módulo não as trata.

Para teste sem tempo real, o relógio e o sono são atributos de módulo
injetáveis (`_agora`, `_dormir`), no padrão de `patch.object` já usado no
restante do repositório.
"""

from __future__ import annotations

import os
import random
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Literal

# Configuração (seção 10 da spec) — lida uma vez, no boot do processo.
ATIVADO: bool = os.getenv("YT_THROTTLE_ATIVADO", "true").lower() == "true"
BUSCA_S: float = float(os.getenv("YT_THROTTLE_BUSCA_S", "30"))
TENTATIVA_S: float = float(os.getenv("YT_THROTTLE_TENTATIVA_S", "8"))
JITTER_PCT: float = float(os.getenv("YT_THROTTLE_JITTER_PCT", "0.3"))
MAX_ESPERA_S: float = float(os.getenv("YT_THROTTLE_MAX_ESPERA_S", "150"))
MAX_FILA: int = int(os.getenv("YT_THROTTLE_MAX_FILA", "4"))

# Relógio e sono injetáveis — testes trocam por `patch.object` para não
# dormir de verdade.
_agora = time.monotonic
_dormir = time.sleep

# Fim (monotonic) da última chamada ao YouTube — estado de módulo, válido
# entre tipos ("busca" e "tentativa" compartilham o mesmo relógio). Protegido
# pelo mesmo lock que serializa as chamadas.
_lock = threading.Lock()
_ultimo_fim: float | None = None

# Contador de pedidos aguardando a janela, com lock próprio e curto — nunca é
# mantido durante a espera nem durante a chamada real, só durante o incremento
# e o decremento.
_fila_lock = threading.Lock()
_fila_contador = 0


class FilaCheia(RuntimeError):
    """Já há `YT_THROTTLE_MAX_FILA` pedidos aguardando a janela do throttle."""


class EsperaExcedida(RuntimeError):
    """A espera deste pedido no throttle passaria de `YT_THROTTLE_MAX_ESPERA_S`."""


@dataclass
class Orcamento:
    """Acumula, por pedido, a espera (em segundos) já gasta nas janelas do
    throttle. O mesmo `Orcamento` deve ser passado à busca principal e a
    qualquer fallback do mesmo pedido, para o teto valer sobre o pedido como
    um todo — não sobre cada tentativa isolada."""

    gasto_s: float = 0.0


def _resetar() -> None:
    """Restaura o estado de módulo (`_ultimo_fim`, contador de fila). Só para
    uso em teste (setup/teardown de cada caso) — em produção o estado dura a
    vida do processo, de propósito."""
    global _ultimo_fim, _fila_contador
    with _lock:
        _ultimo_fim = None
    with _fila_lock:
        _fila_contador = 0


def _intervalo_base(tipo: str) -> float:
    if tipo == "busca":
        return BUSCA_S
    if tipo == "tentativa":
        return TENTATIVA_S
    raise ValueError(f"tipo de janela do throttle desconhecido: {tipo!r}")


def espera_estimada(tipo: str) -> float:
    """Quanto uma chamada de `tipo` esperaria se fosse feita agora — sem
    reservar vaga na fila nem gastar orçamento, é só leitura. Usada para
    decidir se vale avisar o ouvinte de que a busca está ocupada (seção 7.4
    da spec). Não inclui jitter: é uma estimativa, não a espera real que
    `janela` vai impor."""
    if not ATIVADO:
        return 0.0
    ultimo_fim = _ultimo_fim
    if ultimo_fim is None:
        return 0.0
    decorrido = _agora() - ultimo_fim
    return max(0.0, _intervalo_base(tipo) - decorrido)


@contextmanager
def janela(tipo: Literal["busca", "tentativa"], orcamento: Orcamento) -> Iterator[None]:
    """Serializa e espaça as chamadas ao YouTube. Cobre só a chamada real
    (`extract_info`) — abra a janela por cima dela, não por cima do
    tratamento do resultado.

    Levanta `FilaCheia` se já houver `YT_THROTTLE_MAX_FILA` pedidos
    aguardando (sem dormir) e `EsperaExcedida` se a espera deste pedido,
    somada ao que já foi gasto em `orcamento`, passar de
    `YT_THROTTLE_MAX_ESPERA_S`.
    """
    global _ultimo_fim, _fila_contador

    if not ATIVADO:
        yield
        return

    with _fila_lock:
        if _fila_contador >= MAX_FILA:
            raise FilaCheia(
                f"Fila do throttle do YouTube cheia: {MAX_FILA} pedido(s) já aguardando."
            )
        _fila_contador += 1

    try:
        with _lock:
            espera = 0.0
            if _ultimo_fim is not None:
                decorrido = _agora() - _ultimo_fim
                intervalo = _intervalo_base(tipo) * (1 + JITTER_PCT * random.random())
                espera = max(0.0, intervalo - decorrido)

            if espera > 0:
                if orcamento.gasto_s + espera > MAX_ESPERA_S:
                    raise EsperaExcedida(
                        f"Espera no throttle ({orcamento.gasto_s + espera:.1f}s) passaria "
                        f"do teto de {MAX_ESPERA_S:.0f}s para este pedido."
                    )
                orcamento.gasto_s += espera
                _dormir(espera)

            try:
                yield
            finally:
                # Atualizado na saída, inclusive em caso de exceção na
                # chamada real — o intervalo mínimo vale a partir do fim de
                # QUALQUER tentativa, não só das que tiveram sucesso.
                _ultimo_fim = _agora()
    finally:
        with _fila_lock:
            _fila_contador -= 1
