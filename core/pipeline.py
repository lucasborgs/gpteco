"""
core/pipeline.py

Orquestrador principal do Agente Virtual Musical.

Ponto de entrada público:

    processar_pedido(numero, path_ogg?, texto?) -> dict

Regras de negócio aplicadas:
  - Suporta entrada de voz (.ogg) OU texto — nunca os dois ao mesmo tempo.
  - Cada número de telefone pode fazer apenas 1 pedido a cada 6 horas.
  - Se o áudio contiver mais de uma música, somente a primeira é considerada
    (regra aplicada no SYSTEM_PROMPT do LLM em intelligence.py).
  - Retorna sempre um dict com {"sucesso", "path_audio", "mensagem"} — nunca
    levanta exceção, para facilitar integração com a Evolution API.

Fluxo (quando autorizado):
    1. STT      : se path_ogg, transcreve → texto
    2. LLM      : extrai artista/música + valida is_flashback + is_apropriado
    3. Acervo   : busca música no DuckDB local
    4. Download : se não existir, baixa do YouTube e processa com ffmpeg
    5. Mixer    : sobrepõe voz + música com transição suave
    6. Entrega  : move .mp3 para a fila do ZaraRadio
    7. Registro : salva pedido em dim_pedidos (para cooldown futuro)
"""

import os
import re
import shutil
import time
from pathlib import Path

from core import audio_mixer, database, downloader, intelligence, queue_watcher, stt

# Diretórios (configuráveis via .env)
TEMP_DIR: str = os.getenv(
    "TEMP_DIR",
    str(Path(__file__).parent.parent / "workspace" / "temp"),
)
# Define como "true" no .env para desativar o cooldown durante testes
DISABLE_COOLDOWN: bool = os.getenv("DISABLE_COOLDOWN", "false").lower() == "true"

# Mensagens de resposta ao ouvinte
_MSG_SUCESSO       = "Obrigado pela sua indicação! {artista} - {musica} já está na fila."
_MSG_COOLDOWN      = "Você já fez um pedido nas últimas 6 horas. Tente novamente mais tarde!"
_MSG_INAPROPRIADO  = "Não foi possível atender esse pedido. Mande uma mensagem respeitosa!"
_MSG_NAO_FLASHBACK = "'{musica}' não está no repertório flashback da rádio. Que tal outro clássico?"
_MSG_NAO_ID        = "Não consegui identificar a música. Pode repetir o pedido?"
_MSG_ERRO          = "Ocorreu um erro ao processar seu pedido. Tente novamente em breve."


def processar_pedido(
    numero: str,
    path_ogg: str | None = None,
    texto: str | None = None,
) -> dict:
    """
    Executa o pipeline completo e retorna sempre um dict estruturado.

    Args:
        numero   : número de telefone do ouvinte (ex: "5511999999999").
        path_ogg : caminho do .ogg do WhatsApp (mutuamente exclusivo com texto).
        texto    : mensagem de texto do ouvinte (mutuamente exclusivo com path_ogg).

    Retorna:
        dict com as chaves:
          - "sucesso"    (bool)       : True se o .mp3 foi gerado e entregue.
          - "path_audio" (str | None) : path na fila_zara, ou None se reprovado/erro.
          - "mensagem"   (str)        : texto a ser enviado ao ouvinte via Evolution API.
    """
    # --- Validação de entrada ---
    if not path_ogg and not texto:
        return _resultado(False, None, _MSG_ERRO)
    if path_ogg and texto:
        return _resultado(False, None, _MSG_ERRO)
    if path_ogg and not os.path.isfile(path_ogg):
        return _resultado(False, None, _MSG_ERRO)

    os.makedirs(TEMP_DIR, exist_ok=True)

    _log_separador(f"Novo pedido de {numero}")

    # --- Regra 4: Rate limiting por número ---
    _log_etapa(0, "Verificação de cooldown")
    if not DISABLE_COOLDOWN and not database.verificar_cooldown(numero):
        return _resultado(False, None, _MSG_COOLDOWN)

    try:
        # --- Etapa 1: Transcrição STT (somente se for áudio) ---
        if path_ogg:
            _log_etapa(1, "Transcrição STT")
            texto = stt.transcrever(path_ogg)
        else:
            _log_etapa(1, "Entrada de texto — STT ignorado")
            print(f"[PIPELINE] Texto recebido: \"{texto}\"")

        # --- Etapa 2: Inteligência + Regras de Negócio ---
        _log_etapa(2, "Análise LLM")
        metadados = intelligence.analisar(texto)

        # Mensagem fora do escopo do bot — silêncio total (dono responde manualmente)
        if not metadados.is_pedido_musical:
            print("[PIPELINE] Não é pedido musical — ignorando silenciosamente.")
            return _resultado(False, None, None)

        if not metadados.musica or not metadados.artista:
            return _resultado(False, None, _MSG_NAO_ID)

        if not metadados.is_apropriado:
            return _resultado(False, None, _MSG_INAPROPRIADO)

        if not metadados.is_flashback:
            msg = _MSG_NAO_FLASHBACK.format(musica=metadados.musica)
            return _resultado(False, None, msg)

        # --- Etapa 3: Busca no Acervo Local (DuckDB) ---
        _log_etapa(3, "Busca no acervo local")
        file_path = database.buscar_musica(metadados.artista, metadados.musica)

        # --- Etapa 4: Download Dinâmico (somente se necessário) ---
        if file_path:
            _log_etapa(4, "Download ignorado — música já no acervo")
        else:
            _log_etapa(4, "Download dinâmico (YouTube)")
            file_path = downloader.baixar(metadados.artista, metadados.musica)

        # --- Etapa 5: Mixagem (somente se havia voz para misturar) ---
        _log_etapa(5, "Mixagem de áudio")
        nome_saida = _gerar_nome_arquivo(metadados.artista, metadados.musica)

        if path_ogg:
            path_temp_mix = str(Path(TEMP_DIR) / nome_saida)
            path_entrega = audio_mixer.mixar(path_ogg, file_path, path_temp_mix)
        else:
            # Pedido por texto: não há voz do ouvinte para mixar.
            # A música do acervo vai direto para a fila sem overlay.
            path_entrega = file_path

        # --- Etapa 6: Entrega ao ZaraRadio (via fila gerenciada) ---
        _log_etapa(6, "Entrega ao ZaraRadio")

        if path_ogg:
            # Arquivo mixado: já está em TEMP_DIR com o nome correto
            path_para_enfileirar = path_entrega
        else:
            # Música do acervo: copia para TEMP para preservar o original
            path_para_enfileirar = str(Path(TEMP_DIR) / nome_saida)
            shutil.copy2(path_entrega, path_para_enfileirar)

        path_final = queue_watcher.enfileirar(path_para_enfileirar)

        # --- Etapa 7: Registro do pedido (ativa cooldown) ---
        database.registrar_pedido(numero, metadados.artista, metadados.musica)

        msg = _MSG_SUCESSO.format(artista=metadados.artista, musica=metadados.musica)
        _log_separador(f"Concluído: {nome_saida}")
        return _resultado(True, path_final, msg)

    except Exception as e:
        print(f"[PIPELINE] Erro tecnico: {e}")
        return _resultado(False, None, _MSG_ERRO)


# --- Helpers internos ---

def _resultado(sucesso: bool, path_audio: str | None, mensagem: str | None) -> dict:
    return {"sucesso": sucesso, "path_audio": path_audio, "mensagem": mensagem}


def _gerar_nome_arquivo(artista: str, musica: str) -> str:
    timestamp = int(time.time())
    nome_base = re.sub(r'[\\/:*?"<>|]', "_", f"{artista} - {musica}")
    return f"{timestamp}_{nome_base}.mp3"


def _log_separador(mensagem: str) -> None:
    linha = "=" * 60
    print(f"\n{linha}")
    print(f"[PIPELINE] {mensagem}")
    print(linha)


def _log_etapa(numero: int, descricao: str) -> None:
    prefixo = f"{numero}/6" if numero > 0 else "  "
    print(f"\n[PIPELINE] Etapa {prefixo} — {descricao}")
