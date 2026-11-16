"""Ações de recuperação da sessão WAHA usadas pelo monitor do servidor."""

from typing import Any


def acao_reconexao(status: str) -> str:
    """Retorna a ação adequada para o estado atual da sessão."""
    return "start" if status == "STOPPED" else "restart"


async def solicitar_reconexao(
    client: Any,
    *,
    waha_url: str,
    session: str,
    status: str,
    headers: dict[str, str],
) -> tuple[str, Any]:
    """Solicita start/restart usando o método POST exigido pela API WAHA."""
    acao = acao_reconexao(status)
    response = await client.post(
        f"{waha_url}/api/sessions/{session}/{acao}",
        headers=headers,
    )
    return acao, response
