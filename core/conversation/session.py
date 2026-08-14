"""Sessões voláteis por JID, sem checkpointer ou persistência."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Callable

from .contracts import ConversationState, ConversationStateData, PendingRequest


class InMemorySessionStore:
    """Armazena sessões em processo.

    A aplicação deve operar com um único worker enquanto este armazenamento for
    usado. ``clock`` é injetável para testar TTL sem esperar tempo real.
    """

    def __init__(
        self,
        *,
        ttl_seconds: float | None = None,
        max_messages: int | None = None,
        clock: Callable[[], float] = time.time,
        temp_dir: str | os.PathLike[str] | None = None,
    ) -> None:
        self.ttl_seconds = (
            float(ttl_seconds)
            if ttl_seconds is not None
            else float(os.getenv("CONVERSATION_SESSION_TIMEOUT_MIN", "15")) * 60
        )
        self.max_messages = int(max_messages if max_messages is not None else os.getenv("CONVERSATION_HISTORY_MAX_MESSAGES", "10"))
        self.clock = clock
        self.temp_dir = Path(temp_dir) if temp_dir else None
        self._sessions: dict[str, ConversationStateData] = {}

    def get(self, jid: str) -> ConversationStateData | None:
        session = self._sessions.get(jid)
        if session and self._expired(session):
            self.remove(jid)
            return None
        return session

    def get_or_create(self, jid: str) -> ConversationStateData:
        session = self.get(jid)
        if session is None:
            session = ConversationStateData(jid=jid)
            self._sessions[jid] = session
        return session

    def touch(self, session: ConversationStateData, text: str) -> None:
        now = self.clock()
        session.last_listener_message_at = now
        session.session_expires_at = now + self.ttl_seconds
        if text:
            session.recent_messages.append(text)
            del session.recent_messages[:-self.max_messages]

    def set_pending(self, session: ConversationStateData, pending: PendingRequest) -> None:
        previous = session.pending_request.audio_path if session.pending_request else None
        if previous and previous != pending.audio_path:
            self._cleanup_path(previous)
        session.pending_request = pending
        session.mode = ConversationState.AWAITING_CONFIRMATION

    def clear_pending(self, session: ConversationStateData) -> None:
        if session.pending_request:
            self._cleanup_path(session.pending_request.audio_path)
        session.pending_request = None

    def activate_production(self, session: ConversationStateData, timeout_seconds: float) -> None:
        self.clear_pending(session)
        session.mode = ConversationState.PRODUCTION
        session.production_expires_at = self.clock() + timeout_seconds

    def production_active(self, session: ConversationStateData) -> bool:
        if session.mode is not ConversationState.PRODUCTION:
            return False
        if session.production_expires_at is not None and self.clock() < session.production_expires_at:
            return True
        self.clear_pending(session)
        session.mode = ConversationState.IDLE
        session.production_expires_at = None
        return False

    def renew_production(self, session: ConversationStateData, timeout_seconds: float) -> None:
        session.production_expires_at = self.clock() + timeout_seconds
        session.last_listener_message_at = self.clock()

    def remove(self, jid: str) -> None:
        session = self._sessions.pop(jid, None)
        if session and session.pending_request:
            self._cleanup_path(session.pending_request.audio_path)

    def cleanup_orphans(self, max_age_seconds: float) -> int:
        if not self.temp_dir or not self.temp_dir.is_dir():
            return 0
        cutoff = self.clock() - max_age_seconds
        removed = 0
        for path in self.temp_dir.glob("*.ogg"):
            try:
                if path.stat().st_mtime < cutoff:
                    path.unlink()
                    removed += 1
            except OSError:
                pass
        return removed

    def _expired(self, session: ConversationStateData) -> bool:
        return session.session_expires_at is not None and self.clock() >= session.session_expires_at

    @staticmethod
    def _cleanup_path(path: str | None) -> None:
        if path and path != "__texto__":
            try:
                Path(path).unlink(missing_ok=True)
            except OSError:
                pass
