"""Regressões da remoção dos bloqueios temporários do período eleitoral."""

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
        self.is_eleitoral = False



def _processar_liberado(pipeline, metadados, texto, path_ogg=None):
    registrar = Mock()
    with patch.object(pipeline.stt, "transcrever", return_value=texto), \
         patch.object(pipeline.intelligence, "analisar", return_value=metadados) as analisar, \
         patch.object(pipeline.database, "verificar_cooldown", return_value=True), \
         patch.object(pipeline.database, "buscar_musica", return_value="/acervo/musica.mp3"), \
         patch.object(pipeline.database, "registrar_pedido", registrar), \
         patch.object(pipeline.canal_voz, "sugerir_voz", return_value=False), \
         patch.object(pipeline.audio_mixer, "mixar", return_value="/tmp/mixado.mp3"), \
         patch.object(pipeline, "queue_watcher") as fila, \
         patch.object(pipeline, "shutil"):
        fila.enfileirar.return_value = "/fila/musica.mp3"
        resultado = pipeline.processar_pedido(
            "5511999999999", path_ogg=path_ogg,
            texto=None if path_ogg else texto,
        )
    assert resultado["sucesso"] is True
    assert resultado["path_audio"] == "/fila/musica.mp3"
    assert resultado["aguardando_pedido"] is False
    analisar.assert_called_once_with(texto)
    registrar.assert_called_once_with(
        "5511999999999", metadados.artista, metadados.musica,
        genero=metadados.genero, canal="voz" if path_ogg else "texto",
    )


@pytest.mark.parametrize("canal", ["texto", "voz"])
@pytest.mark.parametrize("musica,artista,genero", [
    ("Vai dar PT", "Léo Santana", "axé"),
    ("Lula Lá", "Artista Qualquer", "mpb"),
    ("Capitão do Povo", "Mateus & Cristiano", "sertanejo"),
    ("Negro Drama", "Racionais MC's", "rap nacional"),
    ("Messias", "Dead Fish", "rock"),
    ("Brasil", "Cazuza", "rock"),
])
def test_faixas_e_artistas_antes_vetados_sao_atendidos(
    monkeypatch, tmp_path, canal, musica, artista, genero,
):
    pipeline = _import_pipeline_with_fake_dependencies(monkeypatch)
    audio = tmp_path / "pedido.ogg"
    audio.write_bytes(b"audio")
    metadados = _Metadados(musica=musica, artista=artista, genero=genero)
    _processar_liberado(
        pipeline, metadados, f"toca {musica} de {artista}",
        str(audio) if canal == "voz" else None,
    )


@pytest.mark.parametrize("nome", ["Lula", "Bolsonaro", "Pablo Marçal"])
def test_nome_de_candidato_em_audio_nao_interrompe_o_pedido(monkeypatch, tmp_path, nome):
    pipeline = _import_pipeline_with_fake_dependencies(monkeypatch)
    audio = tmp_path / "pedido.ogg"
    audio.write_bytes(b"audio")
    _processar_liberado(
        pipeline, _Metadados(), f"gosto do {nome}, toca Evidências",
        path_ogg=str(audio),
    )


def test_lista_legada_e_flag_do_classificador_nao_reativam_bloqueio(monkeypatch, tmp_path):
    lista = tmp_path / "eleitoral.json"
    lista.write_text('{"candidatos": ["Lula"], "musicas_proibidas": []}')
    monkeypatch.setenv("ELEITORAL_LISTA_PATH", str(lista))
    pipeline = _import_pipeline_with_fake_dependencies(monkeypatch)
    metadados = _Metadados(musica="Jingle Qualquer", artista="Banda Qualquer")
    metadados.is_eleitoral = True  # objeto de um classificador anterior
    _processar_liberado(pipeline, metadados, "toca o Jingle Qualquer")


def test_resposta_de_perfil_legado_com_campo_extra_continua_compativel(monkeypatch):
    import json

    pipeline = _import_pipeline_with_fake_dependencies(monkeypatch)
    dados = dict(
        is_pedido_musical=True, musica="Messias", artista="Dead Fish",
        is_flashback=True, is_apropriado=True, is_confiante=True,
        is_eleitoral=True, genero="rock",
    )
    resposta = types.SimpleNamespace(choices=[types.SimpleNamespace(
        message=types.SimpleNamespace(content=json.dumps(dados)),
    )])
    with patch.object(pipeline.intelligence.llm_compat, "completar", return_value=resposta):
        metadados = pipeline.intelligence.analisar("toca Messias Dead Fish")
    assert not hasattr(metadados, "is_eleitoral")
    _processar_liberado(pipeline, metadados, "toca Messias Dead Fish")
