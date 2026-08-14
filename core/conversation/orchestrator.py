"""Orquestrador conversacional: uma interface profunda para o webhook."""

from __future__ import annotations

import asyncio
import inspect
import os
import re
import time
from collections.abc import Callable
from typing import Any

from core import config_radio

from .contracts import (
    ConversationResult,
    ConversationState,
    ExecutorResult,
    Intent,
    MessageReceived,
    PendingRequest,
    RouterDecision,
)
from .router import Router, build_default_router
from .session import InMemorySessionStore
from .graph import build_conversation_graph
from .executor import ConfirmedRequestExecutor
from .repertoire import DeterministicRepertoireChecker


_YES = re.compile(r"^(sim|s|isso|exato|pode colocar|pode tocar|manda|mand[aá]|confirma|confirmo|yes|ok|pode)$", re.I)
_NO = re.compile(r"^(n[aã]o|nao|n|cancela|cancelar|esquece|deixa pra l[aá])$", re.I)


class ConversationOrchestrator:
    """Processa uma mensagem e esconde Router, sessão e pipeline do transporte."""

    def __init__(
        self,
        *,
        router: Router,
        executor: ConfirmedRequestExecutor,
        session_store: InMemorySessionStore | None = None,
        media_downloader: Callable[[dict[str, Any]], Any] | None = None,
        transcriber: Callable[[str], Any] | None = None,
        cooldown_checker: Callable[[str], Any] | None = None,
        repertoire_checker: DeterministicRepertoireChecker | None = None,
        composer: Callable[[str, dict[str, Any], str], Any] | None = None,
        curiosity: Callable[[str, str], Any] | None = None,
        clock: Callable[[], float] = time.time,
        production_timeout_seconds: float | None = None,
    ) -> None:
        self.router = router
        self.executor = executor
        self.sessions = session_store or InMemorySessionStore(clock=clock)
        if media_downloader is None or transcriber is None or cooldown_checker is None:
            # Dependências reais só são importadas quando o orquestrador é
            # construído; contratos e testes com fakes permanecem leves.
            from core import database, stt, whatsapp

            media_downloader = media_downloader or whatsapp.baixar_audio
            transcriber = transcriber or stt.transcrever
            cooldown_checker = cooldown_checker or database.verificar_cooldown
        self.media_downloader = media_downloader
        self.transcriber = transcriber
        self.cooldown_checker = cooldown_checker
        self.repertoire_checker = repertoire_checker or DeterministicRepertoireChecker.from_profile()
        self.composer = composer
        self.curiosity = curiosity
        self.clock = clock
        self.production_timeout_seconds = production_timeout_seconds or float(os.getenv("CONVERSATION_PRODUCTION_TIMEOUT_MIN", "5")) * 60
        self._locks: dict[str, asyncio.Lock] = {}
        self.graph = build_conversation_graph(self._processar_serial)

    @classmethod
    def from_environment(cls) -> "ConversationOrchestrator":
        from .executor import ConfirmedPipelineExecutor

        return cls(
            router=build_default_router(),
            executor=ConfirmedPipelineExecutor(),
            session_store=InMemorySessionStore(),
        )

    async def processar(self, mensagem_recebida: MessageReceived) -> ConversationResult:
        """Entrada única da camada conversacional."""
        if mensagem_recebida.from_me:
            return ConversationResult(silent=True, state=ConversationState.IDLE)
        lock = self._locks.setdefault(mensagem_recebida.jid, asyncio.Lock())
        async with lock:
            output = await self.graph.ainvoke({"message": mensagem_recebida})
            return output["result"]

    async def _processar_serial(self, message: MessageReceived) -> ConversationResult:
        session = self.sessions.get_or_create(message.jid)
        # A própria busca já remove sessão expirada; a expiração também remove .ogg.
        self.sessions.touch(session, message.text)

        if self.sessions.production_active(session):
            # fromMe já é filtrado pelo webhook; portanto qualquer mensagem aqui
            # é do ouvinte e renova o timeout móvel, sem resposta.
            self.sessions.renew_production(session, self.production_timeout_seconds)
            return ConversationResult(silent=True, state=ConversationState.PRODUCTION)

        text, audio_path = await self._normalize_input(message)
        if message.is_audio and not text:
            self.sessions.clear_pending(session)
            session.mode = ConversationState.CONVERSING
            return ConversationResult(
                replies=["Não consegui entender o áudio. Pode mandar outro ou escrever o nome da música?"],
                state=session.mode,
            )

        # Confirmação e cancelamento são determinísticos e não consomem LLM.
        pending = session.pending_request
        if pending and _YES.fullmatch(text.strip()):
            return await self._confirm(session, pending)
        if pending and _NO.fullmatch(text.strip()):
            self.sessions.clear_pending(session)
            session.mode = ConversationState.CONVERSING
            return ConversationResult(replies=["Tudo bem, cancelei esse pedido. Se quiser, pode me mandar outra música."], state=session.mode)
        if not pending and _YES.fullmatch(text.strip()):
            session.mode = ConversationState.COLLECTING_REQUEST
            return ConversationResult(replies=["Me manda o nome da música e do artista que você quer ouvir."], state=session.mode)

        decision = await self.router.route(text, context=session.recent_messages[-10:])
        if decision.failure_code == "llm_unavailable":
            session.mode = ConversationState.CONVERSING
            return ConversationResult(replies=[self._fixed("llm_unavailable")], state=session.mode)
        if decision.intent in (Intent.PRODUCTION, Intent.COMPLAINT, Intent.REPORT, Intent.PROMOTION):
            self.sessions.activate_production(session, self.production_timeout_seconds)
            return ConversationResult(replies=[self._fixed("production")], state=ConversationState.PRODUCTION)
        if decision.intent is Intent.INAPPROPRIATE or decision.inappropriate:
            session.mode = ConversationState.CONVERSING
            return ConversationResult(replies=[self._fixed("inappropriate")], state=session.mode)
        if decision.intent is Intent.MUSIC_QUESTION_AND_REQUEST and decision.answer:
            first_reply = decision.answer
        else:
            first_reply = ""

        if decision.intent in (Intent.MUSIC_REQUEST, Intent.MUSIC_QUESTION_AND_REQUEST):
            result = await self._handle_request(session, message, text, audio_path, decision)
            if first_reply:
                result.replies.insert(0, first_reply)
            return result
        if decision.intent is Intent.MUSIC_QUESTION:
            session.mode = ConversationState.CONVERSING
            return ConversationResult(replies=[decision.answer or "Posso conversar sobre artistas, músicas, álbuns, letras e histórias da música."], state=session.mode)
        if decision.intent is Intent.GREETING:
            session.mode = ConversationState.CONVERSING
            return ConversationResult(replies=[self._fixed("greeting")], state=session.mode)
        if decision.intent is Intent.OFF_TOPIC:
            session.mode = ConversationState.CONVERSING
            return ConversationResult(replies=["Eu consigo ajudar com música: artistas, álbuns, letras, shows ou pedidos para a rádio."], state=session.mode)
        session.mode = ConversationState.CONVERSING
        return ConversationResult(replies=[decision.question or "Você quer conversar sobre música ou pedir uma faixa?"], state=session.mode)

    async def _normalize_input(self, message: MessageReceived) -> tuple[str, str | None]:
        if not message.is_audio:
            return message.text.strip(), None
        # Esta função só é chamada depois da trava de produção.
        raw = message.raw_payload or {}
        try:
            path = await self._call_adapter(self.media_downloader, raw)
        except Exception:
            return "", None
        if not path:
            return "", None
        try:
            transcript = await self._call_adapter(self.transcriber, path)
        except Exception:
            self._remove_file(str(path))
            return "", None
        return str(transcript or "").strip(), str(path)

    async def _handle_request(
        self,
        session: Any,
        message: MessageReceived,
        text: str,
        audio_path: str | None,
        decision: RouterDecision,
    ) -> ConversationResult:
        artist, music = decision.artist.strip(), decision.music.strip()
        if session.pending_request:
            # Correção textual atualiza os metadados, mas preserva o áudio que
            # originou o pedido para a mixagem confirmada.
            audio_path = audio_path or session.pending_request.audio_path
        missing = list(decision.missing)
        if not artist:
            missing.append("artista")
        if not music:
            missing.append("música")
        if missing or not decision.confidence:
            session.mode = ConversationState.COLLECTING_REQUEST
            missing_text = " e ".join(dict.fromkeys(missing)) or "o nome da música e do artista"
            return ConversationResult(replies=[f"Qual {missing_text} você quer pedir?"], state=session.mode)

        allowed = self.repertoire_checker.allows(artist, music, decision.genre, decision.decade)
        if not allowed:
            self.sessions.clear_pending(session)
            session.mode = ConversationState.CONVERSING
            return ConversationResult(replies=[self._compose("out_of_repertoire", {"artist": artist, "music": music})], state=session.mode)

        if not await self._call_adapter(self.cooldown_checker, message.jid):
            # Cooldown não muda o estado de conversa nem consulta acervo.
            if audio_path:
                self._remove_file(audio_path)
            session.mode = ConversationState.CONVERSING
            return ConversationResult(replies=[self._compose("cooldown", {})], state=session.mode)

        pending = PendingRequest(
            jid=message.jid,
            artist=artist,
            music=music,
            genre=decision.genre,
            original_text=message.text,
            transcript=text if message.is_audio else "",
            audio_path=audio_path,
            source="audio" if message.is_audio else "text",
            created_at=self.clock(),
            message_id=message.message_id,
        )
        self.sessions.set_pending(session, pending)
        return ConversationResult(
            replies=[self._compose("confirmation", {"artist": artist, "music": music})],
            state=ConversationState.AWAITING_CONFIRMATION,
        )

    async def _confirm(self, session: Any, pending: PendingRequest) -> ConversationResult:
        # Consome a confirmação antes de qualquer efeito externo. O lock por JID
        # também torna duplicatas do WAHA idempotentes.
        session.pending_request = None
        session.mode = ConversationState.EXECUTING_REQUEST
        try:
            result = await self._execute(pending)
        finally:
            # O áudio original é temporário e só precisa existir durante a
            # execução confirmada, inclusive em falha definitiva.
            if pending.audio_path:
                self._remove_file(pending.audio_path)
        if result.success:
            replies = [result.message or self._success_message(pending)]
            if self.curiosity and not self.sessions.production_active(session):
                try:
                    fact = await self._call_adapter(self.curiosity, pending.artist, pending.music)
                    if fact:
                        replies.append(str(fact))
                except Exception:
                    pass
            session.mode = ConversationState.CONVERSING
            return ConversationResult(replies=replies, state=session.mode, executor_result=result)
        session.mode = ConversationState.CONVERSING
        return ConversationResult(replies=[self._failure_message(result.code)], state=session.mode, executor_result=result)

    async def _execute(self, pending: PendingRequest) -> ExecutorResult:
        try:
            return await self.executor.execute(pending)
        except Exception as exc:
            return ExecutorResult(code="unexpected_error", details={"exception": str(exc)})

    def _fixed(self, kind: str) -> str:
        if kind == "production":
            return getattr(config_radio, "MSG_PRODUCAO_ATIVADO", "Combinado! Nossa equipe vai continuar daqui com você.")
        if kind == "greeting":
            return getattr(config_radio, "MSG_SAUDACAO", "Oi! Posso ajudar com música?")
        if kind == "inappropriate":
            return getattr(config_radio, "MSG_INAPROPRIADO", "Vamos manter o respeito. Posso ajudar com música.")
        if kind == "llm_unavailable":
            return getattr(config_radio, "MSG_LLM_UNAVAILABLE", "Não consegui concluir isso agora. Tenta de novo daqui a pouquinho?")
        return "Não consegui concluir isso agora. Tenta de novo daqui a pouquinho?"

    def _compose(self, kind: str, context: dict[str, Any]) -> str:
        if self.composer:
            try:
                value = self.composer(kind, context, "")
                return str(value)
            except Exception:
                pass
        if kind == "confirmation":
            return f"Você quer *{context['music']}*, de {context['artist']}? Responda *SIM* para confirmar ou mande a correção."
        if kind == "cooldown":
            return getattr(config_radio, "MSG_COOLDOWN", "Você já fez um pedido há pouco. Tente novamente mais tarde.")
        if kind == "out_of_repertoire":
            return getattr(config_radio, "MSG_NAO_REPERTORIO", "Essa música não faz parte do repertório da rádio.").format(
                artist=context["artist"], artista=context["artist"], music=context["music"], musica=context["music"]
            )
        return self._fixed("error")

    @staticmethod
    def _success_message(pending: PendingRequest) -> str:
        return f"{pending.music} - {pending.artist} entrou na fila."

    @staticmethod
    def _failure_message(code: str) -> str:
        return {
            "cooldown": "Você já fez um pedido há pouco. Tente novamente mais tarde.",
            "stt_unintelligible": "Não consegui entender o áudio. Pode mandar outro ou escrever o pedido?",
            "request_not_identified": "Não consegui identificar a música e o artista. Pode mandar os dois nomes?",
            "out_of_repertoire": "Essa música não faz parte do repertório da rádio. Pode escolher outro clássico?",
            "source_not_found": "Não consegui localizar essa faixa agora. Tenta outra daqui a pouco?",
            "download_failed": "A música não pôde ser localizada agora. Tenta novamente mais tarde?",
            "mix_failed": "Não consegui preparar o áudio agora. Tenta novamente daqui a pouco?",
            "queue_failed": "Não consegui entregar o pedido à rádio. Tenta novamente mais tarde?",
            "database_failed": "Tive uma falha ao consultar a rádio. Tenta novamente daqui a pouco?",
            "llm_unavailable": "Não consegui entender a mensagem agora. Pode escrever o nome da música e do artista?",
        }.get(code, "Ô, parece que alguma coisa saiu do ritmo por aqui e não consegui concluir seu pedido agora. Tenta de novo daqui a pouquinho?")

    @staticmethod
    async def _call_adapter(fn: Callable[..., Any], *args: Any) -> Any:
        """Mantém adaptadores async no loop e desloca os síncronos para thread."""
        if inspect.iscoroutinefunction(fn):
            return await fn(*args)
        value = await asyncio.to_thread(fn, *args)
        return await value if inspect.isawaitable(value) else value

    @staticmethod
    def _remove_file(path: str) -> None:
        try:
            os.remove(path)
        except OSError:
            pass
