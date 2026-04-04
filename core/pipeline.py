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

from __future__ import annotations

import os
import re
import shutil
import time
from pathlib import Path

from core import audio_mixer, config_radio, database, downloader, intelligence, queue_watcher, stt

# Diretórios (configuráveis via .env)
TEMP_DIR: str = os.getenv(
    "TEMP_DIR",
    str(Path(__file__).parent.parent / "workspace" / "temp"),
)
# Define como "true" no .env para desativar o cooldown durante testes
DISABLE_COOLDOWN: bool = os.getenv("DISABLE_COOLDOWN", "false").lower() == "true"

# Mensagem de erro técnico — não é configurável (não é mensagem da rádio)
_MSG_ERRO = "Ocorreu um erro ao processar seu pedido. Tente novamente em breve."


def processar_pedido(
    numero: str,
    path_ogg: str | None = None,
    texto: str | None = None,
    notificar: callable | None = None,
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
    if path_ogg and not os.path.isfile(path_ogg):
        return _resultado(False, None, _MSG_ERRO)

    # Modo retry: path_ogg + texto fornecidos juntos.
    # O texto é a confirmação digitada pelo ouvinte; o áudio é usado só para a mixagem.
    _is_retry = bool(path_ogg and texto)

    os.makedirs(TEMP_DIR, exist_ok=True)

    _log_separador(f"Novo pedido de {numero}")

    try:
        # --- Etapa 1: Transcrição STT ---
        if path_ogg and not _is_retry:
            _log_etapa(1, "Transcrição STT")
            if notificar:
                notificar("🎤 Processando seu áudio...")
            texto = stt.transcrever(path_ogg)
            if not texto.strip():
                return _resultado(False, None, "Não consegui entender o áudio. Pode reenviar ou mandar um texto com o nome da música?")
            if notificar:
                notificar(f"Entendi: \"{texto}\"\n\nBuscando a música...")
        elif _is_retry:
            _log_etapa(1, "Confirmação de texto — STT ignorado (modo retry)")
            print(f"[PIPELINE] Texto de confirmação: \"{texto}\"")
        else:
            _log_etapa(1, "Entrada de texto — STT ignorado")
            print(f"[PIPELINE] Texto recebido: \"{texto}\"")

        # --- Etapa 2: Inteligência + Regras de Negócio ---
        _log_etapa(2, "Análise LLM")
        metadados = intelligence.analisar(texto)

        # Mensagem fora do escopo do bot
        if not metadados.is_pedido_musical:
            if metadados.is_saudacao and not database.verificar_interacao_recente(numero):
                print("[PIPELINE] Novo ouvinte — enviando msg_saudacao.")
                database.registrar_pedido(numero, "", "", sucesso=False, motivo_rejeicao="saudacao")
                return _resultado(False, None, config_radio.MSG_SAUDACAO)
            print("[PIPELINE] Não é pedido musical — ignorando silenciosamente.")
            return _resultado(False, None, None)

        if not metadados.is_apropriado:
            database.registrar_pedido(numero, metadados.artista, metadados.musica, sucesso=False, motivo_rejeicao="inapropriado", genero=metadados.genero)
            return _resultado(False, None, config_radio.MSG_INAPROPRIADO)

        # --- Rate limiting por número (após confirmar que é pedido musical) ---
        _log_etapa(0, "Verificação de cooldown")
        if not DISABLE_COOLDOWN and not database.verificar_cooldown(numero):
            database.registrar_pedido(numero, metadados.artista, metadados.musica, sucesso=False, motivo_rejeicao="cooldown", genero=metadados.genero)
            return _resultado(False, None, config_radio.MSG_COOLDOWN)

        # Baixa confiança na identificação (transcrição possivelmente corrompida).
        # No modo retry o ouvinte já digitou — não abre nova pendência.
        if not metadados.is_confiante and not _is_retry:
            if not metadados.musica or not metadados.artista:
                database.registrar_pedido(numero, "", "", sucesso=False, motivo_rejeicao="nao_identificado")
                return _resultado(False, None, config_radio.MSG_NAO_ID)
            if path_ogg:
                database.criar_pendencia(numero, path_ogg, metadados.artista, metadados.musica)
                msg = config_radio.MSG_CONFIRMACAO.format(
                    musica=metadados.musica, artista=metadados.artista
                )
                return _resultado(False, None, msg, pendente=True)
            # Texto digitado com baixa confiança → pede confirmação (sem pendência de áudio)
            database.criar_pendencia(numero, "__texto__", metadados.artista, metadados.musica)
            msg = config_radio.MSG_CONFIRMACAO.format(
                musica=metadados.musica, artista=metadados.artista
            )
            return _resultado(False, None, msg, pendente=True)

        if not metadados.musica or not metadados.artista:
            database.registrar_pedido(numero, "", "", sucesso=False, motivo_rejeicao="nao_identificado")
            return _resultado(False, None, config_radio.MSG_NAO_ID)

        if not metadados.is_flashback:
            database.registrar_pedido(numero, metadados.artista, metadados.musica, sucesso=False, motivo_rejeicao="nao_flashback", genero=metadados.genero)
            msg = config_radio.MSG_NAO_REPERTORIO.format(musica=metadados.musica, artista=metadados.artista)
            return _resultado(False, None, msg)

        # --- Etapa 3: Busca no Acervo Local ---
        _log_etapa(3, "Busca no acervo local")
        file_path = database.buscar_musica(metadados.artista, metadados.musica)

        # --- Etapa 4: Download Dinâmico (somente se necessário) ---
        if file_path:
            _log_etapa(4, "Download ignorado — música já no acervo")
            if notificar:
                notificar(f"🎵 Encontrei! Preparando '{metadados.musica}' de {metadados.artista}...")
        else:
            _log_etapa(4, "Download dinâmico (YouTube)")
            if notificar:
                notificar("⬇️ Sua música não está no acervo ainda. Aguarde, estou buscando...")
            file_path = downloader.baixar(metadados.artista, metadados.musica)

        # --- Etapa 5: Mixagem (somente se havia voz para misturar) ---
        _log_etapa(5, "Mixagem de áudio")
        if path_ogg and notificar:
            notificar("🔀 Mixando sua voz com a música...")
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

        try:
            path_final = queue_watcher.enfileirar(path_para_enfileirar)
        except Exception:
            # Limpa o arquivo temporário para evitar acúmulo em TEMP
            if os.path.isfile(path_para_enfileirar):
                os.remove(path_para_enfileirar)
            raise

        # --- Etapa 7: Registro do pedido (ativa cooldown) ---
        # Registrado APÓS enfileirar bem-sucedido: cooldown só ativa se a música
        # foi entregue na fila. Se enfileirar lançar exceção, o except registra
        # o pedido como erro_tecnico (sem ativar cooldown para o ouvinte).
        database.registrar_pedido(numero, metadados.artista, metadados.musica, genero=metadados.genero)

        msg = config_radio.MSG_SUCESSO.format(artista=metadados.artista, musica=metadados.musica)
        _log_separador(f"Concluído: {nome_saida}")
        return _resultado(True, path_final, msg)

    except Exception as e:
        print(f"[PIPELINE] Erro tecnico: {e}")
        try:
            artista = metadados.artista if "metadados" in locals() else ""
            musica  = metadados.musica  if "metadados" in locals() else ""
            database.registrar_pedido(numero, artista, musica, sucesso=False, motivo_rejeicao="erro_tecnico")
        except Exception:
            pass
        return _resultado(False, None, _MSG_ERRO)


# --- Helpers internos ---

def _resultado(sucesso: bool, path_audio: str | None, mensagem: str | None, pendente: bool = False) -> dict:
    return {"sucesso": sucesso, "path_audio": path_audio, "mensagem": mensagem, "pendente": pendente}


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
