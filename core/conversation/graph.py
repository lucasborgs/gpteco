"""Workflow LangGraph da conversa, composto por fases reais.

O grafo conhece só o protocolo interno do workflow. Cada nó executa uma fase
material (sessão, mídia, confirmação, Router ou uma resposta) e as arestas
condicionais escolhem o próximo passo antes de qualquer resultado final.
"""

from __future__ import annotations

from typing import Any, Literal, Protocol, TypedDict


class ConversationGraphState(TypedDict, total=False):
    message: Any
    session: Any
    text: str
    audio_path: str | None
    decision: Any
    result: Any


class ConversationWorkflow(Protocol):
    async def graph_load_session(self, state: ConversationGraphState) -> dict[str, Any]: ...
    def graph_production_active(self, state: ConversationGraphState) -> bool: ...
    async def graph_silence_production(self, state: ConversationGraphState) -> dict[str, Any]: ...
    async def graph_normalize(self, state: ConversationGraphState) -> dict[str, Any]: ...
    def graph_input_transition(self, state: ConversationGraphState) -> Literal["audio_unintelligible", "confirm", "cancel", "collect", "route"]: ...
    async def graph_audio_unintelligible(self, state: ConversationGraphState) -> dict[str, Any]: ...
    async def graph_confirm(self, state: ConversationGraphState) -> dict[str, Any]: ...
    async def graph_cancel(self, state: ConversationGraphState) -> dict[str, Any]: ...
    async def graph_collect(self, state: ConversationGraphState) -> dict[str, Any]: ...
    async def graph_route(self, state: ConversationGraphState) -> dict[str, Any]: ...
    def graph_route_transition(self, state: ConversationGraphState) -> Literal["llm_unavailable", "production", "request", "conversation"]: ...
    async def graph_llm_unavailable(self, state: ConversationGraphState) -> dict[str, Any]: ...
    async def graph_enter_production(self, state: ConversationGraphState) -> dict[str, Any]: ...
    async def graph_request(self, state: ConversationGraphState) -> dict[str, Any]: ...
    async def graph_conversation(self, state: ConversationGraphState) -> dict[str, Any]: ...


def build_conversation_graph(workflow: ConversationWorkflow):
    from langgraph.graph import END, START, StateGraph

    builder = StateGraph(ConversationGraphState)
    builder.add_node("load_session", workflow.graph_load_session)
    builder.add_node("production_silence", workflow.graph_silence_production)
    builder.add_node("normalize", workflow.graph_normalize)
    builder.add_node("audio_unintelligible", workflow.graph_audio_unintelligible)
    builder.add_node("confirm", workflow.graph_confirm)
    builder.add_node("cancel", workflow.graph_cancel)
    builder.add_node("collect", workflow.graph_collect)
    builder.add_node("route", workflow.graph_route)
    builder.add_node("llm_unavailable", workflow.graph_llm_unavailable)
    builder.add_node("enter_production", workflow.graph_enter_production)
    builder.add_node("request", workflow.graph_request)
    builder.add_node("conversation", workflow.graph_conversation)

    builder.add_edge(START, "load_session")
    builder.add_conditional_edges(
        "load_session",
        lambda state: "production_silence" if workflow.graph_production_active(state) else "normalize",
    )
    builder.add_edge("production_silence", END)
    builder.add_conditional_edges("normalize", workflow.graph_input_transition)
    for node in ("audio_unintelligible", "confirm", "cancel", "collect"):
        builder.add_edge(node, END)
    builder.add_conditional_edges(
        "route",
        workflow.graph_route_transition,
        {
            "llm_unavailable": "llm_unavailable",
            "production": "enter_production",
            "request": "request",
            "conversation": "conversation",
        },
    )
    for node in ("llm_unavailable", "enter_production", "request", "conversation"):
        builder.add_edge(node, END)
    return builder.compile()
