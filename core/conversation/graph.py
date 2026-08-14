"""Integração mínima com LangGraph.

O grafo não recebe ferramentas nem autorização para efeitos externos. Ele
apenas formaliza a entrada e delega a decisão controlada ao orquestrador; em
ambientes de testes leves o orquestrador usa o mesmo handler diretamente.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, TypedDict


class _GraphState(TypedDict, total=False):
    message: Any
    result: Any


def build_conversation_graph(handler: Callable[[Any], Awaitable[Any]]):
    try:
        from langgraph.graph import END, START, StateGraph
    except ImportError:
        return None

    async def process(state: _GraphState) -> dict[str, Any]:
        return {"result": await handler(state["message"])}

    builder = StateGraph(_GraphState)
    builder.add_node("process", process)
    builder.add_edge(START, "process")
    builder.add_edge("process", END)
    return builder.compile()
