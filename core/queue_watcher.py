"""
core/queue_watcher.py

Watcher de fila FIFO para pedidos de ouvintes no ZaraRadio.

Problema resolvido:
    O ZaraRadio v1.6.2 não permite configurar modo de reprodução ou
    "deletar após tocar" por pasta — qualquer ajuste se aplica a todas.
    Este módulo resolve isso mantendo a lógica de fila externamente:

      1. Apenas UM arquivo existe em fila_zara/ de cada vez.
      2. O ZaraRadio toca esse arquivo (modo aleatório é indiferente com 1 arquivo).
      3. Detecta o fim da reprodução por tempo: compara a idade do arquivo em
         fila_zara/ com sua duração (via ffprobe) + buffer de segurança.
      4. Remove o arquivo reproduzido e promove o próximo de queue_pedidos/.

Detecção de reprodução:
    O ZaraRadio monitora fila_zara/ e começa a tocar em poucos segundos após
    o arquivo chegar. Portanto: idade_do_arquivo ≈ tempo_reproduzido.
    Quando idade > duração + PLAYBACK_BUFFER_S, o pedido foi reproduzido.

Configuração via .env:
    QUEUE_DIR             — pasta da fila real (não monitorada pelo ZaraRadio)
    FILA_ZARA_DIR         — pasta monitorada pelo ZaraRadio (sempre 0–1 arquivo)
    WATCHER_POLL_INTERVAL — intervalo de polling em segundos (padrão: 2)
    WATCHER_PLAYBACK_BUFFER — segundos extras após fim estimado antes de remover (padrão: 30)
"""

import json
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuração via .env
# ---------------------------------------------------------------------------

QUEUE_DIR: str = os.getenv(
    "QUEUE_DIR",
    str(Path(__file__).parent.parent / "workspace" / "queue_pedidos"),
)

FILA_ZARA_DIR: str = os.getenv(
    "FILA_ZARA_DIR",
    str(Path(__file__).parent.parent / "workspace" / "fila_zara"),
)


POLL_INTERVAL: int = int(os.getenv("WATCHER_POLL_INTERVAL", "2"))

# Segundos extras de buffer após o fim estimado antes de forçar remoção
PLAYBACK_BUFFER_S: int = int(os.getenv("WATCHER_PLAYBACK_BUFFER", "30"))

# Lock protege fila_zara e queue_pedidos contra acesso simultâneo do watcher e do pipeline
_lock = threading.Lock()


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

def start() -> None:
    """Inicia o watcher em thread daemon (não bloqueia o processo principal)."""
    os.makedirs(QUEUE_DIR, exist_ok=True)
    os.makedirs(FILA_ZARA_DIR, exist_ok=True)

    # Garante que fila_zara começa com no máximo 1 arquivo
    with _lock:
        _equilibrar_fila()

    t = threading.Thread(target=_loop, name="queue-watcher", daemon=True)
    t.start()
    print("[WATCHER] Iniciado.")
    print(f"[WATCHER]   Queue       : {QUEUE_DIR}")
    print(f"[WATCHER]   Fila Zara   : {FILA_ZARA_DIR}")
    print(f"[WATCHER]   Polling     : {POLL_INTERVAL}s")
    print(f"[WATCHER]   Buffer      : {PLAYBACK_BUFFER_S}s")


def enfileirar(path_audio: str) -> str:
    """
    Recebe um arquivo processado pelo pipeline e o coloca na posição correta:

    - Fila vazia  → move para fila_zara/ (reprodução imediata).
    - Fila ocupada → move para queue_pedidos/ (aguarda a vez).

    Retorna o path final onde o arquivo foi salvo.
    """
    with _lock:
        nome = Path(path_audio).name
        arquivo_atual = _arquivo_em_fila()

        if arquivo_atual is None:
            destino = str(Path(FILA_ZARA_DIR) / nome)
            shutil.move(path_audio, destino)
            print(f"[WATCHER] Fila vazia → promovido direto: {nome}")
            return destino

        destino = str(Path(QUEUE_DIR) / nome)
        shutil.move(path_audio, destino)
        posicao = len(list(Path(QUEUE_DIR).glob("*.mp3")))
        print(f"[WATCHER] Enfileirado (posição {posicao}): {nome}")
        return destino


# ---------------------------------------------------------------------------
# Loop de monitoramento
# ---------------------------------------------------------------------------

def _loop() -> None:
    # Cache de duração por path para evitar múltiplas chamadas ao ffprobe
    _duracao_cache: dict[str, float] = {}

    while True:
        time.sleep(POLL_INTERVAL)

        with _lock:
            arquivo_fila = _arquivo_em_fila()

            if arquivo_fila is None:
                _duracao_cache.clear()
                _promover_proximo()
                continue

            # Obtém (ou lê do cache) a duração do arquivo atual
            if arquivo_fila not in _duracao_cache:
                d = _get_duracao_segundos(arquivo_fila)
                if d is not None:
                    _duracao_cache[arquivo_fila] = d

            duracao_s = _duracao_cache.get(arquivo_fila)
            if duracao_s is None:
                # Sem duração não conseguimos estimar — aguarda próximo ciclo
                continue

            # Tempo que o arquivo já está em fila_zara.
            # O ZaraRadio detecta o arquivo e começa a tocar em poucos segundos após a chegada.
            # Portanto: idade_do_arquivo ≈ tempo_reproduzido + pequeno delay de pick-up.
            idade_s = time.time() - os.path.getmtime(arquivo_fila)

            if idade_s > duracao_s + PLAYBACK_BUFFER_S:
                print(
                    f"[WATCHER] Reprodução concluída ({idade_s:.0f}s no disco > "
                    f"{duracao_s:.0f}s duração + {PLAYBACK_BUFFER_S}s buffer) → removendo."
                )
                _duracao_cache.pop(arquivo_fila, None)
                _deletar(arquivo_fila)
                _promover_proximo()


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

def _get_duracao_segundos(path: str) -> float | None:
    """Retorna a duração do arquivo MP3 em segundos via ffprobe. Retorna None em caso de erro."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", path],
            capture_output=True, text=True, timeout=10,
        )
        data = json.loads(result.stdout)
        return float(data["format"]["duration"])
    except Exception as e:
        print(f"[WATCHER] Não foi possível obter duração de {path}: {e}")
        return None



def _arquivo_em_fila() -> str | None:
    """Retorna o path do único arquivo mp3 em fila_zara/, ou None se vazia."""
    try:
        arquivos = sorted(Path(FILA_ZARA_DIR).glob("*.mp3"))
        return str(arquivos[0]) if arquivos else None
    except Exception:
        return None


def _proximo_da_queue() -> str | None:
    """Retorna o path do próximo mp3 em queue_pedidos/ (ordenado por nome = FIFO por timestamp)."""
    try:
        arquivos = sorted(Path(QUEUE_DIR).glob("*.mp3"))
        return str(arquivos[0]) if arquivos else None
    except Exception:
        return None


def _promover_proximo() -> str | None:
    """Move o arquivo mais antigo de queue_pedidos/ para fila_zara/. Retorna o novo path ou None."""
    proximo = _proximo_da_queue()
    if not proximo:
        return None
    nome = Path(proximo).name
    destino = str(Path(FILA_ZARA_DIR) / nome)
    shutil.move(proximo, destino)
    print(f"[WATCHER] Promovido para fila_zara: {nome}")
    return destino



def _deletar(path: str) -> None:
    try:
        os.remove(path)
        print(f"[WATCHER] Removido após reprodução: {Path(path).name}")
    except Exception as e:
        print(f"[WATCHER] Erro ao remover {path}: {e}")


def _equilibrar_fila() -> None:
    """
    Chamado uma vez no startup.
    Se fila_zara/ estiver vazia e houver pedidos na queue, promove o primeiro.
    Se fila_zara/ tiver mais de 1 arquivo (estado inválido), move os excedentes para queue.
    """
    arquivos_fila = sorted(Path(FILA_ZARA_DIR).glob("*.mp3"))

    if len(arquivos_fila) == 0:
        _promover_proximo()
    elif len(arquivos_fila) > 1:
        for excedente in arquivos_fila[1:]:
            destino = str(Path(QUEUE_DIR) / excedente.name)
            shutil.move(str(excedente), destino)
            print(f"[WATCHER] Excedente movido para queue: {excedente.name}")
