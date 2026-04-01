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
from collections import OrderedDict

from dotenv import load_dotenv

load_dotenv()

from fastapi import BackgroundTasks, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from core import database, queue_watcher, relatorio, whatsapp
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

# Cache LRU de IDs de mensagens já processadas (evita duplicatas do WAHA NOWEB)
_mensagens_processadas: OrderedDict[str, None] = OrderedDict()
_MAX_CACHE_MENSAGENS = 500

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
    asyncio.create_task(_loop_monitor_sessao())
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
        elif dias_ate_segunda == 0:
            # Hoje é segunda-feira mas já passou das 09h — próximo disparo é daqui a 7 dias
            proxima = (agora + timedelta(days=7)).replace(hour=9, minute=0, second=0, microsecond=0)
        else:
            proxima = (agora + timedelta(days=dias_ate_segunda)).replace(
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


async def _loop_monitor_sessao() -> None:
    """
    Verifica a cada 5 minutos se a sessão WAHA está conectada.
    Se desconectada, loga aviso e envia alerta via WhatsApp ao dono (se configurado).
    """
    import httpx
    WAHA_URL = os.getenv("WAHA_URL", "http://localhost:3001").rstrip("/")
    WAHA_API_KEY = os.getenv("WAHA_API_KEY", "")
    WAHA_SESSION = os.getenv("WAHA_SESSION", "default")
    INTERVALO_S = 300  # 5 minutos
    ja_alertou = False

    await asyncio.sleep(30)  # Aguarda o WAHA inicializar antes do primeiro check

    while True:
        try:
            url = f"{WAHA_URL}/api/sessions/{WAHA_SESSION}"
            headers = {"X-Api-Key": WAHA_API_KEY} if WAHA_API_KEY else {}
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(url, headers=headers)
            status = resp.json().get("status", "UNKNOWN") if resp.status_code == 200 else "UNREACHABLE"

            if status not in ("WORKING", "CONNECTED"):
                print(f"[MONITOR] ALERTA: Sessão WAHA com status '{status}' — WhatsApp desconectado!")
                if NUMERO_DONO and not ja_alertou:
                    await asyncio.to_thread(
                        lambda: whatsapp.enviar_mensagem(
                            NUMERO_DONO,
                            f"⚠️ ALERTA: A sessão do WhatsApp está '{status}'. Reconecte o QR code no painel WAHA."
                        )
                    )
                    ja_alertou = True
            else:
                if ja_alertou:
                    print("[MONITOR] Sessão WAHA reconectada.")
                    ja_alertou = False

        except Exception as e:
            print(f"[MONITOR] Erro ao verificar sessão WAHA: {e}")

        await asyncio.sleep(INTERVALO_S)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/")
async def health():
    return {"status": "online", "servico": "Agente Virtual Musical"}


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
        _mensagens_processadas[msg_id] = None
        while len(_mensagens_processadas) > _MAX_CACHE_MENSAGENS:
            _mensagens_processadas.popitem(last=False)  # remove o mais antigo

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
    """Processa pedido de texto — com detecção de pendência de confirmação."""
    pendencia = await asyncio.to_thread(lambda: database.buscar_pendencia(numero))

    def _notificar(msg: str) -> None:
        whatsapp.enviar_mensagem(numero, msg)

    if pendencia:
        path_ogg = pendencia["path_ogg"]
        if path_ogg == "__texto__":
            # Confirmação por texto: ouvinte responde "sim" ou digita nome correto
            if texto.strip().lower() in ("sim", "s", "yes"):
                # Usa artista/musica normalizados armazenados na pendência
                texto = f"{pendencia['musica_original']} {pendencia['artista_original']}"
            resultado = await asyncio.to_thread(
                lambda: processar_pedido(numero=numero, texto=texto, notificar=_notificar)
            )
        else:
            # Confirmação por áudio: usa o .ogg original salvo para a mixagem
            resultado = await asyncio.to_thread(
                lambda: processar_pedido(numero=numero, path_ogg=path_ogg, texto=texto, notificar=_notificar)
            )
        await asyncio.to_thread(lambda: database.remover_pendencia(numero))
        if path_ogg != "__texto__" and not resultado.get("pendente") and os.path.isfile(path_ogg):
            os.remove(path_ogg)
            print(f"[SERVER] Temp pendência removido: {path_ogg}")
    else:
        resultado = await asyncio.to_thread(
            lambda: processar_pedido(numero=numero, texto=texto, notificar=_notificar)
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

    # 2. Processa e responde.
    # Se pendente=True, o .ogg é mantido para ser usado na confirmação por texto.
    def _notificar(msg: str) -> None:
        whatsapp.enviar_mensagem(numero, msg)

    resultado = {"pendente": False, "mensagem": None}
    try:
        resultado = await asyncio.to_thread(
            lambda: processar_pedido(numero=numero, path_ogg=path_ogg, notificar=_notificar)
        )
        if resultado["mensagem"]:
            await asyncio.to_thread(
                lambda: whatsapp.enviar_mensagem(numero, resultado["mensagem"])
            )
    finally:
        if not resultado.get("pendente") and os.path.isfile(path_ogg):
            os.remove(path_ogg)
            print(f"[SERVER] Temp removido: {path_ogg}")

if __name__ == '__main__':
    import uvicorn
    port = int(os.getenv("SERVER_PORT", "8002"))
    uvicorn.run(app, host='0.0.0.0', port=port)
