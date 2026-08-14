"""Seam único entre a conversa e o pipeline musical confirmado."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Protocol

from .contracts import ExecutorResult, PendingRequest


class ConfirmedRequestExecutor(Protocol):
    """Executa exatamente um pedido já confirmado e devolve seu resultado."""

    async def execute(self, request: PendingRequest) -> ExecutorResult: ...


class ConfirmedPipelineExecutor:
    """Não interpreta novamente: passa artista/música já confirmados ao pipeline."""

    def __init__(self, pipeline: Callable[..., dict] | None = None) -> None:
        self._pipeline = pipeline

    async def execute(self, request: PendingRequest) -> ExecutorResult:
        pipeline = self._pipeline
        if pipeline is None:
            from core.pipeline import executar_pedido_confirmado
            pipeline = executar_pedido_confirmado
        raw = await asyncio.to_thread(
            pipeline,
            numero=request.jid,
            artista=request.artist,
            musica=request.music,
            path_ogg=request.audio_path,
        )
        return ExecutorResult.from_pipeline_result(raw, artist=request.artist, music=request.music)
