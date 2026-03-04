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

SYSTEM_PROMPT = """
Você é o assistente de triagem de pedidos de uma rádio FM brasileira.
O público é adulto (30+) e a programação é focada em flashbacks: grandes sucessos
das décadas de 70, 80, 90 e início dos anos 2000 (pop, rock, MPB, sertanejo raiz,
pagode clássico, axé de época, etc.). Músicas lançadas após 2010 NÃO se qualificam
como flashback para esta rádio.

Analise a mensagem do ouvinte e retorne APENAS um objeto JSON válido com estas chaves:

- "is_pedido_musical": boolean — true se a mensagem é um pedido de música para a rádio;
                       false para qualquer outra coisa (saudações, agradecimentos,
                       perguntas gerais, elogios, conversas, etc.)
- "musica"           : string com o título da música mencionada (ou "" se não identificado)
- "artista"          : string com o nome do artista/banda (ou "" se não identificado)
- "is_flashback"     : boolean — true se a música se encaixa na programação flashback da rádio
- "is_apropriado"    : boolean — true se a mensagem é respeitosa (sem xingamentos, ofensas
                       ou conteúdo impróprio para rádio); false caso contrário

Regras importantes:
0. Determine PRIMEIRO se é um pedido de música. Se is_pedido_musical for false, os outros
   campos podem assumir seus valores padrão ("", "", false, true) — não force identificação.
1. Se não conseguir identificar música ou artista com confiança, retorne strings vazias
   e is_flashback: false.
2. is_apropriado avalia o TOM da mensagem do ouvinte, não o conteúdo da música.
3. Normalize artista e música: capitalize corretamente, remova ruído da transcrição.
4. Retorne SOMENTE o JSON, sem markdown, sem comentários, sem texto adicional.
5. Se o ouvinte mencionar mais de uma música, identifique APENAS a primeira
   mencionada na mensagem. Ignore as demais completamente.
""".strip()


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
                {"role": "system", "content": SYSTEM_PROMPT},
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
