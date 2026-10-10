import importlib
import sys
import types
from unittest.mock import Mock, patch

import pytest


def _import_pipeline_with_fake_dependencies(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "fake-key")
    monkeypatch.setenv("GROQ_API_KEY", "fake-key")

    fake_yt_dlp = types.ModuleType("yt_dlp")
    fake_yt_dlp.YoutubeDL = object

    fake_psycopg2 = types.ModuleType("psycopg2")
    fake_psycopg2.extensions = types.SimpleNamespace(connection=object)
    fake_psycopg2_extras = types.ModuleType("psycopg2.extras")

    fake_pydub = types.ModuleType("pydub")
    fake_pydub.AudioSegment = object

    with patch.dict(
        sys.modules,
        {
            "yt_dlp": fake_yt_dlp,
            "psycopg2": fake_psycopg2,
            "psycopg2.extras": fake_psycopg2_extras,
            "pydub": fake_pydub,
        },
    ):
        for mod in (
            "core.pipeline",
            "core.audio_mixer",
            "core.downloader",
            "core.database",
            "core.intelligence",
            "core.composer",
            "core.stt",
            "core.repertorio",
            "core.canal_voz",
        ):
            sys.modules.pop(mod, None)
        return importlib.import_module("core.pipeline")


class _Metadados:
    def __init__(
        self,
        is_pedido_musical=True,
        musica="Evidências",
        artista="Chitãozinho e Xororó",
        is_flashback=True,
        is_apropriado=True,
        is_confiante=True,
        genero="Sertanejo",
    ):
        self.is_pedido_musical = is_pedido_musical
        self.musica = musica
        self.artista = artista
        self.is_flashback = is_flashback
        self.is_apropriado = is_apropriado
        self.is_confiante = is_confiante
        self.is_pedido_explicito = False
        self.genero = genero
        self.is_eleitoral = False


def test_fila_cheia_no_download_e_recusa_amigavel(monkeypatch):
    """B3: FilaCheia levantada por downloader.baixar tem que ser recusada com
    codigo="download_ocupado" e motivo_rejeicao="busca_ocupada" — não pode
    cair no except Exception genérico (erro_tecnico)."""
    pipeline = _import_pipeline_with_fake_dependencies(monkeypatch)
    metadados = _Metadados(musica="Evidências", artista="Chitãozinho e Xororó")
    registrar = Mock()

    with patch.object(pipeline.intelligence, "analisar", return_value=metadados), \
         patch.object(pipeline.database, "verificar_cooldown", return_value=True), \
         patch.object(pipeline.canal_voz, "avaliar", return_value=(False, False)), \
         patch.object(pipeline.database, "buscar_musica", return_value=None), \
         patch.object(
             pipeline.downloader, "baixar",
             side_effect=pipeline.downloader.yt_throttle.FilaCheia("fila cheia"),
         ), \
         patch.object(pipeline.database, "registrar_pedido", registrar):
        resultado = pipeline.processar_pedido("5511999999999", texto="toca Evidências")

    assert resultado["sucesso"] is False
    assert resultado["codigo"] == "download_ocupado"
    assert resultado["aguardando_pedido"] is True
    registrar.assert_called_once_with(
        "5511999999999", "Chitãozinho e Xororó", "Evidências",
        sucesso=False, motivo_rejeicao="busca_ocupada", genero="Sertanejo", canal="texto",
    )


def test_espera_excedida_no_download_e_recusa_amigavel(monkeypatch):
    """Mesmo tratamento para EsperaExcedida — as duas exceções herdam de
    RuntimeError e precisam do except específico antes do genérico."""
    pipeline = _import_pipeline_with_fake_dependencies(monkeypatch)
    metadados = _Metadados(musica="Evidências", artista="Chitãozinho e Xororó")
    registrar = Mock()

    with patch.object(pipeline.intelligence, "analisar", return_value=metadados), \
         patch.object(pipeline.database, "verificar_cooldown", return_value=True), \
         patch.object(pipeline.canal_voz, "avaliar", return_value=(False, False)), \
         patch.object(pipeline.database, "buscar_musica", return_value=None), \
         patch.object(
             pipeline.downloader, "baixar",
             side_effect=pipeline.downloader.yt_throttle.EsperaExcedida("espera excedida"),
         ), \
         patch.object(pipeline.database, "registrar_pedido", registrar):
        resultado = pipeline.processar_pedido("5511999999999", texto="toca Evidências")

    assert resultado["sucesso"] is False
    assert resultado["codigo"] == "download_ocupado"
    registrar.assert_called_once_with(
        "5511999999999", "Chitãozinho e Xororó", "Evidências",
        sucesso=False, motivo_rejeicao="busca_ocupada", genero="Sertanejo", canal="texto",
    )


def test_mensagem_de_busca_ocupada_vem_do_perfil(monkeypatch):
    """A mensagem enviada ao ouvinte é luzia.mensagem("busca_ocupada", ...),
    não o texto fixo do erro técnico genérico."""
    pipeline = _import_pipeline_with_fake_dependencies(monkeypatch)
    metadados = _Metadados(musica="Evidências", artista="Chitãozinho e Xororó")

    with patch.object(pipeline.intelligence, "analisar", return_value=metadados), \
         patch.object(pipeline.database, "verificar_cooldown", return_value=True), \
         patch.object(pipeline.canal_voz, "avaliar", return_value=(False, False)), \
         patch.object(pipeline.database, "buscar_musica", return_value=None), \
         patch.object(
             pipeline.downloader, "baixar",
             side_effect=pipeline.downloader.yt_throttle.FilaCheia("fila cheia"),
         ), \
         patch.object(pipeline.database, "registrar_pedido"):
        resultado = pipeline.processar_pedido("5511999999999", texto="toca Evidências")

    assert resultado["mensagem"] == pipeline.luzia.mensagem(
        "busca_ocupada", pipeline._MSG_BUSCA_OCUPADA_FALLBACK
    )
    assert resultado["mensagem"] != pipeline._msg_erro()


def test_notificacao_de_fila_quando_espera_estimada_alta(monkeypatch):
    """Seção 7.4: antes de baixar, se espera_estimada("busca") > 20 e existe
    callback de notificação, avisa sem prometer prazo e sem citar posição."""
    pipeline = _import_pipeline_with_fake_dependencies(monkeypatch)
    metadados = _Metadados(musica="Evidências", artista="Chitãozinho e Xororó")
    notificar = Mock()

    with patch.object(pipeline.intelligence, "analisar", return_value=metadados), \
         patch.object(pipeline.database, "verificar_cooldown", return_value=True), \
         patch.object(pipeline.canal_voz, "avaliar", return_value=(False, False)), \
         patch.object(pipeline.database, "buscar_musica", return_value=None), \
         patch.object(pipeline.downloader.yt_throttle, "espera_estimada", return_value=25.0), \
         patch.object(pipeline.downloader, "baixar", return_value="/acervo/musica.mp3"), \
         patch.object(pipeline.database, "registrar_pedido"), \
         patch.object(pipeline, "queue_watcher") as fake_queue, \
         patch.object(pipeline, "shutil"):
        fake_queue.enfileirar.return_value = "/fila/musica.mp3"
        pipeline.processar_pedido("5511999999999", texto="toca Evidências", notificar=notificar)

    mensagens = [c.args[0] for c in notificar.call_args_list]
    assert any("fila" in m.lower() for m in mensagens)
    assert not any("minuto" in m.lower() or "posição" in m.lower() for m in mensagens)


def test_sem_notificacao_de_fila_quando_espera_estimada_baixa(monkeypatch):
    """Abaixo do limiar de 20s, não notifica fila — evita ruído em espera curta."""
    pipeline = _import_pipeline_with_fake_dependencies(monkeypatch)
    metadados = _Metadados(musica="Evidências", artista="Chitãozinho e Xororó")
    notificar = Mock()

    with patch.object(pipeline.intelligence, "analisar", return_value=metadados), \
         patch.object(pipeline.database, "verificar_cooldown", return_value=True), \
         patch.object(pipeline.canal_voz, "avaliar", return_value=(False, False)), \
         patch.object(pipeline.database, "buscar_musica", return_value=None), \
         patch.object(pipeline.downloader.yt_throttle, "espera_estimada", return_value=5.0), \
         patch.object(pipeline.downloader, "baixar", return_value="/acervo/musica.mp3"), \
         patch.object(pipeline.database, "registrar_pedido"), \
         patch.object(pipeline, "queue_watcher") as fake_queue, \
         patch.object(pipeline, "shutil"):
        fake_queue.enfileirar.return_value = "/fila/musica.mp3"
        pipeline.processar_pedido("5511999999999", texto="toca Evidências", notificar=notificar)

    mensagens = [c.args[0] for c in notificar.call_args_list]
    assert not any("fila na busca" in m.lower() for m in mensagens)
