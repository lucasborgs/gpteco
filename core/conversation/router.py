"""Router estruturado e seguro.

O LLM só devolve dados; regras de produção, confirmação e efeitos externos
permanecem no orquestrador. Um adaptador fake pode implementar ``route`` ou
``aroute`` para os testes.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import os
import re
from typing import Any, Protocol

from .contracts import Intent, RouterDecision


class Router(Protocol):
    async def route(self, text: str, *, context: list[str] = ()) -> RouterDecision: ...


class LLMUnavailable(RuntimeError):
    """A chamada ao provedor não pôde ser concluída; não é ambiguidade do usuário."""


_PRODUCTION = re.compile(r"\b(produ[cç][aã]o|reclama[cç][aã]o|den[uú]ncia|promo[cç][aã]o|promocional|sorteio)\b", re.I)
_GREETING = re.compile(r"^(oi|olá|ola|bom dia|boa tarde|boa noite|obrigad[oa]|valeu|vlw|tmj|tchau|até mais|ate mais|abraço|abraco)\b", re.I)
_REQUEST = re.compile(r"\b(toca|toque|coloca|coloque|manda|mande|quero ouvir|quero escutar|gostaria de ouvir|pede|pedir|pedido|m[uú]sica)\b", re.I)
_QUESTION = re.compile(r"\b(como|quando|onde|quem|qual|por que|porque|significa|hist[oó]ria|letra|[eé] verdade|curiosidade|[aà]lbum|show|banda|cantor)\b", re.I)
_INAPPROPRIATE = re.compile(r"\b(vadia|idiota|burro|porra|merda|foder|fod[aã]se)\b", re.I)


class StructuredRouter:
    """Router com LLM opcional e fallback lexical seguro.

    ``llm`` pode ser qualquer objeto com ``ainvoke``/``invoke`` ou uma função;
    a saída pode ser ``RouterDecision``, dict ou JSON. A resposta nunca é uma
    ferramenta: dados externos só são usados depois de validação determinística.
    """

    def __init__(self, llm: Any = None, *, allowed_topics: str = "") -> None:
        self.llm = llm
        self.allowed_topics = allowed_topics

    async def route(self, text: str, *, context: list[str] = ()) -> RouterDecision:
        decision = self._deterministic(text)
        # Produção, ofensa e saudações simples não precisam de LLM.
        if decision is not None:
            return decision
        if self.llm is not None:
            try:
                raw = await self._call_llm(text, context)
                return self._coerce(raw)
            except LLMUnavailable:
                return RouterDecision(Intent.UNCLEAR, failure_code="llm_unavailable")
            except (TypeError, ValueError, json.JSONDecodeError):
                return RouterDecision(Intent.UNCLEAR, question="Você quer conversar sobre música ou pedir uma faixa?")
        return RouterDecision(Intent.UNCLEAR, question="Você quer conversar sobre música ou pedir uma faixa?")

    def _deterministic(self, text: str) -> RouterDecision | None:
        value = text.strip()
        if _PRODUCTION.search(value):
            lowered = value.lower()
            intent = Intent.COMPLAINT if "reclama" in lowered else Intent.REPORT if "denún" in lowered or "denun" in lowered else Intent.PROMOTION if "promo" in lowered or "sorteio" in lowered else Intent.PRODUCTION
            return RouterDecision(intent)
        if _INAPPROPRIATE.search(value) and not _REQUEST.search(value):
            return RouterDecision(Intent.INAPPROPRIATE, inappropriate=True)
        if _GREETING.fullmatch(value.rstrip(".!😊👋")):
            return RouterDecision(Intent.GREETING)
        return None

    async def _call_llm(self, text: str, context: list[str]) -> Any:
        prompt = {
            "message": text,
            "recent_messages": context,
            "schema": "intent, artist, music, genre, decade, confidence, answer, question, missing",
            "intents": [item.value for item in Intent],
        }
        target = self.llm
        try:
            if hasattr(target, "ainvoke"):
                return await target.ainvoke(prompt)
            if hasattr(target, "invoke"):
                result = await asyncio.to_thread(target.invoke, prompt)
                return await result if inspect.isawaitable(result) else result
            if callable(target):
                if inspect.iscoroutinefunction(target):
                    return await target(prompt)
                result = await asyncio.to_thread(target, prompt)
                return await result if inspect.isawaitable(result) else result
            return target
        except Exception as error:
            raise LLMUnavailable("Router indisponível") from error

    @staticmethod
    def _coerce(raw: Any) -> RouterDecision:
        if isinstance(raw, RouterDecision):
            return raw
        if hasattr(raw, "content"):
            raw = raw.content
        if isinstance(raw, str):
            raw = json.loads(raw)
        if not isinstance(raw, dict):
            raise ValueError("saída do Router não é estruturada")
        intent = Intent(str(raw.get("intent", raw.get("intencao", "unclear"))))
        missing = raw.get("missing", raw.get("campos_ausentes", ())) or ()
        def to_bool(value: Any, default: bool = False) -> bool:
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                return value.strip().lower() in {"1", "true", "sim", "yes"}
            return default if value is None else bool(value)

        return RouterDecision(
            intent=intent,
            artist=str(raw.get("artist", raw.get("artista", "")) or "").strip(),
            music=str(raw.get("music", raw.get("musica", "")) or "").strip(),
            genre=str(raw.get("genre", raw.get("genero", "")) or "").strip(),
            decade=str(raw.get("decade", raw.get("decada", "")) or "").strip(),
            confidence=to_bool(raw.get("confidence", raw.get("is_confiante", True)), True),
            answer=str(raw.get("answer", raw.get("resposta", "")) or "").strip(),
            question=str(raw.get("question", raw.get("pergunta", "")) or "").strip(),
            missing=tuple(str(item) for item in missing),
            inappropriate=to_bool(raw.get("inappropriate"), raw.get("is_apropriado") is False),
            reason=str(raw.get("reason", raw.get("motivo", "")) or ""),
        )


def build_default_router() -> StructuredRouter:
    """Constrói o Router apenas quando o experimento é realmente usado."""
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("GROQ_API_KEY")
    if not api_key:
        return StructuredRouter()
    try:
        from openai import OpenAI
        from core import luzia

        client = OpenAI(
            api_key=api_key,
            base_url="https://api.groq.com/openai/v1" if os.getenv("GROQ_API_KEY") and not os.getenv("OPENAI_API_KEY") else None,
        )
        model = os.getenv("CONVERSATION_MODEL") or os.getenv("LLM_MODEL", "gpt-4o")

        def call(payload: dict[str, Any]) -> str:
            response = client.chat.completions.create(
                model=model,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": luzia.router_technical_prompt()},
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                ],
                temperature=0,
            )
            return response.choices[0].message.content or "{}"

        return StructuredRouter(call)
    except Exception:
        return StructuredRouter()
