"""
server.py

Servidor webhook do Agente Virtual Musical.
Recebe eventos do WAHA (WhatsApp HTTP API), processa via pipeline
e responde ao ouvinte com a mensagem de resultado.

Fluxo por mensagem recebida:
  1. WAHA POST /webhook com o payload da mensagem
  2. Servidor valida e retorna 200 imediatamente (sem bloquear)
  3. Background task baixa áudio (se necessário) e chama processar_pedido()
  4. Resultado["mensagem"] é enviado de volta ao ouvinte via enviar_mensagem()

Payload do WAHA (evento "message"):
  {
    "event": "message",
    "session": "default",
    "me": {"id": "55...", "pushName": "Radio"},
    "payload": {
      "id": "msg_id",
      "timestamp": 1234567890,
      "from": "5511999999999@c.us",
      "fromMe": false,
      "to": "5511999999999@c.us",
      "body": "texto da mensagem",
      "hasMedia": false,
      "mediaUrl": null,
      "type": "text" | "ptt" | "audio" | "image" | ...
    }
  }

Iniciar em desenvolvimento:
    uvicorn server:app --host 0.0.0.0 --port 8000 --reload

Iniciar em produção (Windows):
    uvicorn server:app --host 0.0.0.0 --port 8000 --workers 1
"""

import asyncio
import os

from dotenv import load_dotenv

load_dotenv()

from fastapi import BackgroundTasks, FastAPI, Request
from fastapi.responses import JSONResponse

from core import database, whatsapp
from core.pipeline import processar_pedido

app = FastAPI(title="Agente Virtual Musical", version="1.0.0")


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def startup() -> None:
    database.init_db()
    asyncio.create_task(_configurar_webhook_com_retry())
    print("[SERVER] Pronto. Aguardando mensagens do WhatsApp...")


async def _configurar_webhook_com_retry() -> None:
    """Configura o webhook no WAHA com retries, aguardando o WAHA inicializar."""
    for tentativa in range(1, 13):  # até ~2 minutos
        await asyncio.sleep(10)
        try:
            sucesso = await asyncio.to_thread(whatsapp.configurar_webhook)
            if sucesso:
                return
        except Exception as e:
            print(f"[SERVER] Tentativa {tentativa}/12 de configurar webhook falhou: {e}")
    print("[SERVER] AVISO: Webhook nao configurado automaticamente. Configure manualmente.")


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/")
async def health():
    return {"status": "online", "servico": "Agente Virtual Musical"}


# ---------------------------------------------------------------------------
# Webhook principal
# ---------------------------------------------------------------------------

@app.post("/webhook")
async def webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Endpoint registrado no WAHA como destino de webhooks.

    Responde 200 imediatamente para evitar timeout do WAHA.
    O processamento real ocorre em background (thread separada via asyncio.to_thread).
    """
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"status": "invalid_payload"}, status_code=400)

    event = payload.get("event", "")

    # Filtra apenas eventos de mensagens
    if event != "message":
        return JSONResponse({"status": "ignored", "event": event})

    msg = payload.get("payload", {})

    # Ignora mensagens enviadas pelo próprio bot
    if msg.get("fromMe"):
        return JSONResponse({"status": "ignored"})

    # Mantém o JID completo como identificador único do ouvinte
    # WAHA NOWEB usa @lid em vez de @c.us — mantemos o JID inteiro para
    # garantir que enviar_mensagem use o chatId correto.
    from_jid = msg.get("from", "")
    numero = from_jid  # ex: "143890011172971@lid" ou "5511...@c.us"

    # Ignora grupos (@g.us)
    if "@g.us" in from_jid:
        return JSONResponse({"status": "ignored"})

    # WAHA NOWEB não envia campo "type"; detectamos o tipo pelo conteúdo:
    #   - hasMedia=True + mimetype "audio/*" → mensagem de áudio (ptt/audio)
    #   - caso contrário → mensagem de texto (body)
    has_media = msg.get("hasMedia", False)
    mimetype = (msg.get("media") or {}).get("mimetype", "")

    # --- Áudio de voz ---
    if has_media and mimetype.startswith("audio/"):
        background_tasks.add_task(_pipeline_audio, numero, msg)

    # --- Mensagem de texto ---
    else:
        texto = (msg.get("body") or "").strip()
        if not texto:
            return JSONResponse({"status": "ignored"})
        background_tasks.add_task(_pipeline_texto, numero, texto)

    return JSONResponse({"status": "received"})


# ---------------------------------------------------------------------------
# Background tasks (executadas em thread pool para não bloquear o event loop)
# ---------------------------------------------------------------------------

async def _pipeline_texto(numero: str, texto: str) -> None:
    """Processa pedido de texto e envia resposta ao ouvinte."""
    resultado = await asyncio.to_thread(
        lambda: processar_pedido(numero=numero, texto=texto)
    )
    if resultado["mensagem"]:
        await asyncio.to_thread(
            lambda: whatsapp.enviar_mensagem(numero, resultado["mensagem"])
        )


async def _pipeline_audio(numero: str, msg: dict) -> None:
    """Baixa o áudio, processa o pedido e envia resposta ao ouvinte."""
    # 1. Baixa o áudio via WAHA mediaUrl
    path_ogg = await asyncio.to_thread(lambda: whatsapp.baixar_audio(msg))

    if not path_ogg:
        await asyncio.to_thread(
            lambda: whatsapp.enviar_mensagem(
                numero,
                "Nao consegui processar o audio. Pode reenviar ou mandar um texto?",
            )
        )
        return

    # 2. Processa e responde; garante limpeza do .ogg temporario
    try:
        resultado = await asyncio.to_thread(
            lambda: processar_pedido(numero=numero, path_ogg=path_ogg)
        )
        if resultado["mensagem"]:
            await asyncio.to_thread(
                lambda: whatsapp.enviar_mensagem(numero, resultado["mensagem"])
            )
    finally:
        if os.path.isfile(path_ogg):
            os.remove(path_ogg)
            print(f"[SERVER] Temp removido: {path_ogg}")
