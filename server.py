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
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from core import config_radio, database, queue_watcher, relatorio, whatsapp
from core.pipeline import processar_pedido

app = FastAPI(title="Agente Virtual Musical", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000",
                   "http://localhost:3001", "http://localhost:3002",
                   "http://localhost:3003", "http://localhost:3004"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

# Cache de IDs de mensagens já processadas (evita duplicatas do WAHA NOWEB)
_mensagens_processadas: set[str] = set()

# Número do dono da rádio para receber o relatório semanal
NUMERO_DONO: str = os.getenv("NUMERO_DONO", "")


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def startup() -> None:
    database.init_db()
    queue_watcher.start()
    asyncio.create_task(_indexar_biblioteca_async())
    asyncio.create_task(_configurar_webhook_com_retry())
    if NUMERO_DONO:
        asyncio.create_task(_loop_relatorio_semanal())
        print(f"[SERVER] Relatorio semanal ativado para: {NUMERO_DONO}")
    print("[SERVER] Pronto. Aguardando mensagens do WhatsApp...")


async def _indexar_biblioteca_async() -> None:
    """Indexa a biblioteca musical em background para não atrasar o startup."""
    await asyncio.to_thread(database.indexar_biblioteca)


async def _loop_relatorio_semanal() -> None:
    """Envia o relatório semanal toda segunda-feira às 09h."""
    from datetime import datetime, timedelta
    while True:
        agora = datetime.now()
        dias_ate_segunda = (7 - agora.weekday()) % 7
        if dias_ate_segunda == 0 and agora.hour < 9:
            proxima = agora.replace(hour=9, minute=0, second=0, microsecond=0)
        else:
            proxima = (agora + timedelta(days=max(dias_ate_segunda, 1))).replace(
                hour=9, minute=0, second=0, microsecond=0
            )
        segundos = (proxima - agora).total_seconds()
        print(f"[RELATORIO] Proximo relatorio em {segundos / 3600:.1f}h ({proxima.strftime('%d/%m %H:%M')})")
        await asyncio.sleep(segundos)
        try:
            texto = await asyncio.to_thread(relatorio.formatar_relatorio_semanal)
            await asyncio.to_thread(lambda: whatsapp.enviar_mensagem(NUMERO_DONO, texto))
            print("[RELATORIO] Relatorio semanal enviado.")
        except Exception as e:
            print(f"[RELATORIO] Erro ao enviar relatorio: {e}")


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
# Configuração da rádio
# ---------------------------------------------------------------------------

@app.get("/config")
async def get_config():
    """Retorna todas as configurações da rádio."""
    return await asyncio.to_thread(config_radio.get_all_config)


@app.put("/config")
async def put_config(request: Request):
    """
    Atualiza uma ou mais configurações da rádio.

    Body: JSON com chave → valor (ex: {"nome_radio": "Radio Classicos FM"})
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"status": "invalid_payload"}, status_code=400)

    if not isinstance(body, dict):
        return JSONResponse({"status": "body deve ser um objeto JSON"}, status_code=400)

    await asyncio.to_thread(
        lambda: [config_radio.set_config(str(k), str(v)) for k, v in body.items()]
    )
    return {"status": "updated", "keys": list(body.keys())}


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------

@app.get("/analytics")
async def get_analytics():
    """Retorna todos os dados analíticos da rádio para o dashboard."""
    (
        top_all, top_week, tendencia, picos, heatmap,
        taxa, ouvintes, ddd, artistas,
    ) = await asyncio.gather(
        asyncio.to_thread(lambda: relatorio.top_musicas_all_time(10)),
        asyncio.to_thread(relatorio.top_musicas_semana),
        asyncio.to_thread(lambda: relatorio.tendencia_musicas(5)),
        asyncio.to_thread(relatorio.pico_por_dia_semana),
        asyncio.to_thread(relatorio.heatmap_pedidos),
        asyncio.to_thread(relatorio.taxa_atendimento),
        asyncio.to_thread(relatorio.ouvintes_engajados),
        asyncio.to_thread(relatorio.breakdown_ddd),
        asyncio.to_thread(lambda: relatorio.top_artistas(15)),
    )
    return {
        "top_musicas_all_time": top_all,
        "top_musicas_semana":   top_week,
        "tendencia_musicas":    tendencia,
        "pico_por_dia_semana":  picos,
        "heatmap_pedidos":      heatmap,
        "taxa_atendimento":     taxa,
        "ouvintes_engajados":   ouvintes,
        "breakdown_ddd":        ddd,
        "top_artistas":         artistas,
    }


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

    # Deduplica: WAHA NOWEB pode entregar o mesmo webhook mais de uma vez
    msg_id = msg.get("id", "")
    if msg_id and msg_id in _mensagens_processadas:
        return JSONResponse({"status": "duplicate"})
    if msg_id:
        _mensagens_processadas.add(msg_id)
        if len(_mensagens_processadas) > 500:  # evita crescimento ilimitado
            _mensagens_processadas.clear()

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

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=8080)
