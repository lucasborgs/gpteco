"""Camada conversacional experimental da Luzia.

O módulo público é deliberadamente pequeno: :class:`ConversationOrchestrator`
recebe uma mensagem e devolve um :class:`ConversationResult`. WAHA e o fluxo
legado ficam fora deste pacote.
"""

from .contracts import (
    ConversationMode,
    ConversationResult,
    ConversationState,
    ExecutorResult,
    Intent,
    MessageReceived,
    PendingRequest,
    RouterDecision,
)
from .selector import ConversationSelector, parse_conversation_mode
from .session import InMemorySessionStore


def __getattr__(name: str):
    # Mantém contratos e seletor importáveis em ambientes de teste leves; o
    # orquestrador só carrega adaptadores de banco/áudio quando for usado.
    if name == "ConversationOrchestrator":
        from .orchestrator import ConversationOrchestrator

        return ConversationOrchestrator
    raise AttributeError(name)

__all__ = [
    "ConversationMode",
    "ConversationResult",
    "ConversationState",
    "ConversationOrchestrator",
    "ConversationSelector",
    "ExecutorResult",
    "InMemorySessionStore",
    "Intent",
    "MessageReceived",
    "PendingRequest",
    "RouterDecision",
    "parse_conversation_mode",
]
