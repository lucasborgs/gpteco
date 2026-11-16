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
    3. Acervo   : busca música no PostgreSQL (Supabase)
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

from core import audio_mixer, canal_voz, composer, config_radio, database, downloader, intelligence, luzia, queue_watcher, repertorio, stt

# Diretórios (configuráveis via .env)
TEMP_DIR: str = os.getenv(
    "TEMP_DIR",
    str(Path(__file__).parent.parent / "workspace" / "temp"),
)
# Define como "true" no .env para desativar o cooldown durante testes
DISABLE_COOLDOWN: bool = os.getenv("DISABLE_COOLDOWN", "false").lower() == "true"

# Mensagem de falha interna. O texto normal vem do perfil (## erro_tecnico),
# para a rádio ajustar o tom sem rebuild; esta constante é só o fallback de um
# assistente.md que ainda não tenha a seção. Ver _msg_erro(), nos helpers.
_MSG_ERRO_FALLBACK = (
    "Ops, me embolei aqui com o seu pedido! Pode mandar de novo daqui a pouquinho? 🎵"
)

# Fallback de "busca_ocupada" (F0.4/B4) — usado só se o perfil ativo não tiver
# o slug (ex.: assistente.md do cliente ainda não atualizado). O texto normal
# vem de luzia.mensagem("busca_ocupada", ...), que lê core/luzia/luzia.md.
_MSG_BUSCA_OCUPADA_FALLBACK = (
    "Tá com muita gente buscando música aqui agora! Tenta de novo daqui a "
    "uns minutinhos, por favor. 🎵"
)

_MSG_SUGESTAO_VOZ_FALLBACK = (
    "Que tal mandar os próximos pedidos por áudio, com o nome da música e do "
    "artista? Sua voz pode aparecer na programação! 🎙️"
)


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
        return _resultado(False, None, _msg_erro())
    if path_ogg and not os.path.isfile(path_ogg):
        return _resultado(False, None, _msg_erro())

    # Modo retry: path_ogg + texto fornecidos juntos.
    # O texto é a confirmação digitada pelo ouvinte; o áudio é usado só para a mixagem.
    _is_retry = bool(path_ogg and texto)

    # Canal do pedido:
    # há voz do ouvinte quando existe path_ogg (vai à mixagem e ao ar), inclusive
    # no modo retry. A pendência "__texto__" chega sem path_ogg e é "texto".
    # Calculado antes do try/except: é a única variável do bloco de erro que
    # não depende de `metadados` (ver o except genérico, ao final da função).
    canal = "voz" if path_ogg else "texto"

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

        # Qualquer mensagem fora do escopo musical (saudação, agradecimento,
        # pergunta solta) apresenta o menu. A janela pós-sucesso é tratada antes,
        # no webhook, com MSG_MENU_POS_SUCESSO.
        if not metadados.is_pedido_musical:
            print("[PIPELINE] Mensagem fora de escopo — enviando menu.")
            return _resultado(False, None, config_radio.MSG_SAUDACAO, mostrar_menu=True)

        if not metadados.is_apropriado:
            database.registrar_pedido(numero, metadados.artista, metadados.musica, sucesso=False, motivo_rejeicao="inapropriado", genero=metadados.genero, canal=canal)
            msg = composer.compor("inapropriado", {"artista": metadados.artista, "musica": metadados.musica}, texto)
            return _resultado(False, None, msg)

        # --- Rate limiting por número (após confirmar que é pedido musical) ---
        _log_etapa(0, "Verificação de cooldown")
        if not DISABLE_COOLDOWN and not database.verificar_cooldown(numero):
            database.registrar_pedido(numero, metadados.artista, metadados.musica, sucesso=False, motivo_rejeicao="cooldown", genero=metadados.genero, canal=canal)
            msg = composer.compor("cooldown", {"artista": metadados.artista, "musica": metadados.musica}, texto)
            return _resultado(False, None, msg)

        # Baixa confiança na identificação (transcrição possivelmente corrompida).
        # No modo retry o ouvinte já digitou — não abre nova pendência.
        if not metadados.is_confiante and not _is_retry:
            if not metadados.musica or not metadados.artista:
                database.registrar_pedido(numero, "", "", sucesso=False, motivo_rejeicao="nao_identificado", canal=canal)
                return _resultado(False, None, composer.compor("nao_id", {}, texto), aguardando_pedido=True)
            if path_ogg:
                database.criar_pendencia(numero, path_ogg, metadados.artista, metadados.musica)
                msg = composer.compor("confirmacao", {"musica": metadados.musica, "artista": metadados.artista}, texto)
                return _resultado(False, None, msg, pendente=True)
            # Texto digitado com baixa confiança → pede confirmação (sem pendência de áudio)
            database.criar_pendencia(numero, "__texto__", metadados.artista, metadados.musica)
            msg = composer.compor("confirmacao", {"musica": metadados.musica, "artista": metadados.artista}, texto)
            return _resultado(False, None, msg, pendente=True)

        if not metadados.musica or not metadados.artista:
            database.registrar_pedido(numero, "", "", sucesso=False, motivo_rejeicao="nao_identificado", canal=canal)
            return _resultado(False, None, composer.compor("nao_id", {}, texto), aguardando_pedido=True)

        if not metadados.is_flashback and not repertorio.genero_liberado(metadados.genero):
            database.registrar_pedido(numero, metadados.artista, metadados.musica, sucesso=False, motivo_rejeicao="nao_flashback", genero=metadados.genero, canal=canal)
            msg = composer.compor("nao_repertorio", {"musica": metadados.musica, "artista": metadados.artista, "genero": metadados.genero}, texto)
            return _resultado(False, None, msg, aguardando_pedido=True)
        if not metadados.is_flashback:
            print(f"[PIPELINE] Gênero liberado por configuração: '{metadados.genero}' (is_flashback=false)")

        # --- Etapa 3: Busca no Acervo Local ---
        _log_etapa(3, "Busca no acervo local")
        file_path = database.buscar_musica(metadados.artista, metadados.musica)

        # --- Etapa 4: Download Dinâmico (somente se necessário) ---
        if file_path:
            _log_etapa(4, "Download ignorado — música já no acervo")
        else:
            _log_etapa(4, "Download dinâmico (YouTube)")
            # Notifica apenas pedidos por texto (áudio já recebeu "Buscando a música..." no STT)
            if not path_ogg and notificar:
                notificar("🔎 Buscando sua música...")
            # Notificação técnica de fila do throttle (seção 7.4) — sem prometer
            # prazo e sem mencionar posição na fila (regras duras do perfil).
            if notificar and downloader.yt_throttle.espera_estimada("busca") > 20:
                notificar("Tem fila na busca aqui, me dá só um instantinho 🎵")
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

        # Prepara a confirmação antes da entrega: erro no perfil não pode
        # transformar uma música já enfileirada em um falso fracasso.
        msg = config_radio.MSG_SUCESSO.format(artista=metadados.artista, musica=metadados.musica)

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
        codigo = None
        try:
            database.registrar_pedido(numero, metadados.artista, metadados.musica, genero=metadados.genero, canal=canal)
        except Exception as e:
            # A entrega já aconteceu e não é desfeita por uma falha no banco.
            # Não registra rejeição nem pede ao ouvinte para repetir o pedido.
            # O código distingue a falha de persistência para os consumidores;
            # o cooldown no banco só fica disponível se o registro for salvo.
            print(f"[PIPELINE] Pedido entregue à fila, mas registro no banco falhou: {e}")
            codigo = "registro_pendente"

        # O convite só acompanha pedidos já atendidos. É opcional e nunca
        # recusa texto nem transforma uma entrega bem-sucedida em falha.
        if canal == "texto" and codigo is None:
            try:
                if canal_voz.sugerir_voz(numero):
                    msg += "\n\n" + _msg_sugestao_voz()
            except Exception as e:
                print(f"[PIPELINE] Pedido entregue; não foi possível acrescentar o convite de voz: {e}")

        _log_separador(f"Concluído: {nome_saida}")
        return _resultado(
            True,
            path_final,
            msg,
            artista=metadados.artista,
            musica=metadados.musica,
            is_pedido_explicito=metadados.is_pedido_explicito,
            codigo=codigo,
        )

    except (downloader.yt_throttle.FilaCheia, downloader.yt_throttle.EsperaExcedida) as e:
        # Recusa amigável do throttle do YouTube (item B) — tem que vir antes
        # do "except Exception" genérico abaixo: as duas exceções herdam de
        # RuntimeError, e cairiam ali (erro_tecnico) se a ordem fosse invertida.
        print(f"[PIPELINE] Busca ocupada (throttle do YouTube): {e}")
        try:
            database.registrar_pedido(
                numero, metadados.artista, metadados.musica,
                sucesso=False, motivo_rejeicao="busca_ocupada",
                genero=metadados.genero, canal=canal,
            )
        except Exception:
            pass
        msg = luzia.mensagem("busca_ocupada", _MSG_BUSCA_OCUPADA_FALLBACK)
        return _resultado(False, None, msg, codigo="download_ocupado", aguardando_pedido=True)

    except Exception as e:
        print(f"[PIPELINE] Erro tecnico: {e}")
        try:
            artista = metadados.artista if "metadados" in locals() else ""
            musica  = metadados.musica  if "metadados" in locals() else ""
            database.registrar_pedido(numero, artista, musica, sucesso=False, motivo_rejeicao="erro_tecnico", canal=canal)
        except Exception:
            pass
        return _resultado(False, None, _msg_erro())


# --- Helpers internos ---

def _msg_sugestao_voz() -> str:
    return luzia.mensagem("sugestao_voz", _MSG_SUGESTAO_VOZ_FALLBACK)


def _msg_erro() -> str:
    """Texto de falha interna, lido do perfil a CADA chamada.

    Não é constante de módulo porque o perfil tem hot-reload por mtime: ler no
    import congelaria a mensagem da primeira versão carregada. Acesso tolerante
    (luzia.mensagem) de propósito — este é o caminho de erro, o último lugar
    onde cabe levantar outra exceção por falta de uma seção no assistente.md.
    """
    return luzia.mensagem("erro_tecnico", _MSG_ERRO_FALLBACK)


def _resultado(
    sucesso: bool,
    path_audio: str | None,
    mensagem: str | None,
    pendente: bool = False,
    mostrar_menu: bool = False,
    aguardando_pedido: bool = False,
    artista: str | None = None,
    musica: str | None = None,
    is_pedido_explicito: bool = False,
    codigo: str | None = None,
) -> dict:
    return {
        "sucesso": sucesso,
        "path_audio": path_audio,
        "mensagem": mensagem,
        "pendente": pendente,
        "mostrar_menu": mostrar_menu,
        "aguardando_pedido": aguardando_pedido,
        "artista": artista,
        "musica": musica,
        "is_pedido_explicito": is_pedido_explicito,
        "codigo": codigo,
    }


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
