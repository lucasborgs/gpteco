"""
core/downloader.py

Etapa 4 do pipeline: Download Dinâmico.

Fluxo quando a música não existe no acervo local:
  1. Busca os primeiros resultados no YouTube via yt-dlp (query: "artista musica official audio").
  2. Tenta os resultados com duração plausível até um download funcionar.
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

# Limites anti-OOM: evita baixar mixes/vídeos/lives longos que estouram a RAM na mixagem.
MAX_DURACAO_S: int = 900                      # 15 min — acima disso não é a música pedida
MAX_FILESIZE_BYTES: int = 30 * 1024 * 1024    # 30 MB — rede de segurança no próprio download
SEARCH_N: int = 5                             # nº de resultados avaliados na busca


class _FalhaResultadosBloqueados(RuntimeError):
    """Indica que todos os candidatos falharam por indisponibilidade prevista."""


def _limpar_download_parcial(
    video_id: str,
    preservar: set[Path] | None = None,
) -> None:
    """Remove artefatos de uma tentativa de download que falhou."""
    preservar = preservar or set()
    for path in Path(TEMP_DIR).glob(f"{video_id}.*"):
        if path.resolve() in preservar:
            continue
        try:
            path.unlink()
        except OSError:
            # Um artefato que não possa ser removido não deve interromper os
            # candidatos seguintes nem colocar arquivos fora do escopo em risco.
            pass


def _deve_tentar_busca_alternativa(erro: Exception) -> bool:
    """Indica erros em que uma segunda busca costuma encontrar outro vídeo."""
    mensagem = str(erro).lower()
    return any(
        trecho in mensagem
        for trecho in (
            "403",
            "forbidden",
            "not available",
            "video unavailable",
            "unable to download video data",
        )
    )


def _sanitizar_nome(nome: str) -> str:
    """Remove caracteres inválidos para nomes de arquivo no Windows."""
    return re.sub(r'[\\/:*?"<>|]', "_", nome).strip()


def _baixar_youtube(query: str) -> str:
    """
    Busca no YouTube e baixa o melhor áudio de um resultado com duração
    plausível de música (<= MAX_DURACAO_S).

    Resultados longos (mixes, vídeos, lives) são ignorados: além de não serem
    a faixa pedida, o pydub carrega o áudio inteiro na RAM na mixagem e um
    arquivo de horas estoura a memória do container (OOM).

    Retorna:
        str : caminho do arquivo baixado (extensão variável: webm, m4a, opus...).

    Raises:
        RuntimeError : se nenhum resultado adequado for encontrado ou o download falhar.
    """
    os.makedirs(TEMP_DIR, exist_ok=True)

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": os.path.join(TEMP_DIR, "%(id)s.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "socket_timeout": 30,                # segundos — evita hang indefinido
        "nopart": True,                      # evita .part → rename (falha em volumes Windows)
        "max_filesize": MAX_FILESIZE_BYTES,  # aborta o download se o arquivo passar do teto
    }

    print(f"[DOWNLOADER] Buscando no YouTube: '{query}'")

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        # Fase 1 — coleta metadados dos primeiros resultados SEM baixar.
        busca = ydl.extract_info(f"ytsearch{SEARCH_N}:{query}", download=False)
        entries = [e for e in ((busca or {}).get("entries") or []) if e]

        if not entries:
            raise RuntimeError(f"Nenhum resultado encontrado no YouTube para: '{query}'")

        candidatos = [
            e for e in entries
            if e.get("id") and 0 < (e.get("duration") or 0) <= MAX_DURACAO_S
        ]
        if not candidatos:
            duracoes = [e.get("duration") for e in entries]
            raise RuntimeError(
                f"Nenhum resultado com duração <= {MAX_DURACAO_S // 60} min para '{query}' "
                f"(durações encontradas, em s: {duracoes})"
            )

        falhas: list[str] = []
        falhas_previstas: list[bool] = []
        for candidato in candidatos:
            video_id = candidato["id"]
            duracao = int(candidato.get("duration") or 0)
            arquivos_antes = {
                path.resolve() for path in Path(TEMP_DIR).glob(f"{video_id}.*")
            }
            try:
                # Fase 2 — tenta cada resultado até encontrar um que possa ser baixado.
                info = ydl.extract_info(
                    f"https://www.youtube.com/watch?v={video_id}", download=True
                )
                ext = info.get("ext", "webm")
                path_baixado = os.path.join(TEMP_DIR, f"{video_id}.{ext}")

                if not os.path.isfile(path_baixado):
                    raise RuntimeError(
                        f"Arquivo baixado não encontrado (possível corte por tamanho): {path_baixado}"
                    )

                titulo = info.get("title", query)
                print(f"[DOWNLOADER] Baixado: '{titulo}' ({duracao // 60}min{duracao % 60:02d}s)")
                return path_baixado
            except Exception as erro:
                falhas.append(f"{video_id}: {erro}")
                falhas_previstas.append(_deve_tentar_busca_alternativa(erro))
                _limpar_download_parcial(video_id, preservar=arquivos_antes)
                print(
                    f"[DOWNLOADER] Falha no resultado {video_id}: {erro} — "
                    "tentando o próximo resultado..."
                )

        resumo = " | ".join(falhas)
        if falhas_previstas and all(falhas_previstas):
            raise _FalhaResultadosBloqueados(
                f"Todos os resultados estavam bloqueados ou indisponíveis para '{query}': {resumo}"
            )
        raise RuntimeError(f"Todos os resultados falharam para '{query}': {resumo}")


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

    # Valida que o arquivo foi gerado com conteúdo real
    tamanho = os.path.getsize(path_saida) if os.path.isfile(path_saida) else 0
    if tamanho == 0:
        if os.path.isfile(path_saida):
            os.remove(path_saida)
        raise RuntimeError(
            f"ffmpeg retornou código 0 mas gerou arquivo vazio: {os.path.basename(path_saida)}"
        )

    print(f"[DOWNLOADER] ffmpeg concluído: {os.path.basename(path_saida)} ({tamanho / 1024:.0f} KB)")


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
    try:
        path_temp = _baixar_youtube(query)
    except _FalhaResultadosBloqueados:
        query_fallback = f"{artista} {musica} lyrics"
        print(f"[DOWNLOADER] Resultado bloqueado/indisponível — tentando fallback: '{query_fallback}'")
        path_temp = _baixar_youtube(query_fallback)

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
