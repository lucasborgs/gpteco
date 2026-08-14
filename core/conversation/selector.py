"""Seleção isolada entre o fluxo legado e o experimental."""

from __future__ import annotations

import os
from dataclasses import dataclass

from .contracts import ConversationMode


def parse_conversation_mode(value: str | None) -> ConversationMode:
    """Converte configuração inválida em ``legacy`` por segurança."""
    normalized = (value or "legacy").strip().lower()
    try:
        return ConversationMode(normalized)
    except ValueError:
        return ConversationMode.LEGACY


def parse_allowed_jids(value: str | None) -> frozenset[str]:
    return frozenset(item.strip() for item in (value or "").split(",") if item.strip())


@dataclass(frozen=True, slots=True)
class ConversationSelector:
    mode: ConversationMode = ConversationMode.LEGACY
    allowed_jids: frozenset[str] = frozenset()

    @classmethod
    def from_environment(cls) -> "ConversationSelector":
        return cls(
            mode=parse_conversation_mode(os.getenv("CONVERSATION_MODE", "legacy")),
            allowed_jids=parse_allowed_jids(os.getenv("CONVERSATION_ALLOWED_JIDS", "")),
        )

    def uses_conversation(self, jid: str) -> bool:
        if self.mode is ConversationMode.ALL:
            return True
        if self.mode is ConversationMode.ALLOWLIST:
            return jid in self.allowed_jids
        return False
