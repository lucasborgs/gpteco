"""Adaptador do executor confirmado para o pipeline musical atual."""

from __future__ import annotations

from typing import Any

from core.pipeline import executar_pedido_confirmado


class ConfirmedPipelineExecutor:
    """Não interpreta novamente: passa artista/música já confirmados ao pipeline."""

    def __init__(self, *, jid: str | None = None) -> None:
        self.jid = jid

    def executar_pedido_confirmado(self, *, numero: str = "", jid: str = "", artista: str, musica: str, path_ogg: str | None = None, **_: Any) -> dict:
        return executar_pedido_confirmado(
            numero=self.jid or jid or numero,
            artista=artista,
            musica=musica,
            path_ogg=path_ogg,
        )
