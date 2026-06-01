"""
core/composer.py

Gera as mensagens de RECUSA/dúvida ao ouvinte com tom natural, mantendo as
regras de decisão em código (pipeline.py) e o texto canônico como rede de
segurança.

Princípio: o composer nunca decide nada. O pipeline já decidiu (recusou por
cooldown, fora do repertório, etc.) e passa a "situação" pronta. O composer só
redige a frase. Em qualquer falha (sem API, texto inválido, exceção) cai no
texto fixo (canned) de luzia.md — ou seja, o pior caso é a experiência de hoje.

Configuração (.env):
  COMPOSER_ENABLED : "true"/"false" (padrão true). Se false, sempre usa canned.
  COMPOSER_MODELO  : modelo a usar (padrão: gpt-4o, ou llama no Groq).
  OPENAI_API_KEY / GROQ_API_KEY : seleção de provedor (OpenAI tem prioridade).
"""

from __future__ import annotations

import os
import re
import time
from collections import defaultdict

from openai import OpenAI
from dotenv import load_dotenv

from core import luzia

load_dotenv()

_ENABLED: bool = os.getenv("COMPOSER_ENABLED", "true").lower() == "true"
_GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
_OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
_USAR_GROQ: bool = bool(_GROQ_API_KEY) and not bool(_OPENAI_API_KEY)

_MODELO_PADRAO = "llama-3.3-70b-versatile" if _USAR_GROQ else "gpt-4o"
MODELO: str = os.getenv("COMPOSER_MODELO", _MODELO_PADRAO)

if not _ENABLED:
    _client: OpenAI | None = None
    print("[COMPOSER] Desativado (COMPOSER_ENABLED=false) — usando mensagens fixas.")
elif _USAR_GROQ:
    _client = OpenAI(api_key=_GROQ_API_KEY, base_url="https://api.groq.com/openai/v1")
    print(f"[COMPOSER] Provedor: Groq | Modelo: {MODELO}")
elif _OPENAI_API_KEY:
    _client = OpenAI(api_key=_OPENAI_API_KEY)
    print(f"[COMPOSER] Provedor: OpenAI | Modelo: {MODELO}")
else:
    _client = None
    print("[COMPOSER] Sem API key — usando mensagens fixas.")

_MAX_CHARS = 400

# Indícios de tom errado / fora de marca → invalida a geração (cai no canned).
_BLOCKLIST = re.compile(
    r"\b(prezad[oa]|lamentamos|tape[çc]aria|navegando|queue|playlist|\bplay\b|"
    r"\btens\b|\best[áa]s\b|\bteu\b|\btua\b)\b",
    re.IGNORECASE,
)

# Mapeia situação → função que produz o texto canônico (rede de segurança).
_CANNED = {
    "nao_repertorio": lambda c: luzia.MSG_NAO_REPERTORIO.format_map(_Safe(c)),
    "cooldown":       lambda c: luzia.MSG_COOLDOWN,
    "inapropriado":   lambda c: luzia.MSG_INAPROPRIADO,
    "nao_id":         lambda c: luzia.MSG_NAO_ID,
    "confirmacao":    lambda c: luzia.MSG_CONFIRMACAO.format_map(_Safe(c)),
}


class _Safe(dict):
    """dict que não quebra .format_map quando falta uma chave (vira '')."""
    def __missing__(self, key):  # noqa: D401
        return ""


def _normalizar(texto: str) -> str:
    # WhatsApp usa *negrito* (um asterisco), não **negrito**.
    texto = re.sub(r"\*\*(.+?)\*\*", r"*\1*", texto)
    return texto.strip()


def _valido(texto: str) -> str | None:
    """Retorna o motivo da invalidez, ou None se válido."""
    if not texto:
        return "vazio"
    if len(texto) > _MAX_CHARS:
        return "tamanho"
    if _BLOCKLIST.search(texto):
        return "blocklist"
    return None


def compor(situacao: str, contexto: dict | None = None, texto_ouvinte: str = "") -> str:
    """
    Redige a mensagem de recusa para `situacao`, ou cai no texto fixo.

    Args:
        situacao: uma de luzia.SITUACOES_COMPOSER
                  (nao_repertorio, cooldown, inapropriado, nao_id, confirmacao).
        contexto: {artista, musica, genero, ...} usado na instrução e no canned.
        texto_ouvinte: mensagem original do ouvinte (dá personalização).

    Retorna sempre uma string pronta para enviar.
    """
    contexto = contexto or {}
    canned_fn = _CANNED.get(situacao)
    if canned_fn is None:
        raise ValueError(f"Situação de composer desconhecida: {situacao!r}")

    def _canned() -> str:
        return canned_fn(contexto)

    if _client is None:
        return _canned()

    t0 = time.monotonic()
    motivo = "erro"
    try:
        system = (
            "Você é a LuzIA, atendente da Luz FM no WhatsApp. Sua tarefa é escrever "
            "UMA mensagem curta ao ouvinte, dada a situação já decidida pelo sistema.\n\n"
            + luzia.diretrizes_luzia()
        )
        instrucao = luzia.instrucao_composer(situacao).format_map(_Safe(contexto))
        user = (
            f'Mensagem do ouvinte: "{texto_ouvinte}"\n\n'
            f"Situação: {situacao}\n"
            f"Instrução: {instrucao}\n\n"
            "Escreva apenas a mensagem final, sem aspas e sem rótulos."
        )
        resp = _client.chat.completions.create(
            model=MODELO,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.5,
            max_tokens=160,
        )
        texto = _normalizar(resp.choices[0].message.content or "")
        motivo = _valido(texto)
        latencia = int((time.monotonic() - t0) * 1000)
        if motivo is None:
            print(f"[COMPOSER] situacao={situacao} status=ok latencia_ms={latencia} chars={len(texto)}")
            return texto
        print(f"[COMPOSER] situacao={situacao} status=fallback latencia_ms={latencia} fallback_motivo={motivo}")
    except Exception as e:
        latencia = int((time.monotonic() - t0) * 1000)
        print(f"[COMPOSER] situacao={situacao} status=fallback latencia_ms={latencia} fallback_motivo=excecao:{e}")

    return _canned()
