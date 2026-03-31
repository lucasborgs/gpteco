"""
core/stt.py

Etapa 1 do pipeline: Ingestão e Transcrição (STT).

Recebe um arquivo de áudio (.ogg do WhatsApp) e transcreve para texto
usando a API Whisper do Groq (whisper-large-v3-turbo).

Vantagens sobre o modelo local:
  - Zero consumo de RAM do container (~1.4 GB economizados)
  - Latência menor (inferência na infraestrutura do Groq)
  - Mesma qualidade do modelo medium/large para PT-BR
"""

import os

import httpx
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")

# Modelo Whisper no Groq. Opções disponíveis:
#   whisper-large-v3-turbo  → rápido, alta qualidade (padrão)
#   whisper-large-v3        → máxima qualidade, um pouco mais lento
WHISPER_MODEL: str = os.getenv("WHISPER_MODEL", "whisper-large-v3-turbo")

_GROQ_ENDPOINT = "https://api.groq.com/openai/v1/audio/transcriptions"


def transcrever(path_audio: str, idioma: str = "pt") -> str:
    """
    Transcreve um arquivo de áudio para texto em português via API Groq.

    Args:
        path_audio : caminho do arquivo de áudio (.ogg, .mp3, .wav, etc.).
        idioma     : código ISO do idioma para guiar o decodificador (padrão: "pt").

    Retorna:
        str : texto transcrito, limpo de espaços extras.

    Raises:
        FileNotFoundError : se o arquivo de áudio não existir.
        RuntimeError      : se a chamada à API falhar.
    """
    if not os.path.isfile(path_audio):
        raise FileNotFoundError(f"Arquivo de áudio não encontrado: {path_audio}")

    print(f"[STT] Transcrevendo via Groq ({WHISPER_MODEL}): {os.path.basename(path_audio)}")

    with open(path_audio, "rb") as f:
        try:
            response = httpx.post(
                _GROQ_ENDPOINT,
                headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
                data={"model": WHISPER_MODEL, "language": idioma},
                files={"file": (os.path.basename(path_audio), f, "audio/ogg")},
                timeout=60,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise RuntimeError(f"Groq STT erro {e.response.status_code}: {e.response.text}") from e
        except Exception as e:
            raise RuntimeError(f"Groq STT falha na requisição: {e}") from e

    texto = response.json()["text"].strip()
    print(f"[STT] Transcrição: \"{texto}\"")
    return texto
