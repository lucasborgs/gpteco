"""
core/whatsapp.py

Cliente do WAHA (WhatsApp HTTP API) para recepção e envio de mensagens.

Responsabilidades:
  - baixar_audio() : obtém o arquivo de áudio da mensagem via mediaUrl e
                     salva como .ogg em workspace/temp/ para o pipeline consumir.
  - enviar_mensagem(): envia a resposta em texto ao ouvinte após o processamento.

Variáveis de ambiente necessárias (ver .env.example):
  WAHA_URL     : URL base do servidor WAHA (ex: http://localhost:3001)
  WAHA_API_KEY : chave de autenticação (X-Api-Key)
  WAHA_SESSION : nome da sessão (ex: default)
"""

import os
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv()

WAHA_URL: str = os.getenv("WAHA_URL", "http://localhost:3001").rstrip("/")
WAHA_API_KEY: str = os.getenv("WAHA_API_KEY", "")
WAHA_SESSION: str = os.getenv("WAHA_SESSION", "default")
WEBHOOK_URL: str = os.getenv("WEBHOOK_URL", "http://servidor:8002/webhook")

TEMP_DIR: str = os.getenv(
    "TEMP_DIR",
    str(Path(__file__).parent.parent / "workspace" / "temp"),
)


def _headers() -> dict:
    return {"X-Api-Key": WAHA_API_KEY, "Content-Type": "application/json"}


def configurar_webhook() -> bool:
    """
    Configura o webhook no WAHA para a sessão atual.
    Chamado automaticamente no startup do servidor.
    """
    url = f"{WAHA_URL}/api/sessions/{WAHA_SESSION}"
    payload = {
        "config": {
            "webhooks": [
                {
                    "url": WEBHOOK_URL,
                    "events": ["message", "session.status"],
                }
            ]
        }
    }
    try:
        with httpx.Client(timeout=10) as client:
            response = client.put(url, json=payload, headers=_headers())
            response.raise_for_status()
        print(f"[WHATSAPP] Webhook configurado: {WEBHOOK_URL}")
        return True
    except Exception as e:
        print(f"[WHATSAPP] Falha ao configurar webhook: {e}")
        return False


def baixar_audio(payload: dict) -> str | None:
    """
    Baixa o arquivo de áudio de uma mensagem WAHA.

    WAHA fornece o mediaUrl no payload da mensagem para download direto.

    Args:
        payload : dicionário "payload" do webhook do WAHA.

    Retorna:
        str  : caminho absoluto do arquivo .ogg salvo.
        None : se o download falhar por qualquer motivo.
    """
    # WAHA NOWEB expõe a URL em media.url; versões antigas usavam mediaUrl
    media_info = payload.get("media") or {}
    media_url = media_info.get("url") or payload.get("mediaUrl", "")
    if not media_url:
        print("[WHATSAPP] Payload sem URL de mídia.")
        return None

    # O WAHA NOWEB coloca localhost:3000 na URL, mas dentro do Docker o
    # serviço é acessado pelo hostname do container (WAHA_URL).
    media_url = media_url.replace("http://localhost:3000", WAHA_URL)

    try:
        with httpx.Client(timeout=30) as client:
            response = client.get(
                media_url,
                headers={"X-Api-Key": WAHA_API_KEY},
            )
            response.raise_for_status()
    except Exception as e:
        print(f"[WHATSAPP] Erro ao baixar áudio do WAHA: {e}")
        return None

    audio_bytes = response.content
    msg_id = payload.get("id", str(int(time.time())))
    # Remove caracteres inválidos em nome de arquivo
    msg_id = "".join(c for c in msg_id if c.isalnum() or c in "-_")

    os.makedirs(TEMP_DIR, exist_ok=True)
    path_ogg = str(Path(TEMP_DIR) / f"{msg_id}.ogg")

    with open(path_ogg, "wb") as f:
        f.write(audio_bytes)

    print(f"[WHATSAPP] Audio salvo: {path_ogg} ({len(audio_bytes) / 1024:.1f} KB)")
    return path_ogg


def resolver_telefone(numero: str) -> str | None:
    """
    Converte LID para número de telefone real via API WAHA.

    Retorna o número no formato '5511...@c.us' ou None se não resolver.
    Se o número já estiver em formato @c.us, retorna como está.
    """
    if "@lid" not in numero:
        return numero
    lid = numero.split("@")[0]
    try:
        with httpx.Client(timeout=5) as client:
            response = client.get(
                f"{WAHA_URL}/api/{WAHA_SESSION}/lids/{lid}",
                headers=_headers(),
            )
            if response.status_code == 200:
                return response.json().get("phoneNumber")
    except Exception:
        pass
    return None


def enviar_mensagem(numero: str, texto: str) -> bool:
    """
    Envia uma mensagem de texto ao ouvinte via WAHA.

    Args:
        numero : número do destinatário no formato "5511999999999"
                 (sem @c.us, sem espaços).
        texto  : conteúdo da mensagem.

    Retorna:
        True se enviado com sucesso, False em caso de falha (erro já logado).
    """
    # WAHA usa o formato chatId = "número@c.us"
    chat_id = f"{numero}@c.us" if "@" not in numero else numero

    url = f"{WAHA_URL}/api/sendText"
    payload = {
        "session": WAHA_SESSION,
        "chatId": chat_id,
        "text": texto,
    }

    try:
        with httpx.Client(timeout=15) as client:
            response = client.post(url, json=payload, headers=_headers())
            response.raise_for_status()
        print(f"[WHATSAPP] Mensagem enviada para {numero}: \"{texto}\"")
        return True
    except Exception as e:
        print(f"[WHATSAPP] Falha ao enviar mensagem para {numero}: {e}")
        return False
