"""
core/downloader.py

Etapa 4 do pipeline: Download Dinâmico.

Fluxo quando a música não existe no acervo local:
  1. Busca o primeiro resultado no YouTube via yt-dlp (query: "artista musica official audio").
  2. Baixa o melhor áudio disponível para a pasta temp.
  3. Processa com ffmpeg em um único passo:
       - Converte para .mp3 (192k, 44100 Hz)
       - Remove silêncios de início e fim (silenceremove)
       - Normaliza para -14 LUFS (loudnorm — padrão broadcast)
  4. Salva o .mp3 final em workspace/acervo_limpo.
  5. Remove o arquivo temporário.
  6. Registra o novo registro no DuckDB via database.py.

Dependências externas: yt-dlp e ffmpeg devem estar instalados e no PATH do sistema.
"""

import os
import re
import subprocess
from pathlib import Path

import yt_dlp

from core import database

# Diretórios (configuráveis via .env)
ACERVO_DIR: str = os.getenv(
    "ACERVO_DIR",
    str(Path(__file__).parent.parent / "workspace" / "acervo_limpo"),
)
TEMP_DIR: str = os.getenv(
    "TEMP_DIR",
    str(Path(__file__).parent.parent / "workspace" / "temp"),
)

# Parâmetros de normalização LUFS (EBU R128 / broadcast standard)
LUFS_TARGET: int = -14
LUFS_TRUE_PEAK: float = -1.5
LUFS_LRA: int = 11


def _sanitizar_nome(nome: str) -> str:
    """Remove caracteres inválidos para nomes de arquivo no Windows."""
    return re.sub(r'[\\/:*?"<>|]', "_", nome).strip()


def _baixar_youtube(query: str) -> str:
    """
    Busca o primeiro resultado no YouTube e baixa o melhor áudio disponível.

    Retorna:
        str : caminho do arquivo baixado (extensão variável: webm, m4a, opus...).

    Raises:
        RuntimeError : se nenhum resultado for encontrado ou o download falhar.
    """
    os.makedirs(TEMP_DIR, exist_ok=True)

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": os.path.join(TEMP_DIR, "%(id)s.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "socket_timeout": 30,   # segundos — evita hang indefinido
    }

    print(f"[DOWNLOADER] Buscando no YouTube: '{query}'")

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(f"ytsearch1:{query}", download=True)

        if not info or not info.get("entries"):
            raise RuntimeError(f"Nenhum resultado encontrado no YouTube para: '{query}'")

        video = info["entries"][0]
        video_id = video["id"]
        ext = video.get("ext", "webm")
        titulo = video.get("title", query)

    path_baixado = os.path.join(TEMP_DIR, f"{video_id}.{ext}")

    if not os.path.isfile(path_baixado):
        raise RuntimeError(f"Arquivo baixado não encontrado em: {path_baixado}")

    print(f"[DOWNLOADER] Baixado: '{titulo}'")
    return path_baixado


def _processar_ffmpeg(path_entrada: str, path_saida: str) -> None:
    """
    Processa o áudio com ffmpeg em um único passo:
      - Converte para mp3
      - Remove silêncios de início e fim
      - Normaliza para -14 LUFS

    Os dois filtros são encadeados via -af "filtro1,filtro2" para evitar
    reencoding intermediário e manter qualidade máxima.

    Raises:
        RuntimeError : se o ffmpeg retornar código de erro.
    """
    filtro_audio = (
        # 1. Remove silêncio no início (start_periods=1) e fim (stop_periods=-1)
        "silenceremove="
        "start_periods=1:start_silence=0.1:start_threshold=-50dB:"
        "stop_periods=-1:stop_silence=0.5:stop_threshold=-50dB,"
        # 2. Normaliza para -14 LUFS (single-pass)
        f"loudnorm=I={LUFS_TARGET}:TP={LUFS_TRUE_PEAK}:LRA={LUFS_LRA}"
    )

    comando = [
        "ffmpeg",
        "-y",                      # Sobrescreve sem confirmação
        "-i", path_entrada,
        "-af", filtro_audio,
        "-c:a", "libmp3lame",
        "-b:a", "192k",
        "-ar", "44100",
        path_saida,
    ]

    print(f"[DOWNLOADER] Convertendo + silenceremove + loudnorm {LUFS_TARGET} LUFS...")

    resultado = subprocess.run(comando, capture_output=True, text=True)

    if resultado.returncode != 0:
        raise RuntimeError(
            f"ffmpeg falhou (código {resultado.returncode}):\n{resultado.stderr[-500:]}"
        )

    print(f"[DOWNLOADER] ffmpeg concluído: {os.path.basename(path_saida)}")


def baixar(artista: str, musica: str) -> str:
    """
    Executa o pipeline completo: YouTube → temp → ffmpeg → acervo → DuckDB.

    Args:
        artista : nome do artista.
        musica  : título da música.

    Retorna:
        str : caminho absoluto do .mp3 salvo no acervo.

    Raises:
        RuntimeError : se o download ou processamento falhar.
    """
    os.makedirs(ACERVO_DIR, exist_ok=True)

    query = f"{artista} {musica} official audio"
    path_temp = _baixar_youtube(query)

    nome_arquivo = _sanitizar_nome(f"{artista} - {musica}") + ".mp3"
    path_final = os.path.join(ACERVO_DIR, nome_arquivo)

    try:
        _processar_ffmpeg(path_temp, path_final)
        database.inserir_musica(artista, musica, path_final)
        return path_final
    finally:
        # Limpa o arquivo temporário mesmo em caso de falha
        if os.path.isfile(path_temp):
            os.remove(path_temp)
            print(f"[DOWNLOADER] Temp removido: {os.path.basename(path_temp)}")
