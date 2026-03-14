"""
core/intelligence.py

Etapa 2 do pipeline: Inteligência / Extração de Metadados.

Suporta dois provedores de LLM (configurado via .env):
  - Groq  : gratuito, ideal para testes. Defina GROQ_API_KEY no .env.
  - OpenAI: produção. Defina OPENAI_API_KEY no .env.

O provedor é selecionado automaticamente: se GROQ_API_KEY estiver presente,
o Groq é usado. Caso contrário, cai para OpenAI.
A API do Groq é compatível com o SDK da OpenAI — nenhuma biblioteca extra necessária.
"""

import os
import json
from dataclasses import dataclass
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

_GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
_OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
_USAR_GROQ: bool = bool(_GROQ_API_KEY)

# Modelos padrão por provedor (sobrescrevível via LLM_MODEL no .env)
_MODELO_PADRAO = "llama-3.3-70b-versatile" if _USAR_GROQ else "gpt-4o-mini"
LLM_MODEL: str = os.getenv("LLM_MODEL", _MODELO_PADRAO)


@dataclass
class MetadadosMusica:
    is_pedido_musical: bool
    musica: str
    artista: str
    is_flashback: bool
    is_apropriado: bool


def analisar(texto_transcrito: str) -> MetadadosMusica:
    """
    Envia o texto ao LLM e extrai metadados + aplica regras de negócio.

    Args:
        texto_transcrito : texto transcrito pelo Whisper.

    Retorna:
        MetadadosMusica : dataclass com artista, musica e os dois booleans.

    Raises:
        ValueError  : se o LLM retornar JSON inválido ou com campos ausentes.
        RuntimeError: se a chamada à API falhar.
    """
    from core import config_radio
    system_prompt = config_radio.build_system_prompt()

    if _USAR_GROQ:
        client = OpenAI(api_key=_GROQ_API_KEY, base_url="https://api.groq.com/openai/v1")
        print(f"[LLM] Provedor: Groq | Modelo: {LLM_MODEL}")
    else:
        client = OpenAI(api_key=_OPENAI_API_KEY)
        print(f"[LLM] Provedor: OpenAI | Modelo: {LLM_MODEL}")

    print(f"[LLM] Analisando: \"{texto_transcrito}\"")

    try:
        response = client.chat.completions.create(
            model=LLM_MODEL,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": texto_transcrito},
            ],
            temperature=0.1,  # Baixa temperatura para respostas determinísticas
        )
    except Exception as e:
        raise RuntimeError(f"Falha na chamada ao LLM: {e}") from e

    conteudo = response.choices[0].message.content
    print(f"[LLM] Resposta: {conteudo}")

    try:
        dados = json.loads(conteudo)
    except json.JSONDecodeError as e:
        raise ValueError(f"LLM retornou JSON inválido: {conteudo}") from e

    campos_esperados = {"is_pedido_musical", "musica", "artista", "is_flashback", "is_apropriado"}
    campos_faltando = campos_esperados - set(dados.keys())
    if campos_faltando:
        raise ValueError(f"Campos ausentes na resposta do LLM: {campos_faltando}")

    metadados = MetadadosMusica(
        is_pedido_musical=bool(dados["is_pedido_musical"]),
        musica=str(dados["musica"]).strip(),
        artista=str(dados["artista"]).strip(),
        is_flashback=bool(dados["is_flashback"]),
        is_apropriado=bool(dados["is_apropriado"]),
    )

    print(f"[LLM] is_pedido_musical={metadados.is_pedido_musical}")
    print(f"[LLM] Musica: '{metadados.musica}' | Artista: '{metadados.artista}'")
    print(f"[LLM] is_flashback={metadados.is_flashback} | is_apropriado={metadados.is_apropriado}")

    return metadados
