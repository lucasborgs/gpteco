"""Grafo LangGraph do workflow conversacional.

O único caminho de produção atravessa este grafo. O nó de decisão calcula o
resultado profundo do orquestrador; as arestas condicionais deixam explícitas
as transições externas relevantes: silêncio de produção, espera de confirmação
e resposta concluída.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Literal, TypedDict

from .contracts import ConversationState


class _GraphState(TypedDict, total=False):
    message: Any
    result: Any


def build_conversation_graph(handler: Callable[[Any], Awaitable[Any]]):
    from langgraph.graph import END, START, StateGraph

    async def decide(state: _GraphState) -> dict[str, Any]:
        return {"result": await handler(state["message"])}

    def transition(state: _GraphState) -> Literal["production", "awaiting_confirmation", "responded"]:
        result = state["result"]
        if result.state is ConversationState.PRODUCTION:
            return "production"
        if result.state is ConversationState.AWAITING_CONFIRMATION:
            return "awaiting_confirmation"
        return "responded"

    # Esses nós são os estados terminais do workflow: o resultado já está
    # calculado, e os callers recebem a mesma estrutura independente da rota.
    def keep_result(_: _GraphState) -> dict[str, Any]:
        return {}

    builder = StateGraph(_GraphState)
    builder.add_node("decide", decide)
    builder.add_node("production", keep_result)
    builder.add_node("awaiting_confirmation", keep_result)
    builder.add_node("responded", keep_result)
    builder.add_edge(START, "decide")
    builder.add_conditional_edges("decide", transition)
    builder.add_edge("production", END)
    builder.add_edge("awaiting_confirmation", END)
    builder.add_edge("responded", END)
    return builder.compile()
