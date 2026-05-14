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
import shutil
import time
from collections import OrderedDict

import httpx

from dotenv import load_dotenv

load_dotenv()

from fastapi import BackgroundTasks, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from core import config_radio, curador, database, queue_watcher, relatorio, whatsapp
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

# Números com pipeline em andamento — bloqueia requisições concorrentes do mesmo ouvinte
# (segunda linha de defesa: dedup por msg_id pode falhar se o WAHA atribuir ids diferentes)
_numeros_em_processamento: set[str] = set()
_lock_processamento = asyncio.Lock()


async def _reservar_numero(numero: str) -> bool:
    """Reserva o número para processamento. Retorna False se já em uso."""
    async with _lock_processamento:
        if numero in _numeros_em_processamento:
            return False
        _numeros_em_processamento.add(numero)
        return True


async def _liberar_numero(numero: str) -> None:
    async with _lock_processamento:
        _numeros_em_processamento.discard(numero)


# ---------------------------------------------------------------------------
# Máquina de estados por ouvinte (em memória)
# ---------------------------------------------------------------------------
# Estados possíveis:
#   "aguardando_menu"   : menu foi enviado; aguardando resposta "1" ou "2"
#   "aguardando_pedido" : bot está esperando o nome da música (após "1" do menu
#                          ou após MSG_NAO_ID / MSG_NAO_REPERTORIO). Suprime o
#                          menu para evitar regressão da conversa.
#   "producao"          : ouvinte optou por falar com a produção; pipeline
#                          desativado até o timer expirar (sem chamada ao LLM)
# Ausência de entrada no dict = estado neutro (comportamento padrão).
_estados_ouvinte: dict[str, dict] = {}
_lock_estados = asyncio.Lock()

PRODUCAO_TIMEOUT_S: int = int(os.getenv("PRODUCAO_TIMEOUT_MIN", "30")) * 60
_AGUARDANDO_MENU_TIMEOUT_S: int = 5 * 60     # 5 min para responder o menu
_AGUARDANDO_PEDIDO_TIMEOUT_S: int = 5 * 60   # 5 min para mandar o nome da música

# --- Pílulas de curiosidade musical ---
PILULAS_ATIVADAS: bool = os.getenv("PILULAS_ATIVADAS", "true").lower() == "true"
_PILULA_DELAY_S: int = 2  # tempo entre MSG_SUCESSO e a pílula, para separação visual


async def _esta_em_producao(numero: str) -> bool:
    """Retorna True se o ouvinte está em modo produção e o timer ainda não expirou."""
    async with _lock_estados:
        estado = _estados_ouvinte.get(numero)
        if not estado or estado["modo"] != "producao":
            return False
        if time.time() > estado["expira_em"]:
            del _estados_ouvinte[numero]
            return False
        return True


async def _renovar_timer_producao(numero: str) -> None:
    """Estende o timer do modo produção a partir da última interação."""
    async with _lock_estados:
        if numero in _estados_ouvinte and _estados_ouvinte[numero]["modo"] == "producao":
            _estados_ouvinte[numero]["expira_em"] = time.time() + PRODUCAO_TIMEOUT_S


async def _ativar_modo_producao(numero: str) -> None:
    async with _lock_estados:
        _estados_ouvinte[numero] = {
            "modo": "producao",
            "expira_em": time.time() + PRODUCAO_TIMEOUT_S,
        }


async def _ativar_aguardando_menu(numero: str) -> None:
    async with _lock_estados:
        _estados_ouvinte[numero] = {
            "modo": "aguardando_menu",
            "expira_em": time.time() + _AGUARDANDO_MENU_TIMEOUT_S,
        }


async def _consumir_aguardando_menu(numero: str) -> bool:
    """Se o ouvinte está aguardando resposta do menu (e não expirou), limpa o
    estado e retorna True. Caso contrário, retorna False."""
    async with _lock_estados:
        estado = _estados_ouvinte.get(numero)
        if not estado or estado["modo"] != "aguardando_menu":
            return False
        if time.time() > estado["expira_em"]:
            del _estados_ouvinte[numero]
            return False
        del _estados_ouvinte[numero]
        return True


async def _ativar_aguardando_pedido(numero: str) -> None:
    """Marca o ouvinte como 'esperando o nome da música'. Renova o timer se
    já estiver nesse estado."""
    async with _lock_estados:
        _estados_ouvinte[numero] = {
            "modo": "aguardando_pedido",
            "expira_em": time.time() + _AGUARDANDO_PEDIDO_TIMEOUT_S,
        }


async def _esta_aguardando_pedido(numero: str) -> bool:
    """Retorna True se o ouvinte está em aguardando_pedido e não expirou.
    Não consome o estado (ele só sai por sucesso, novo pedido válido ou timer)."""
    async with _lock_estados:
        estado = _estados_ouvinte.get(numero)
        if not estado or estado["modo"] != "aguardando_pedido":
            return False
        if time.time() > estado["expira_em"]:
            del _estados_ouvinte[numero]
            return False
        return True


async def _limpar_estado(numero: str) -> None:
    async with _lock_estados:
        _estados_ouvinte.pop(numero, None)


# Números para alertas e relatório semanal
NUMERO_DONO: str = os.getenv("NUMERO_DONO", "")
NUMERO_DEV: str = os.getenv("NUMERO_DEV", "")

# Constantes WAHA (nível de módulo — usadas por health check e monitor)
WAHA_URL: str = os.getenv("WAHA_URL", "http://localhost:3001").rstrip("/")
WAHA_API_KEY: str = os.getenv("WAHA_API_KEY", "")
WAHA_SESSION: str = os.getenv("WAHA_SESSION", "default")


async def _enviar_alerta(texto: str) -> None:
    """Envia alerta via WhatsApp para o dono e o dev (best-effort)."""
    for numero in (NUMERO_DONO, NUMERO_DEV):
        if numero:
            try:
                await asyncio.to_thread(lambda n=numero: whatsapp.enviar_mensagem(n, texto))
            except Exception:
                pass


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


async def _verificar_status_sessao() -> str:
    """Consulta o status da sessão WAHA. Retorna string de status ou 'UNREACHABLE'."""
    try:
        url = f"{WAHA_URL}/api/sessions/{WAHA_SESSION}"
        headers = {"X-Api-Key": WAHA_API_KEY} if WAHA_API_KEY else {}
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, headers=headers)
        return resp.json().get("status", "UNKNOWN") if resp.status_code == 200 else "UNREACHABLE"
    except Exception:
        return "UNREACHABLE"


async def _loop_monitor_sessao() -> None:
    """
    Verifica a cada 5 minutos se a sessão WAHA está conectada.
    Se desconectada, tenta reconexão automática (até 3x).
    Alerta o dono apenas se a reconexão falhar.
    """
    INTERVALO_S = 300           # 5 minutos
    MAX_RECONEXAO = 3           # tentativas por incidente
    ESPERA_ENTRE_TENTATIVAS = 30
    ESPERA_POS_RESTART = 15
    ja_alertou = False

    await asyncio.sleep(30)  # Aguarda o WAHA inicializar antes do primeiro check

    while True:
        try:
            status = await _verificar_status_sessao()

            if status not in ("WORKING", "CONNECTED"):
                print(f"[MONITOR] Sessão WAHA com status '{status}' — tentando reconexão automática...")

                reconectou = False
                for tentativa in range(1, MAX_RECONEXAO + 1):
                    print(f"[MONITOR] Tentativa de reconexão {tentativa}/{MAX_RECONEXAO}...")
                    try:
                        headers = {"X-Api-Key": WAHA_API_KEY} if WAHA_API_KEY else {}
                        async with httpx.AsyncClient(timeout=15) as client:
                            resp = await client.put(
                                f"{WAHA_URL}/api/sessions/{WAHA_SESSION}/restart",
                                headers=headers,
                            )
                        print(f"[MONITOR] Restart API retornou HTTP {resp.status_code}")
                    except Exception as e:
                        print(f"[MONITOR] Erro ao chamar restart: {e}")

                    await asyncio.sleep(ESPERA_POS_RESTART)
                    novo_status = await _verificar_status_sessao()

                    if novo_status in ("WORKING", "CONNECTED"):
                        print(f"[MONITOR] Reconexão bem-sucedida na tentativa {tentativa}!")
                        reconectou = True
                        break

                    if tentativa < MAX_RECONEXAO:
                        await asyncio.sleep(ESPERA_ENTRE_TENTATIVAS)

                if reconectou:
                    if ja_alertou:
                        await _enviar_alerta("✅ Sessão do WhatsApp reconectada automaticamente.")
                    ja_alertou = False
                else:
                    print("[MONITOR] Todas as tentativas de reconexão falharam.")
                    if not ja_alertou:
                        await _enviar_alerta(
                            "⚠️ ALERTA: A sessão do WhatsApp está desconectada e a reconexão automática falhou. "
                            "Reconecte manualmente pelo painel WAHA."
                        )
                        ja_alertou = True
            else:
                if ja_alertou:
                    print("[MONITOR] Sessão WAHA reconectada.")
                    await _enviar_alerta("✅ Sessão do WhatsApp reconectada com sucesso.")
                    ja_alertou = False

        except Exception as e:
            print(f"[MONITOR] Erro ao verificar sessão WAHA: {e}")

        await asyncio.sleep(INTERVALO_S)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health")
@app.get("/")
async def health():
    checks: dict = {}
    overall_healthy = True

    # 1. WAHA session status
    try:
        waha_status = await _verificar_status_sessao()
        waha_ok = waha_status in ("WORKING", "CONNECTED")
        checks["waha"] = {"status": waha_status, "healthy": waha_ok}
        if not waha_ok:
            overall_healthy = False
    except Exception as e:
        checks["waha"] = {"status": "ERROR", "detail": str(e), "healthy": False}
        overall_healthy = False

    # 2. Database connectivity
    try:
        con = await asyncio.to_thread(database._get_connection)
        try:
            with con.cursor() as cur:
                cur.execute("SELECT 1")
            checks["database"] = {"status": "connected", "healthy": True}
        finally:
            con.close()
    except Exception as e:
        checks["database"] = {"status": "unreachable", "detail": str(e), "healthy": False}
        overall_healthy = False

    # 3. Queue watcher thread
    watcher_alive = queue_watcher.is_alive()
    checks["queue_watcher"] = {
        "status": "running" if watcher_alive else "dead",
        "healthy": watcher_alive,
    }
    if not watcher_alive:
        overall_healthy = False

    # 4. Disk space (soft warning — não causa 503)
    try:
        usage = shutil.disk_usage("/app/workspace")
        free_gb = usage.free / (1024 ** 3)
        total_gb = usage.total / (1024 ** 3)
        disk_ok = free_gb > 1.0
        checks["disk"] = {
            "free_gb": round(free_gb, 2),
            "total_gb": round(total_gb, 2),
            "healthy": disk_ok,
        }
    except Exception:
        checks["disk"] = {"status": "unknown", "healthy": True}

    status_code = 200 if overall_healthy else 503
    return JSONResponse(
        {
            "status": "healthy" if overall_healthy else "unhealthy",
            "servico": "Agente Virtual Musical",
            "checks": checks,
        },
        status_code=status_code,
    )


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

    # --- Modo produção: bloqueia processamento, renova timer, sem chamar LLM ---
    if await _esta_em_producao(numero):
        await _renovar_timer_producao(numero)
        print(f"[WEBHOOK] {numero} em modo produção — mensagem ignorada pelo bot.")
        return JSONResponse({"status": "production_mode"})

    # WAHA NOWEB não envia campo "type"; detectamos o tipo pelo conteúdo:
    #   - hasMedia=True + mimetype "audio/*" → mensagem de áudio (ptt/audio)
    #   - caso contrário → mensagem de texto (body)
    has_media = msg.get("hasMedia", False)
    mimetype = (msg.get("media") or {}).get("mimetype", "")

    # --- Áudio de voz ---
    if has_media and mimetype.startswith("audio/"):
        # Áudio invalida apenas o aguardando_menu (não é "1" nem "2");
        # preserva aguardando_pedido pois o áudio quase sempre é o pedido.
        await _consumir_aguardando_menu(numero)
        # Segunda linha de defesa: bloqueia pipelines concorrentes para o mesmo ouvinte
        if not await _reservar_numero(numero):
            print(f"[WEBHOOK] Ignorado: {numero} já está em processamento.")
            return JSONResponse({"status": "already_processing"})
        background_tasks.add_task(_pipeline_audio, numero, msg)

    # --- Mensagem de texto ---
    else:
        texto = (msg.get("body") or "").strip()
        if not texto:
            return JSONResponse({"status": "ignored"})

        # Resposta a um menu enviado anteriormente?
        if await _consumir_aguardando_menu(numero):
            escolha = texto.strip().lower().rstrip(".!,)")
            if escolha in ("1", "1️⃣", "música", "musica", "pedir música", "pedir musica"):
                await _ativar_aguardando_pedido(numero)
                background_tasks.add_task(
                    _enviar_resposta_menu, numero, config_radio.MSG_AGUARDANDO_PEDIDO
                )
                return JSONResponse({"status": "menu_pedido"})
            if escolha in ("2", "2️⃣", "produção", "producao", "falar com a produção", "falar com a producao"):
                await _ativar_modo_producao(numero)
                background_tasks.add_task(
                    _enviar_resposta_menu, numero, config_radio.MSG_PRODUCAO_ATIVADO
                )
                return JSONResponse({"status": "menu_producao"})
            # Qualquer outra coisa: assume que o ouvinte já mandou o pedido direto

        if not await _reservar_numero(numero):
            print(f"[WEBHOOK] Ignorado: {numero} já está em processamento.")
            return JSONResponse({"status": "already_processing"})
        background_tasks.add_task(_pipeline_texto, numero, texto)

    return JSONResponse({"status": "received"})


async def _enviar_resposta_menu(numero: str, mensagem: str) -> None:
    """Envia a resposta a uma escolha do menu (background task curta)."""
    await asyncio.to_thread(lambda: whatsapp.enviar_mensagem(numero, mensagem))


async def _aplicar_resultado_pipeline(
    numero: str, resultado: dict, was_aguardando_pedido: bool
) -> None:
    """
    Centraliza o envio da mensagem do pipeline e a transição de estado.

    Regras:
      - Se já estava em aguardando_pedido E o pipeline ia mostrar o menu:
          suprime o menu (sem mensagem) e renova o timer — evita regressão da
          conversa ("ouvinte já tinha optado por pedir música").
      - Pendência (MSG_CONFIRMACAO) não altera o estado em memória — o fluxo
          de pendência (DB) tem prioridade na próxima mensagem.
      - Sucesso → limpa qualquer estado.
      - mostrar_menu (sem aguardando_pedido prévio) → ativa aguardando_menu.
      - aguardando_pedido (do pipeline) ou ouvinte que já estava aguardando →
          ativa/renova aguardando_pedido.
    """
    mensagem = resultado.get("mensagem")
    mostrar_menu = resultado.get("mostrar_menu", False)
    deve_aguardar_pedido = resultado.get("aguardando_pedido", False)
    sucesso = resultado.get("sucesso", False)
    pendente = resultado.get("pendente", False)

    # Suprime menu para ouvinte que já estava aguardando o pedido
    if mostrar_menu and was_aguardando_pedido:
        await _ativar_aguardando_pedido(numero)  # renova timer
        print(f"[ESTADO] {numero}: menu suprimido (aguardando_pedido ativo).")
        return

    if mensagem:
        await asyncio.to_thread(
            lambda: whatsapp.enviar_mensagem(numero, mensagem)
        )

    if pendente:
        return  # pendência (DB) tem prioridade — não muda o estado em memória

    if sucesso:
        await _limpar_estado(numero)
        # Dispara pílula de curiosidade em background (não bloqueia)
        artista = resultado.get("artista")
        musica = resultado.get("musica")
        if artista and musica and resultado.get("is_pedido_explicito"):
            asyncio.create_task(_enviar_pilula_bg(numero, artista, musica))
    elif mostrar_menu:
        await _ativar_aguardando_menu(numero)
    elif deve_aguardar_pedido or was_aguardando_pedido:
        await _ativar_aguardando_pedido(numero)


async def _enviar_pilula_bg(numero: str, artista: str, musica: str) -> None:
    """
    Gera (ou busca em cache) e envia a pílula de curiosidade ao ouvinte.

    Falhas são silenciosas — a pílula é uma feature opcional e nunca pode
    afetar a entrega da música.

    Bloqueios:
      - PILULAS_ATIVADAS=false no .env
      - Número é o dono ou o dev (testes não devem ter ruído)
      - Pílula já foi enviada para esse ouvinte+música
      - Curador retorna None (modelo sem certeza, falha de API, etc.)
    """
    if not PILULAS_ATIVADAS:
        return
    if numero in (NUMERO_DONO, NUMERO_DEV):
        return

    try:
        # 1. Busca pílula em cache; gera se não existir
        cache = await asyncio.to_thread(
            lambda: database.buscar_pilula(artista, musica)
        )
        if cache:
            pilula_id, texto = cache
        else:
            texto = await asyncio.to_thread(
                lambda: curador.gerar_pilula(artista, musica)
            )
            if not texto:
                return  # modelo sem certeza ou falha
            pilula_id = await asyncio.to_thread(
                lambda: database.salvar_pilula(
                    artista, musica, texto, curador.PILULAS_MODELO
                )
            )

        # 2. Não repete pílula para o mesmo ouvinte+música
        ja_enviada = await asyncio.to_thread(
            lambda: database.verificar_pilula_enviada(numero, pilula_id)
        )
        if ja_enviada:
            return

        # 3. Aguarda alguns segundos para separar visualmente do MSG_SUCESSO
        await asyncio.sleep(_PILULA_DELAY_S)

        # 4. Envia e registra
        mensagem = f"{config_radio.MSG_PILULA_PREFIXO}{texto}"
        await asyncio.to_thread(
            lambda: whatsapp.enviar_mensagem(numero, mensagem)
        )
        await asyncio.to_thread(
            lambda: database.registrar_pilula_enviada(numero, pilula_id)
        )
    except Exception as e:
        print(f"[PILULA] Falha ao enviar pílula para {numero}: {e}")


# ---------------------------------------------------------------------------
# Background tasks (executadas em thread pool para não bloquear o event loop)
# ---------------------------------------------------------------------------

async def _resolver_telefone_bg(numero: str) -> None:
    """Resolve LID → telefone via API WAHA e grava no banco (background)."""
    if "@lid" not in numero:
        return
    telefone = await asyncio.to_thread(lambda: whatsapp.resolver_telefone(numero))
    if telefone:
        await asyncio.to_thread(lambda: database.atualizar_telefone(numero, telefone))


async def _pipeline_texto(numero: str, texto: str) -> None:
    """Processa pedido de texto — com detecção de pendência de confirmação."""
    try:
        was_aguardando_pedido = await _esta_aguardando_pedido(numero)
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

        await _aplicar_resultado_pipeline(numero, resultado, was_aguardando_pedido)

        await _resolver_telefone_bg(numero)
    finally:
        await _liberar_numero(numero)


async def _pipeline_audio(numero: str, msg: dict) -> None:
    """Baixa o áudio, processa o pedido e envia resposta ao ouvinte."""
    try:
        was_aguardando_pedido = await _esta_aguardando_pedido(numero)
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
            await _aplicar_resultado_pipeline(numero, resultado, was_aguardando_pedido)
        finally:
            if not resultado.get("pendente") and os.path.isfile(path_ogg):
                os.remove(path_ogg)
                print(f"[SERVER] Temp removido: {path_ogg}")

        await _resolver_telefone_bg(numero)
    finally:
        await _liberar_numero(numero)

if __name__ == '__main__':
    import uvicorn
    port = int(os.getenv("SERVER_PORT", "8002"))
    uvicorn.run(app, host='0.0.0.0', port=port)
