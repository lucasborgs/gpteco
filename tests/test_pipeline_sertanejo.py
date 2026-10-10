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


def test_sertanejo_moderno_e_aceito_mesmo_sem_flashback(monkeypatch):
    """Pedido rotulado sertanejo (mesmo com maiúscula, como o classificador
    costuma devolver) é aceito mesmo quando is_flashback=False — é a
    liberação determinística do item A vencendo o veredito da LLM."""
    pipeline = _import_pipeline_with_fake_dependencies(monkeypatch)
    metadados = _Metadados(musica="Nosso Quadro", artista="Zé Neto e Cristiano",
                            is_flashback=False, genero="Sertanejo")

    with patch.object(pipeline.intelligence, "analisar", return_value=metadados), \
         patch.object(pipeline.database, "verificar_cooldown", return_value=True), \
         patch.object(pipeline.canal_voz, "avaliar", return_value=(False, False)), \
         patch.object(pipeline.database, "buscar_musica", return_value="/acervo/musica.mp3"), \
         patch.object(pipeline.database, "registrar_pedido"), \
         patch.object(pipeline, "queue_watcher") as fake_queue, \
         patch.object(pipeline, "shutil"):
        fake_queue.enfileirar.return_value = "/fila/musica.mp3"
        resultado = pipeline.processar_pedido("5511999999999", texto="toca Nosso Quadro")

    assert resultado["sucesso"] is True


def test_genero_nao_liberado_sem_flashback_e_recusado(monkeypatch):
    """Gênero fora de GENEROS_SEMPRE_ACEITOS continua sujeito ao
    is_flashback do classificador — sem a liberação, a recusa de sempre."""
    pipeline = _import_pipeline_with_fake_dependencies(monkeypatch)
    metadados = _Metadados(musica="Oceano", artista="Djavan",
                            is_flashback=False, genero="gospel")
    registrar = Mock()

    with patch.object(pipeline.intelligence, "analisar", return_value=metadados), \
         patch.object(pipeline.database, "verificar_cooldown", return_value=True), \
         patch.object(pipeline.canal_voz, "avaliar", return_value=(False, False)), \
         patch.object(pipeline.database, "registrar_pedido", registrar):
        resultado = pipeline.processar_pedido("5511999999999", texto="toca Oceano do Djavan")

    assert resultado["sucesso"] is False
    assert resultado["aguardando_pedido"] is True
    registrar.assert_called_once_with(
        "5511999999999", "Djavan", "Oceano",
        sucesso=False, motivo_rejeicao="nao_flashback", genero="gospel", canal="texto",
    )


def test_sertanejo_na_lista_eleitoral_precedencia(monkeypatch):
    """Precedência da seção 5.4: a liberação de gênero não reabre o que o
    gate eleitoral já fechou. Capitão do Povo (Mateus & Cristiano) é uma
    das 5 faixas sertanejas da lista do item D."""
    pipeline = _import_pipeline_with_fake_dependencies(monkeypatch)
    metadados = _Metadados(musica="Capitão do Povo", artista="Mateus & Cristiano",
                            is_flashback=False, genero="Sertanejo")
    registrar = Mock()

    with patch.object(pipeline.intelligence, "analisar", return_value=metadados), \
         patch.object(pipeline.database, "registrar_pedido", registrar):
        resultado = pipeline.processar_pedido("5511999999999", texto="toca Capitão do Povo")

    assert resultado["sucesso"] is False
    assert resultado["mensagem"] == pipeline.luzia.MSG_ELEITORAL
    registrar.assert_called_once_with(
        "5511999999999", "Mateus & Cristiano", "Capitão do Povo",
        sucesso=False, motivo_rejeicao="eleitoral", genero="Sertanejo", canal="texto",
    )


def test_sertanejo_inapropriado_e_recusado(monkeypatch):
    """A liberação de gênero não vence is_apropriado=False."""
    pipeline = _import_pipeline_with_fake_dependencies(monkeypatch)
    metadados = _Metadados(musica="Evidências", artista="Chitãozinho e Xororó",
                            genero="sertanejo", is_apropriado=False)
    registrar = Mock()

    with patch.object(pipeline.intelligence, "analisar", return_value=metadados), \
         patch.object(pipeline.database, "registrar_pedido", registrar):
        resultado = pipeline.processar_pedido("5511999999999", texto="toca Evidências, seus mané")

    assert resultado["sucesso"] is False
    registrar.assert_called_once_with(
        "5511999999999", "Chitãozinho e Xororó", "Evidências",
        sucesso=False, motivo_rejeicao="inapropriado", genero="sertanejo", canal="texto",
    )


def test_racionais_mcs_fora_das_cinco_faixas_e_aceito(monkeypatch):
    """Racionais MC's é a exceção explícita do perfil para rap nacional —
    o classificador real devolveria is_flashback=True para eles (não é a
    liberação de gênero do item A que resolve isso, é o is_flashback)."""
    pipeline = _import_pipeline_with_fake_dependencies(monkeypatch)
    metadados = _Metadados(musica="Vida Loka", artista="Racionais MC's",
                            is_flashback=True, genero="rap nacional")

    with patch.object(pipeline.intelligence, "analisar", return_value=metadados), \
         patch.object(pipeline.database, "verificar_cooldown", return_value=True), \
         patch.object(pipeline.canal_voz, "avaliar", return_value=(False, False)), \
         patch.object(pipeline.database, "buscar_musica", return_value="/acervo/musica.mp3"), \
         patch.object(pipeline.database, "registrar_pedido"), \
         patch.object(pipeline, "queue_watcher") as fake_queue, \
         patch.object(pipeline, "shutil"):
        fake_queue.enfileirar.return_value = "/fila/musica.mp3"
        resultado = pipeline.processar_pedido("5511999999999", texto="toca Vida Loka Racionais")

    assert resultado["sucesso"] is True


def test_racionais_mcs_nas_cinco_faixas_e_recusado_eleitoral(monkeypatch):
    pipeline = _import_pipeline_with_fake_dependencies(monkeypatch)
    metadados = _Metadados(musica="Negro Drama", artista="Racionais MC's",
                            is_flashback=False, genero="rap nacional")
    registrar = Mock()

    with patch.object(pipeline.intelligence, "analisar", return_value=metadados), \
         patch.object(pipeline.database, "registrar_pedido", registrar):
        resultado = pipeline.processar_pedido("5511999999999", texto="toca Negro Drama Racionais")

    assert resultado["sucesso"] is False
    assert resultado["mensagem"] == pipeline.luzia.MSG_ELEITORAL
