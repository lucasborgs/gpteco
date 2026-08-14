from __future__ import annotations

import asyncio
from pathlib import Path

from core.conversation import (
    ConversationMode,
    ConversationOrchestrator,
    ConversationSelector,
    ConversationState,
    InMemorySessionStore,
    Intent,
    MessageReceived,
    RouterDecision,
    parse_conversation_mode,
)
from core.conversation.router import StructuredRouter


class FakeClock:
    def __init__(self, value: float = 0):
        self.value = value

    def __call__(self):
        return self.value

    def advance(self, seconds: float):
        self.value += seconds


class FakeRouter:
    def __init__(self, *decisions):
        self.decisions = list(decisions)
        self.calls = []

    async def route(self, text, **_kwargs):
        self.calls.append(text)
        return self.decisions.pop(0)


def make_orchestrator(router, *, clock=None, executor=None, **kwargs):
    clock = clock or FakeClock()
    return ConversationOrchestrator(
        router=router,
        executor=executor or (lambda _pending: {"sucesso": True, "codigo": "success", "mensagem": "entregue"}),
        session_store=InMemorySessionStore(clock=clock, ttl_seconds=900, max_messages=10, temp_dir=kwargs.pop("temp_dir", None)),
        cooldown_checker=kwargs.pop("cooldown_checker", lambda _jid: True),
        media_downloader=kwargs.pop("media_downloader", lambda _payload: None),
        transcriber=kwargs.pop("transcriber", lambda _path: ""),
        clock=clock,
        production_timeout_seconds=300,
        **kwargs,
    )


def test_selector_modes_and_invalid_configuration():
    assert parse_conversation_mode("invalid") is ConversationMode.LEGACY
    assert not ConversationSelector(ConversationMode.LEGACY).uses_conversation("a")
    assert ConversationSelector(ConversationMode.ALL).uses_conversation("a")
    allow = ConversationSelector(ConversationMode.ALLOWLIST, frozenset({"a@c.us"}))
    assert allow.uses_conversation("a@c.us")
    assert not allow.uses_conversation("b@c.us")


def test_session_ttl_history_and_audio_cleanup(tmp_path: Path):
    clock = FakeClock()
    store = InMemorySessionStore(clock=clock, ttl_seconds=10, max_messages=2, temp_dir=tmp_path)
    audio = tmp_path / "pending.ogg"
    audio.write_bytes(b"ogg")
    session = store.get_or_create("jid")
    store.touch(session, "one")
    store.touch(session, "two")
    store.touch(session, "three")
    assert session.recent_messages == ["two", "three"]
    from core.conversation.contracts import PendingRequest

    store.set_pending(session, PendingRequest(artist="a", music="m", audio_path=str(audio)))
    clock.advance(11)
    assert store.get("jid") is None
    assert not audio.exists()


def test_request_requires_confirmation_and_duplicate_confirmation_executes_once():
    router = FakeRouter(RouterDecision(Intent.MUSIC_REQUEST, artist="Artist", music="Song", in_repertoire=True))
    calls = []

    def executor(pending):
        calls.append(pending)
        return {"sucesso": True, "codigo": "success", "mensagem": "feito"}

    async def scenario():
        o = make_orchestrator(router, executor=executor)
        first = await o.processar(MessageReceived(jid="j", text="toca"))
        second = await o.processar(MessageReceived(jid="j", text="sim"))
        duplicate = await o.processar(MessageReceived(jid="j", text="sim"))
        return first, second, duplicate

    first, second, duplicate = asyncio.run(scenario())
    assert first.state is ConversationState.AWAITING_CONFIRMATION
    assert second.executor_result.code == "success"
    assert len(calls) == 1
    assert duplicate.state is ConversationState.COLLECTING_REQUEST


def test_out_of_repertoire_does_not_check_cooldown_or_execute():
    checks = []
    router = FakeRouter(RouterDecision(Intent.MUSIC_REQUEST, artist="A", music="M", in_repertoire=False))
    o = make_orchestrator(router, cooldown_checker=lambda jid: checks.append(jid) or True)
    result = asyncio.run(o.processar(MessageReceived(jid="j", text="pedido")))
    assert result.state is ConversationState.CONVERSING
    assert checks == []


def test_production_is_a_silent_gate_before_audio_and_router():
    router = FakeRouter(
        RouterDecision(Intent.PRODUCTION),
        RouterDecision(Intent.MUSIC_REQUEST, artist="A", music="M", in_repertoire=True),
    )
    media_calls, stt_calls = [], []
    clock = FakeClock()
    o = make_orchestrator(
        router,
        clock=clock,
        media_downloader=lambda payload: media_calls.append(payload) or "/tmp/a.ogg",
        transcriber=lambda path: stt_calls.append(path) or "pedido",
    )

    async def scenario():
        activated = await o.processar(MessageReceived(jid="j", text="quero falar com a produção"))
        silent = await o.processar(MessageReceived(jid="j", is_audio=True, raw_payload={"id": "a"}))
        calls_while_production = (len(media_calls), len(stt_calls))
        clock.advance(301)
        after = await o.processar(MessageReceived(jid="j", is_audio=True, raw_payload={"id": "b"}))
        return activated, silent, after, calls_while_production

    activated, silent, after, calls_while_production = asyncio.run(scenario())
    assert activated.state is ConversationState.PRODUCTION
    assert silent.silent is True
    assert calls_while_production == (0, 0)
    assert after.state is not ConversationState.PRODUCTION
    assert media_calls == [{"id": "b"}]


def test_audio_is_preserved_through_correction_and_removed_after_execution(tmp_path: Path):
    audio = tmp_path / "voice.ogg"
    audio.write_bytes(b"voice")
    router = FakeRouter(
        RouterDecision(Intent.MUSIC_REQUEST, artist="A", music="M", in_repertoire=True),
        RouterDecision(Intent.MUSIC_REQUEST, artist="B", music="N", in_repertoire=True),
    )
    received = []

    def executor(pending):
        received.append(pending)
        return {"sucesso": True, "codigo": "success"}

    o = make_orchestrator(
        router,
        executor=executor,
        media_downloader=lambda _payload: str(audio),
        transcriber=lambda _path: "pedido",
    )

    async def scenario():
        await o.processar(MessageReceived(jid="j", is_audio=True, raw_payload={"id": "a"}))
        await o.processar(MessageReceived(jid="j", text="corrige"))
        return await o.processar(MessageReceived(jid="j", text="sim"))

    result = asyncio.run(scenario())
    assert result.executor_result.success
    assert received[0].artist == "B"
    assert received[0].audio_path == str(audio)
    assert not audio.exists()


def test_structured_router_coerces_all_intentions_without_executing_effects():
    async def fake_llm(_payload):
        return {"intent": "music_question", "answer": "É uma faixa dos anos 80.", "confidence": "true"}

    router = StructuredRouter(fake_llm)
    result = asyncio.run(router.route("quem gravou essa música?"))
    assert result.intent is Intent.MUSIC_QUESTION
    assert result.answer.startswith("É uma faixa")

    for name in (
        "production", "complaint", "report", "promotion", "music_request",
        "music_question", "music_question_and_request", "greeting",
        "off_topic", "inappropriate", "unclear",
    ):
        decision = StructuredRouter._coerce({"intent": name})
        assert decision.intent.value == name


def test_question_and_request_is_replied_before_confirmation_and_complaint_wins():
    router = FakeRouter(
        RouterDecision(Intent.MUSIC_QUESTION_AND_REQUEST, artist="A", music="M", in_repertoire=True, answer="Foi gravada em 1985."),
        RouterDecision(Intent.COMPLAINT, artist="A", music="M"),
    )
    o = make_orchestrator(router)

    async def scenario():
        combined = await o.processar(MessageReceived(jid="j", text="pergunta e pedido"))
        complaint = await o.processar(MessageReceived(jid="j", text="reclamação com pedido"))
        return combined, complaint

    combined, complaint = asyncio.run(scenario())
    assert combined.replies[0] == "Foi gravada em 1985."
    assert combined.state is ConversationState.AWAITING_CONFIRMATION
    assert complaint.state is ConversationState.PRODUCTION
    assert complaint.replies
