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
# OpenAI tem prioridade na LLM. Groq é usado apenas se não houver OPENAI_API_KEY.
_USAR_GROQ: bool = bool(_GROQ_API_KEY) and not bool(_OPENAI_API_KEY)

# Modelos padrão por provedor (sobrescrevível via LLM_MODEL no .env)
_MODELO_PADRAO = "llama-3.3-70b-versatile" if _USAR_GROQ else "gpt-4o-mini"
LLM_MODEL: str = os.getenv("LLM_MODEL", _MODELO_PADRAO)

# Singleton: client criado uma única vez no import, reutiliza connection pool HTTP
if _USAR_GROQ:
    _client = OpenAI(api_key=_GROQ_API_KEY, base_url="https://api.groq.com/openai/v1")
    print(f"[LLM] Provedor: Groq | Modelo: {LLM_MODEL}")
else:
    _client = OpenAI(api_key=_OPENAI_API_KEY)
    print(f"[LLM] Provedor: OpenAI | Modelo: {LLM_MODEL}")


@dataclass
class MetadadosMusica:
    is_pedido_musical: bool
    musica: str
    artista: str
    is_flashback: bool
    is_apropriado: bool
    is_confiante: bool = True
    is_saudacao: bool = False
    is_pedido_explicito: bool = False
    genero: str = ""


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

    print(f"[LLM] Analisando: \"{texto_transcrito}\"")

    try:
        response = _client.chat.completions.create(
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

    campos_esperados = {"is_pedido_musical", "musica", "artista", "is_flashback", "is_apropriado", "is_confiante"}
    campos_faltando = campos_esperados - set(dados.keys())
    if campos_faltando:
        raise ValueError(f"Campos ausentes na resposta do LLM: {campos_faltando}")

    def _to_bool(valor) -> bool:
        """Converte valor do LLM para bool com segurança.
        Evita bool("false") == True (string "false" é truthy em Python).
        """
        if isinstance(valor, bool):
            return valor
        if isinstance(valor, str):
            return valor.strip().lower() == "true"
        return bool(valor)

    metadados = MetadadosMusica(
        is_pedido_musical=_to_bool(dados["is_pedido_musical"]),
        musica=str(dados["musica"]).strip(),
        artista=str(dados["artista"]).strip(),
        is_flashback=_to_bool(dados["is_flashback"]),
        is_apropriado=_to_bool(dados["is_apropriado"]),
        is_confiante=_to_bool(dados["is_confiante"]),
        is_saudacao=_to_bool(dados.get("is_saudacao", False)),
        is_pedido_explicito=_to_bool(dados.get("is_pedido_explicito", False)),
        genero=str(dados.get("genero", "")).strip(),
    )

    print(f"[LLM] is_pedido_musical={metadados.is_pedido_musical}")
    print(f"[LLM] Musica: '{metadados.musica}' | Artista: '{metadados.artista}'")
    print(f"[LLM] is_flashback={metadados.is_flashback} | is_apropriado={metadados.is_apropriado} | is_confiante={metadados.is_confiante} | is_saudacao={metadados.is_saudacao} | is_pedido_explicito={metadados.is_pedido_explicito}")

    return metadados
