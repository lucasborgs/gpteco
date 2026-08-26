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


def test_audio_com_nome_de_candidato_e_bloqueado_antes_do_llm(monkeypatch, tmp_path):
    pipeline = _import_pipeline_with_fake_dependencies(monkeypatch)
    path_ogg = tmp_path / "audio.ogg"
    path_ogg.write_bytes(b"fake")

    analisar = Mock()
    registrar = Mock()

    with patch.object(pipeline.stt, "transcrever", return_value="vou votar no Bolsonaro"), \
         patch.object(pipeline.intelligence, "analisar", analisar), \
         patch.object(pipeline.database, "registrar_pedido", registrar):
        resultado = pipeline.processar_pedido("5511999999999", path_ogg=str(path_ogg))

    assert resultado["sucesso"] is False
    assert resultado["mensagem"] == pipeline.luzia.MSG_ELEITORAL
    analisar.assert_not_called()
    registrar.assert_called_once_with(
        "5511999999999", "", "", sucesso=False, motivo_rejeicao="eleitoral"
    )


def test_texto_digitado_com_nome_de_candidato_nao_e_bloqueado(monkeypatch):
    """O gate de candidatos só vale para áudio (é a voz do ouvinte que iria
    ao ar na mixagem) — pedido digitado não passa por essa checagem."""
    pipeline = _import_pipeline_with_fake_dependencies(monkeypatch)
    metadados = _Metadados(musica="Evidências", artista="Chitãozinho e Xororó")

    with patch.object(pipeline.intelligence, "analisar", return_value=metadados), \
         patch.object(pipeline.database, "verificar_cooldown", return_value=True), \
         patch.object(pipeline.database, "buscar_musica", return_value="/acervo/musica.mp3"), \
         patch.object(pipeline.database, "registrar_pedido"), \
         patch.object(pipeline, "queue_watcher") as fake_queue, \
         patch.object(pipeline, "shutil") as fake_shutil:
        fake_queue.enfileirar.return_value = "/fila/musica.mp3"
        resultado = pipeline.processar_pedido("5511999999999", texto="vou votar no Bolsonaro, toca Evidências")

    assert resultado["sucesso"] is True
    assert resultado["mensagem"] != pipeline.luzia.MSG_ELEITORAL


def test_musica_da_lista_proibida_e_bloqueada_em_pedido_por_texto(monkeypatch):
    pipeline = _import_pipeline_with_fake_dependencies(monkeypatch)
    metadados = _Metadados(musica="Vai dar PT", artista="Léo Santana")
    registrar = Mock()

    with patch.object(pipeline.intelligence, "analisar", return_value=metadados), \
         patch.object(pipeline.database, "registrar_pedido", registrar):
        resultado = pipeline.processar_pedido("5511999999999", texto="toca vai dar pt")

    assert resultado["sucesso"] is False
    assert resultado["mensagem"] == pipeline.luzia.MSG_ELEITORAL
    registrar.assert_called_once_with(
        "5511999999999", "Léo Santana", "Vai dar PT",
        sucesso=False, motivo_rejeicao="eleitoral", genero="Sertanejo",
    )


def test_musica_da_lista_proibida_bloqueia_independente_do_artista(monkeypatch, tmp_path):
    """Confirmado com o usuário: bloqueio é pelo título sozinho, mesmo que o
    LLM identifique um artista diferente do da lista de referência."""
    pipeline = _import_pipeline_with_fake_dependencies(monkeypatch)
    path_ogg = tmp_path / "audio.ogg"
    path_ogg.write_bytes(b"fake")
    metadados = _Metadados(musica="Lula Lá", artista="Artista Qualquer")
    registrar = Mock()

    with patch.object(pipeline.stt, "transcrever", return_value="toca lula la pra mim"), \
         patch.object(pipeline.intelligence, "analisar", return_value=metadados), \
         patch.object(pipeline.database, "registrar_pedido", registrar):
        resultado = pipeline.processar_pedido("5511999999999", path_ogg=str(path_ogg))

    assert resultado["sucesso"] is False
    assert resultado["mensagem"] == pipeline.luzia.MSG_ELEITORAL


def test_pedido_normal_sem_conteudo_eleitoral_nao_e_afetado(monkeypatch):
    pipeline = _import_pipeline_with_fake_dependencies(monkeypatch)
    metadados = _Metadados(musica="Evidências", artista="Chitãozinho e Xororó")

    with patch.object(pipeline.intelligence, "analisar", return_value=metadados), \
         patch.object(pipeline.database, "verificar_cooldown", return_value=True), \
         patch.object(pipeline.database, "buscar_musica", return_value="/acervo/musica.mp3"), \
         patch.object(pipeline.database, "registrar_pedido"), \
         patch.object(pipeline, "queue_watcher") as fake_queue, \
         patch.object(pipeline, "shutil") as fake_shutil:
        fake_queue.enfileirar.return_value = "/fila/musica.mp3"
        resultado = pipeline.processar_pedido("5511999999999", texto="toca Evidências")

    assert resultado["sucesso"] is True
    assert resultado["mensagem"] != pipeline.luzia.MSG_ELEITORAL
