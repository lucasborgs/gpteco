"""Contratos estáveis da conversa experimental.

São dados simples de propósito: facilitam fakes nos testes e impedem que o
chamador precise conhecer estados internos do grafo.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ConversationMode(str, Enum):
    LEGACY = "legacy"
    ALLOWLIST = "allowlist"
    ALL = "all"


class ConversationState(str, Enum):
    IDLE = "idle"
    CONVERSING = "conversing"
    COLLECTING_REQUEST = "collecting_request"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    EXECUTING_REQUEST = "executing_request"
    PRODUCTION = "production"


class Intent(str, Enum):
    PRODUCTION = "production"
    COMPLAINT = "complaint"
    REPORT = "report"
    PROMOTION = "promotion"
    MUSIC_REQUEST = "music_request"
    MUSIC_QUESTION = "music_question"
    MUSIC_QUESTION_AND_REQUEST = "music_question_and_request"
    GREETING = "greeting"
    OFF_TOPIC = "off_topic"
    INAPPROPRIATE = "inappropriate"
    UNCLEAR = "unclear"


@dataclass(slots=True)
class MessageReceived:
    jid: str
    message_id: str = ""
    text: str = ""
    is_audio: bool = False
    raw_payload: dict[str, Any] | None = None
    from_me: bool = False
    received_at: float | None = None


@dataclass(slots=True)
class PendingRequest:
    artist: str
    music: str
    jid: str = ""
    genre: str = ""
    original_text: str = ""
    transcript: str = ""
    audio_path: str | None = None
    source: str = "text"
    created_at: float = 0.0
    message_id: str = ""


@dataclass(slots=True)
class ConversationStateData:
    """Estado bruto armazenado por JID, sem prompts nem mensagens formatadas."""

    jid: str
    mode: ConversationState = ConversationState.IDLE
    recent_messages: list[str] = field(default_factory=list)
    pending_request: PendingRequest | None = None
    last_listener_message_at: float | None = None
    production_expires_at: float | None = None
    session_expires_at: float | None = None


@dataclass(slots=True)
class RouterDecision:
    intent: Intent
    artist: str = ""
    music: str = ""
    genre: str = ""
    decade: str = ""
    confidence: bool = True
    answer: str = ""
    question: str = ""
    missing: tuple[str, ...] = ()
    inappropriate: bool = False
    reason: str = ""
    failure_code: str = ""


@dataclass(slots=True)
class ExecutorResult:
    code: str
    success: bool = False
    delivered: bool = False
    message: str = ""
    artist: str = ""
    music: str = ""
    details: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_pipeline_result(cls, raw: dict[str, Any], *, artist: str, music: str) -> "ExecutorResult":
        """Traduz o resultado legado uma única vez, no adaptador do pipeline."""
        success = bool(raw.get("sucesso", False))
        return cls(
            code=str(raw.get("codigo") or ("success" if success else "unexpected_error")),
            success=success,
            delivered=bool(raw.get("entregue", success)),
            message=str(raw.get("mensagem") or ""),
            artist=artist,
            music=music,
            details=raw,
        )


@dataclass(slots=True)
class ConversationResult:
    replies: list[str] = field(default_factory=list)
    silent: bool = False
    state: ConversationState = ConversationState.IDLE
    executor_result: ExecutorResult | None = None
