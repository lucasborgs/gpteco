"""
core/audio_mixer.py

Etapa 5 do pipeline: Transição Suave (MIXER).

Comportamento de timing:
  - Se duração da voz > 5s: a música entra 5 segundos antes do fim da voz,
    começando silenciosa e aumentando gradualmente até o volume cheio
    exatamente quando a voz termina. Depois disso, a música continua normalmente.
  - Se duração da voz <= 5s: a música começa junto com a voz e faz o
    fade_in durante toda a duração da voz.

Dependência externa: ffmpeg deve estar instalado e no PATH do sistema.
"""

import os
from pydub import AudioSegment

# --- Parâmetros de mixagem (ajustáveis) ---

# Volume alvo da voz normalizada (dBFS). -14 é broadcast standard.
VOZ_TARGET_DBFS: float = -14.0

# Janela de entrada da música antes do fim da voz, em ms.
# A música sobe de silêncio até volume cheio nesse período.
JANELA_ENTRADA_MS: int = 3_000

# Formato de saída unificado — deve coincidir com o que o downloader.py produz.
# Voz do WhatsApp chega tipicamente em 48000 Hz mono; música do acervo em 44100 Hz estéreo.
# pydub não faz resample automático no overlay(), então normalizamos explicitamente.
SAMPLE_RATE: int = 44100   # Hz
CHANNELS: int = 2          # Estéreo

# Teto de tamanho do arquivo de música aceito na mixagem.
# pydub carrega o áudio inteiro (descomprimido) na RAM e cria cópias durante o
# overlay/export; um arquivo longo (mix/vídeo de horas) estoura a memória (OOM).
# 35 MB ≈ ~24 min a 192 kbps — cobre faixas longas legítimas e barra mixes/vídeos.
MAX_MUSICA_BYTES: int = 35 * 1024 * 1024


def _normalizar_voz(voz: AudioSegment, target_dbfs: float = VOZ_TARGET_DBFS) -> AudioSegment:
    """
    Normaliza o volume da voz para o target_dbfs especificado.
    Usa a diferença entre o volume atual e o alvo para aplicar o ganho correto.
    Se a voz for silêncio total (dBFS = -inf), retorna sem alteração.
    """
    import math
    if math.isinf(voz.dBFS):
        print("[MIXER] Aviso: voz com silêncio total (dBFS = -inf) — normalização ignorada.")
        return voz
    diferenca = target_dbfs - voz.dBFS
    return voz.apply_gain(diferenca)


def mixar(path_voz: str, path_musica: str, path_saida: str) -> str:
    """
    Realiza a transição suave entre a voz do ouvinte e a música pedida.

    A música entra nos últimos 5 segundos da voz com fade_in gradual,
    atingindo volume cheio no exato momento em que a voz termina.
    Para vozes com <= 5s, a música começa junto desde o início.

    Args:
        path_voz    : caminho do arquivo de voz do ouvinte (.ogg).
        path_musica : caminho do arquivo de música do acervo (.mp3).
        path_saida  : caminho do arquivo de saída mixado (.mp3).

    Retorna:
        str : caminho absoluto do arquivo mixado gerado.

    Raises:
        FileNotFoundError : se voz ou música não existirem.
    """
    # --- Validação de entrada ---
    if not os.path.isfile(path_voz):
        raise FileNotFoundError(f"Arquivo de voz não encontrado: {path_voz}")
    if not os.path.isfile(path_musica):
        raise FileNotFoundError(f"Arquivo de música não encontrado: {path_musica}")

    # --- Guarda anti-OOM: recusa arquivos grandes demais ANTES de carregar na RAM ---
    tam_musica = os.path.getsize(path_musica)
    if tam_musica > MAX_MUSICA_BYTES:
        raise ValueError(
            f"Música grande demais para mixar com segurança: "
            f"{tam_musica / (1024 * 1024):.0f} MB "
            f"(limite {MAX_MUSICA_BYTES // (1024 * 1024)} MB). "
            f"Provavelmente é um mix/vídeo longo, não a faixa pedida: {path_musica}"
        )

    os.makedirs(os.path.dirname(os.path.abspath(path_saida)), exist_ok=True)

    print(f"[MIXER] Carregando voz:   {path_voz}")
    print(f"[MIXER] Carregando música: {path_musica}")

    # --- 1. Carrega os áudios ---
    voz = AudioSegment.from_file(path_voz)
    musica = AudioSegment.from_file(path_musica)

    # --- 2. Normaliza formato de áudio (sample rate + canais) ---
    # Deve acontecer antes de qualquer outra operação para garantir que
    # o overlay() opere sobre streams idênticos. Sem isso, pydub mistura
    # frames incompatíveis silenciosamente (timing errado, artefatos de pitch).
    if voz.frame_rate != SAMPLE_RATE:
        print(f"[MIXER] Resample voz: {voz.frame_rate} Hz → {SAMPLE_RATE} Hz")
        voz = voz.set_frame_rate(SAMPLE_RATE)
    if voz.channels != CHANNELS:
        print(f"[MIXER] Canais voz: {voz.channels} → {CHANNELS} (estéreo)")
        voz = voz.set_channels(CHANNELS)
    if musica.frame_rate != SAMPLE_RATE:
        print(f"[MIXER] Resample música: {musica.frame_rate} Hz → {SAMPLE_RATE} Hz")
        musica = musica.set_frame_rate(SAMPLE_RATE)
    if musica.channels != CHANNELS:
        print(f"[MIXER] Canais música: {musica.channels} → {CHANNELS} (estéreo)")
        musica = musica.set_channels(CHANNELS)

    # --- 3. Normaliza a voz ---
    print(f"[MIXER] Volume original da voz: {voz.dBFS:.1f} dBFS → alvo: {VOZ_TARGET_DBFS} dBFS")
    voz = _normalizar_voz(voz)
    print(f"[MIXER] Voz normalizada: {voz.dBFS:.1f} dBFS")

    # --- 4. Calcula o ponto de entrada da música ---
    duracao_voz_ms = len(voz)

    if duracao_voz_ms <= JANELA_ENTRADA_MS:
        # Voz curta: música começa junto e faz fade durante toda a voz
        inicio_musica_ms = 0
        fade_duration_ms = duracao_voz_ms
        print(f"[MIXER] Voz curta ({duracao_voz_ms / 1000:.1f}s): música começa junto com fade de {fade_duration_ms / 1000:.1f}s")
    else:
        # Música entra 5s antes do fim da voz
        inicio_musica_ms = duracao_voz_ms - JANELA_ENTRADA_MS
        fade_duration_ms = JANELA_ENTRADA_MS
        print(f"[MIXER] Música entra em {inicio_musica_ms / 1000:.1f}s ({JANELA_ENTRADA_MS // 1000}s antes do fim da voz)")

    # --- 5. Aplica fade_in na música ---
    # A música sobe de silêncio absoluto até volume cheio em fade_duration_ms.
    # Isso significa que no momento em que a voz termina, a música já está
    # em volume cheio e continua normalmente pelo resto da faixa.
    musica_com_fade = musica.fade_in(fade_duration_ms)

    # --- 6. Sobreposição: overlay da música sobre a voz com offset ---
    # O pydub limita o resultado ao comprimento da base (voz).
    # Para que a música continue após o fim da voz, estendemos a voz
    # com silêncio até cobrir toda a duração da música.
    total_ms = inicio_musica_ms + len(musica)
    if total_ms > len(voz):
        silencio = AudioSegment.silent(
            duration=total_ms - len(voz),
            frame_rate=SAMPLE_RATE,
        ).set_channels(CHANNELS)
        voz = voz + silencio

    print("[MIXER] Aplicando overlay (música sobre voz)...")
    mixado = voz.overlay(musica_com_fade, position=inicio_musica_ms)

    # --- 7. Exporta o arquivo final ---
    print(f"[MIXER] Exportando mixagem para: {path_saida}")
    mixado.export(path_saida, format="mp3", bitrate="192k")

    tamanho_mb = os.path.getsize(path_saida) / (1024 * 1024)
    duracao_s = len(mixado) / 1000
    print(f"[MIXER] Arquivo gerado: {tamanho_mb:.2f} MB | {duracao_s:.1f}s")

    return os.path.abspath(path_saida)
