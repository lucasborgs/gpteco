"""Convite opcional para voz e regressões do resultado da entrega."""

import importlib
import sys
import types
from datetime import datetime, timedelta
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



def _rodar_texto(pipeline, historico, registrar=None):
    historico = list(historico)
    registrar = registrar if registrar is not None else Mock()

    def salvar(*args, **kwargs):
        registrar(*args, **kwargs)
        if kwargs.get("sucesso", True):
            historico.append((datetime.now(), kwargs["canal"]))

    with patch.object(pipeline.intelligence, "analisar", return_value=_Metadados()), \
         patch.object(pipeline.database, "verificar_cooldown", return_value=True), \
         patch.object(pipeline.database, "pedidos_atendidos_por_canal", return_value=historico), \
         patch.object(pipeline.database, "buscar_musica", return_value="/acervo/musica.mp3"), \
         patch.object(pipeline.database, "registrar_pedido", side_effect=salvar), \
         patch.object(pipeline, "queue_watcher") as fila, \
         patch.object(pipeline, "shutil"):
        fila.enfileirar.return_value = "/fila/musica.mp3"
        resultado = pipeline.processar_pedido("5511999999999", texto="toca Evidências")
    return resultado, registrar


@pytest.mark.parametrize("textos_anteriores", [0, 1, 2, 3, 10])
def test_convite_a_partir_do_segundo_pedido_sem_bloquear_os_proximos(monkeypatch, textos_anteriores):
    pipeline = _import_pipeline_with_fake_dependencies(monkeypatch)
    historico = [(datetime.now() - timedelta(hours=i + 1), "texto") for i in reversed(range(textos_anteriores))]
    resultado, registrar = _rodar_texto(pipeline, historico)

    assert resultado["sucesso"] is True
    assert resultado["aguardando_pedido"] is False
    assert resultado["pendente"] is False
    assert (pipeline._msg_sugestao_voz() in resultado["mensagem"]) == (textos_anteriores >= 1)
    assert resultado["mensagem"].startswith(pipeline.config_radio.MSG_SUCESSO.format(
        artista="Chitãozinho e Xororó", musica="Evidências",
    ))
    registrar.assert_called_once_with(
        "5511999999999", "Chitãozinho e Xororó", "Evidências",
        genero="Sertanejo", canal="texto",
    )


def test_pedido_por_voz_reinicia_o_convite(monkeypatch):
    pipeline = _import_pipeline_with_fake_dependencies(monkeypatch)
    canais = ["texto", "texto", "voz"]
    historico = [(datetime.now() - timedelta(hours=4 - i), canal) for i, canal in enumerate(canais)]
    resultado, _ = _rodar_texto(pipeline, historico)
    assert resultado["sucesso"] is True
    assert pipeline._msg_sugestao_voz() not in resultado["mensagem"]


def test_pedido_por_audio_nao_recebe_convite_para_audio(monkeypatch, tmp_path):
    pipeline = _import_pipeline_with_fake_dependencies(monkeypatch)
    audio = tmp_path / "ouvinte.ogg"
    audio.write_bytes(b"voz")
    with patch.object(pipeline.stt, "transcrever", return_value="toca Evidências"), \
         patch.object(pipeline.intelligence, "analisar", return_value=_Metadados()), \
         patch.object(pipeline.database, "verificar_cooldown", return_value=True), \
         patch.object(pipeline.database, "buscar_musica", return_value="/acervo/musica.mp3"), \
         patch.object(pipeline.database, "registrar_pedido"), \
         patch.object(pipeline.canal_voz, "sugerir_voz") as sugestao, \
         patch.object(pipeline.audio_mixer, "mixar", return_value="/tmp/mix.mp3"), \
         patch.object(pipeline.queue_watcher, "enfileirar", return_value="/fila/musica.mp3"):
        resultado = pipeline.processar_pedido("5511999999999", path_ogg=str(audio))
    assert resultado["sucesso"] is True
    sugestao.assert_not_called()
    assert pipeline._msg_sugestao_voz() not in resultado["mensagem"]


def test_falha_no_convite_nao_desfaz_entrega(monkeypatch):
    pipeline = _import_pipeline_with_fake_dependencies(monkeypatch)
    with patch.object(pipeline.canal_voz, "sugerir_voz", side_effect=RuntimeError("banco indisponivel")):
        resultado, registrar = _rodar_texto(pipeline, [])
    assert resultado["sucesso"] is True
    assert resultado["path_audio"] == "/fila/musica.mp3"
    registrar.assert_called_once()


def test_pedido_recusado_por_cooldown_nao_recebe_convite(monkeypatch):
    pipeline = _import_pipeline_with_fake_dependencies(monkeypatch)
    with patch.object(pipeline.intelligence, "analisar", return_value=_Metadados()), \
         patch.object(pipeline.database, "verificar_cooldown", return_value=False), \
         patch.object(pipeline.database, "registrar_pedido"), \
         patch.object(pipeline.composer, "compor", return_value="Aguarde um pouco."), \
         patch.object(pipeline.canal_voz, "sugerir_voz") as sugestao:
        resultado = pipeline.processar_pedido("5511999999999", texto="toca Evidências")
    assert resultado["sucesso"] is False
    sugestao.assert_not_called()


@pytest.mark.parametrize("canal", ["texto", "voz"])
@pytest.mark.parametrize("falha", ["registro", "entrega", "mensagem"])
def test_resultado_respeita_limite_da_entrega(monkeypatch, tmp_path, canal, falha):
    """Somente falhas anteriores à entrega podem informar fracasso ao ouvinte."""
    pipeline = _import_pipeline_with_fake_dependencies(monkeypatch)
    monkeypatch.setattr(pipeline, "TEMP_DIR", str(tmp_path / "temp"))
    acervo = tmp_path / "musica.mp3"
    acervo.write_bytes(b"musica")
    audio = tmp_path / "ouvinte.ogg"
    audio.write_bytes(b"voz")
    metadados = _Metadados()
    registrar = Mock(side_effect=RuntimeError("banco indisponivel") if falha == "registro" else None)
    destino = tmp_path / "fila" / "pedido.mp3"
    if falha == "mensagem":
        monkeypatch.setattr(pipeline.config_radio, "MSG_SUCESSO", "{campo_inexistente}")

    def enfileirar(origem):
        if falha == "entrega":
            raise RuntimeError("fila indisponivel")
        destino.parent.mkdir(exist_ok=True)
        destino.write_bytes(pipeline.Path(origem).read_bytes())
        return str(destino)

    with patch.object(pipeline.intelligence, "analisar", return_value=metadados), \
         patch.object(pipeline.database, "verificar_cooldown", return_value=True), \
         patch.object(pipeline.canal_voz, "sugerir_voz", return_value=False), \
         patch.object(pipeline.database, "buscar_musica", return_value=str(acervo)), \
         patch.object(pipeline.database, "registrar_pedido", registrar), \
         patch.object(pipeline.stt, "transcrever", return_value="toca Evidências"), \
         patch.object(pipeline.audio_mixer, "mixar", return_value=str(acervo)), \
         patch.object(pipeline.queue_watcher, "enfileirar", side_effect=enfileirar) as entregar:
        resultado = pipeline.processar_pedido(
            "5511999999999",
            path_ogg=str(audio) if canal == "voz" else None,
            texto="toca Evidências" if canal == "texto" else None,
        )

    if falha != "registro":
        assert not destino.exists()
        assert resultado["sucesso"] is False
        assert resultado["path_audio"] is None
        registrar.assert_called_once_with(
            "5511999999999", metadados.artista, metadados.musica, sucesso=False,
            motivo_rejeicao="erro_tecnico", canal=canal,
        )
        if falha == "mensagem":
            entregar.assert_not_called()
        else:
            entregar.assert_called_once()
        return

    assert destino.read_bytes() == b"musica"
    assert resultado["sucesso"] is True
    assert resultado["path_audio"] == str(destino)
    assert resultado["artista"] == metadados.artista
    assert resultado["musica"] == metadados.musica
    assert resultado["mensagem"] == pipeline.config_radio.MSG_SUCESSO.format(
        artista=metadados.artista, musica=metadados.musica,
    )
    assert resultado["codigo"] == "registro_pendente"
    entregar.assert_called_once()
    registrar.assert_called_once_with(
        "5511999999999", metadados.artista, metadados.musica,
        genero=metadados.genero, canal=canal,
    )
