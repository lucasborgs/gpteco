"""
core/queue_watcher.py

Watcher de fila FIFO para pedidos de ouvintes no ZaraRadio.

Problema resolvido:
    O ZaraRadio v1.6.2 não permite configurar modo de reprodução ou
    "deletar após tocar" por pasta — qualquer ajuste se aplica a todas.
    Este módulo resolve isso mantendo a lógica de fila externamente:

      1. Apenas UM arquivo existe em fila_zara/ de cada vez.
      2. O ZaraRadio toca esse arquivo (modo aleatório é indiferente com 1 arquivo).
      3. Detecta o fim da reprodução via CurrentSong.txt (atualizado pelo ZaraRadio
         a cada troca de faixa).
      4. Remove o arquivo reproduzido e promove o próximo de queue_pedidos/.

Detecção de reprodução:
    O watcher compara o conteúdo anterior com o atual do CurrentSong.txt.
    Se o nome do arquivo em fila_zara aparecia no conteúdo anterior e não
    aparece mais, o pedido foi reproduzido e pode ser removido.

Configuração via .env:
    QUEUE_DIR          — pasta da fila real (não monitorada pelo ZaraRadio)
    FILA_ZARA_DIR      — pasta monitorada pelo ZaraRadio (sempre 0–1 arquivo)
    CURRENT_SONG_DIR   — pasta onde o ZaraRadio grava CurrentSong.txt
    WATCHER_POLL_INTERVAL — intervalo de polling em segundos (padrão: 2)
"""

import os
import shutil
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

# Diretório onde o ZaraRadio grava CurrentSong.txt
# No Windows: C:\Users\user  →  montado no container como /app/workspace/current_song
_CURRENT_SONG_DIR: str = os.getenv(
    "CURRENT_SONG_DIR",
    str(Path(__file__).parent.parent / "workspace" / "current_song"),
)
CURRENT_SONG_PATH: str = str(Path(_CURRENT_SONG_DIR) / "CurrentSong.txt")

POLL_INTERVAL: int = int(os.getenv("WATCHER_POLL_INTERVAL", "2"))

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
    print(f"[WATCHER]   CurrentSong : {CURRENT_SONG_PATH}")
    print(f"[WATCHER]   Polling     : {POLL_INTERVAL}s")


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
    prev_song = _ler_current_song()
    em_reproducao = False  # True quando o arquivo da fila aparece no CurrentSong.txt

    while True:
        time.sleep(POLL_INTERVAL)

        with _lock:
            current_song = _ler_current_song()
            arquivo_fila = _arquivo_em_fila()

            # Sem arquivo na fila: tenta promover o próximo
            if arquivo_fila is None:
                if _promover_proximo():
                    prev_song = current_song
                    em_reproducao = False
                continue

            # CurrentSong.txt não mudou: nada a fazer
            if current_song == prev_song:
                continue

            # CurrentSong.txt mudou — verifica se nosso arquivo está envolvido
            aparecia_antes = _nome_em_conteudo(arquivo_fila, prev_song)
            aparece_agora  = _nome_em_conteudo(arquivo_fila, current_song)

            if aparecia_antes:
                em_reproducao = True

            if em_reproducao and not aparece_agora:
                # Arquivo saiu do CurrentSong.txt → foi reproduzido
                _deletar(arquivo_fila)
                em_reproducao = False
                _promover_proximo()

            prev_song = current_song


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

def _ler_current_song() -> str:
    """Lê o conteúdo atual de CurrentSong.txt (tolerante a erros de I/O)."""
    try:
        return Path(CURRENT_SONG_PATH).read_text(encoding="utf-8", errors="ignore").strip()
    except Exception:
        return ""


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


def _nome_em_conteudo(path_arquivo: str, conteudo: str) -> bool:
    """Verifica se o nome (ou stem) do arquivo aparece no conteúdo do CurrentSong.txt."""
    if not conteudo or not path_arquivo:
        return False
    nome  = Path(path_arquivo).name.lower()
    stem  = Path(path_arquivo).stem.lower()
    lower = conteudo.lower()
    return nome in lower or stem in lower


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
