"""
tests/test_pipeline_canal.py

Cobertura da C5: o gate de canal (item C, seção 8.1) dentro de
core/pipeline.py. Segue o padrão de tests/test_pipeline_eleitoral.py — helper
de import com fakes em sys.modules, _Metadados, database mockado. O ponto de
controle é database.pedidos_atendidos_por_canal, mockado com listas de
(datetime, canal); o fold em si (core/canal_voz.py) já tem cobertura própria
em tests/test_canal_voz.py — aqui o foco é a fiação do gate dentro do
pipeline (posição, canal= nos registros, mensagens, aguardando_pedido).
"""

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


def _rodar_texto(pipeline, historico, registrar=None, notificar=None):
    """Executa um pedido por texto com `historico` mockado em
    pedidos_atendidos_por_canal e o resto do pipeline liberado (cooldown ok,
    música já no acervo) — isola o efeito do gate de canal."""
    metadados = _Metadados()
    registrar = registrar if registrar is not None else Mock()
    with patch.object(pipeline.intelligence, "analisar", return_value=metadados), \
         patch.object(pipeline.database, "verificar_cooldown", return_value=True), \
         patch.object(pipeline.database, "pedidos_atendidos_por_canal", return_value=historico), \
         patch.object(pipeline.database, "buscar_musica", return_value="/acervo/musica.mp3"), \
         patch.object(pipeline.database, "registrar_pedido", registrar), \
         patch.object(pipeline, "queue_watcher") as fake_queue, \
         patch.object(pipeline, "shutil"):
        fake_queue.enfileirar.return_value = "/fila/musica.mp3"
        resultado = pipeline.processar_pedido(
            "5511999999999", texto="toca Evidências", notificar=notificar
        )
    return resultado, registrar


def test_dois_atendidos_por_texto_terceiro_por_texto_e_processado(monkeypatch):
    """2 pedidos de texto atendidos no histórico + este (3º, ainda não
    registrado) não bloqueia — o fold só bloqueia quando o histórico JÁ
    contém 3 atendidos por texto."""
    pipeline = _import_pipeline_with_fake_dependencies(monkeypatch)
    agora = datetime.now()
    historico = [
        (agora - timedelta(hours=2), "texto"),
        (agora - timedelta(hours=1), "texto"),
    ]
    resultado, registrar = _rodar_texto(pipeline, historico)

    assert resultado["sucesso"] is True
    # Fecha o ciclo: o próprio registro de sucesso deste pedido entra com canal="texto".
    registrar.assert_called_once_with(
        "5511999999999", "Chitãozinho e Xororó", "Evidências",
        genero="Sertanejo", canal="texto",
    )


def test_tres_atendidos_por_texto_terceiro_ha_dez_minutos_recusa_apenas_voz(monkeypatch):
    """3 atendidos por texto, o 3º há 10 min → dentro do bloqueio de 60 min:
    recusa apenas_voz (sem histórico de voz), aguardando_pedido=True."""
    pipeline = _import_pipeline_with_fake_dependencies(monkeypatch)
    agora = datetime.now()
    historico = [
        (agora - timedelta(hours=3), "texto"),
        (agora - timedelta(hours=2), "texto"),
        (agora - timedelta(minutes=10), "texto"),
    ]
    registrar = Mock()
    resultado, registrar = _rodar_texto(pipeline, historico, registrar=registrar)

    assert resultado["sucesso"] is False
    assert resultado["aguardando_pedido"] is True
    assert resultado["mensagem"] == pipeline.luzia.mensagem(
        "apenas_voz", pipeline.composer._FALLBACK_APENAS_VOZ
    )
    registrar.assert_called_once_with(
        "5511999999999", "Chitãozinho e Xororó", "Evidências",
        sucesso=False, motivo_rejeicao="apenas_voz", genero="Sertanejo", canal="texto",
    )


def test_mesmo_cenario_de_bloqueio_mas_com_path_ogg_e_processado(monkeypatch, tmp_path):
    """O mesmo histórico de bloqueio não afeta quem está mandando voz — o
    gate só vale para canal == "texto"; path_ogg (voz) nunca é bloqueado."""
    pipeline = _import_pipeline_with_fake_dependencies(monkeypatch)
    path_ogg = tmp_path / "audio.ogg"
    path_ogg.write_bytes(b"fake")
    agora = datetime.now()
    historico = [
        (agora - timedelta(hours=3), "texto"),
        (agora - timedelta(hours=2), "texto"),
        (agora - timedelta(minutes=10), "texto"),
    ]
    metadados = _Metadados()
    registrar = Mock()

    with patch.object(pipeline.stt, "transcrever", return_value="toca Evidências"), \
         patch.object(pipeline.intelligence, "analisar", return_value=metadados), \
         patch.object(pipeline.database, "verificar_cooldown", return_value=True), \
         patch.object(pipeline.database, "pedidos_atendidos_por_canal", return_value=historico), \
         patch.object(pipeline.database, "buscar_musica", return_value="/acervo/musica.mp3"), \
         patch.object(pipeline.database, "registrar_pedido", registrar), \
         patch.object(pipeline, "audio_mixer") as fake_mixer, \
         patch.object(pipeline, "queue_watcher") as fake_queue, \
         patch.object(pipeline, "shutil"):
        fake_mixer.mixar.return_value = "/tmp/mixado.mp3"
        fake_queue.enfileirar.return_value = "/fila/musica.mp3"
        resultado = pipeline.processar_pedido("5511999999999", path_ogg=str(path_ogg))

    assert resultado["sucesso"] is True
    registrar.assert_called_once_with(
        "5511999999999", "Chitãozinho e Xororó", "Evidências",
        genero="Sertanejo", canal="voz",
    )


def test_terceiro_pedido_ha_sessenta_e_um_minutos_e_liberado(monkeypatch):
    """Bloqueio de 60 min já expirado (fechou há 61 min) → liberado."""
    pipeline = _import_pipeline_with_fake_dependencies(monkeypatch)
    agora = datetime.now()
    historico = [
        (agora - timedelta(hours=3), "texto"),
        (agora - timedelta(hours=2), "texto"),
        (agora - timedelta(minutes=61), "texto"),
    ]
    resultado, _ = _rodar_texto(pipeline, historico)

    assert resultado["sucesso"] is True


def test_texto_texto_voz_texto_texto_nao_bloqueia(monkeypatch):
    """Um atendido por voz no meio zera o contador — os dois textos
    seguintes não chegam a 3."""
    pipeline = _import_pipeline_with_fake_dependencies(monkeypatch)
    agora = datetime.now()
    historico = [
        (agora - timedelta(hours=5), "texto"),
        (agora - timedelta(hours=4), "texto"),
        (agora - timedelta(hours=3), "voz"),
        (agora - timedelta(hours=2), "texto"),
        (agora - timedelta(hours=1), "texto"),
    ]
    resultado, _ = _rodar_texto(pipeline, historico)

    assert resultado["sucesso"] is True


def test_tres_atendidos_por_voz_libera_texto(monkeypatch):
    """3 atendidos por voz não incrementam o contador de texto — liberado."""
    pipeline = _import_pipeline_with_fake_dependencies(monkeypatch)
    agora = datetime.now()
    historico = [
        (agora - timedelta(hours=3), "voz"),
        (agora - timedelta(hours=2), "voz"),
        (agora - timedelta(hours=1), "voz"),
    ]
    resultado, _ = _rodar_texto(pipeline, historico)

    assert resultado["sucesso"] is True


def test_linhas_com_canal_nulo_sao_ignoradas_pelo_fold(monkeypatch):
    """canal IS NULL (ou "") no meio do histórico não conta como texto nem
    como voz — só os 3 "texto" reais fecham o ciclo."""
    pipeline = _import_pipeline_with_fake_dependencies(monkeypatch)
    agora = datetime.now()
    historico = [
        (agora - timedelta(hours=5), None),
        (agora - timedelta(hours=4), "texto"),
        (agora - timedelta(hours=3), ""),
        (agora - timedelta(hours=2), "texto"),
        (agora - timedelta(minutes=10), "texto"),
    ]
    resultado, registrar = _rodar_texto(pipeline, historico)

    assert resultado["sucesso"] is False
    assert resultado["aguardando_pedido"] is True
    registrar.assert_called_once_with(
        "5511999999999", "Chitãozinho e Xororó", "Evidências",
        sucesso=False, motivo_rejeicao="apenas_voz", genero="Sertanejo", canal="texto",
    )


def test_sem_historico_de_voz_usa_mensagem_apenas_voz(monkeypatch):
    """Bloqueado e nunca mandou voz → situação apenas_voz (sem "retorno")."""
    pipeline = _import_pipeline_with_fake_dependencies(monkeypatch)
    agora = datetime.now()
    historico = [
        (agora - timedelta(hours=3), "texto"),
        (agora - timedelta(hours=2), "texto"),
        (agora - timedelta(minutes=10), "texto"),
    ]
    resultado, _ = _rodar_texto(pipeline, historico)

    assert resultado["mensagem"] == pipeline.luzia.mensagem(
        "apenas_voz", pipeline.composer._FALLBACK_APENAS_VOZ
    )


def test_com_historico_de_voz_usa_mensagem_apenas_voz_retorno(monkeypatch):
    """Bloqueado, mas já mandou voz alguma vez no histórico (antes do ciclo
    de bloqueio atual) → situação apenas_voz_retorno."""
    pipeline = _import_pipeline_with_fake_dependencies(monkeypatch)
    agora = datetime.now()
    historico = [
        (agora - timedelta(days=5), "voz"),
        (agora - timedelta(hours=3), "texto"),
        (agora - timedelta(hours=2), "texto"),
        (agora - timedelta(minutes=10), "texto"),
    ]
    resultado, registrar = _rodar_texto(pipeline, historico)

    assert resultado["sucesso"] is False
    assert resultado["mensagem"] == pipeline.luzia.mensagem(
        "apenas_voz_retorno", pipeline.composer._FALLBACK_APENAS_VOZ_RETORNO
    )
    registrar.assert_called_once_with(
        "5511999999999", "Chitãozinho e Xororó", "Evidências",
        sucesso=False, motivo_rejeicao="apenas_voz", genero="Sertanejo", canal="texto",
    )


def test_canal_voz_ativado_false_deixa_gate_inerte(monkeypatch):
    """CANAL_VOZ_ATIVADO=false desliga o gate inteiro: mesmo com histórico de
    bloqueio, o pedido é processado normalmente (seção 10 da spec).

    O pacote `core` guarda `canal_voz` como atributo desde a primeira vez que
    algum teste o importou nesta sessão (mecanismo padrão de `from X import Y`
    do Python); popular `sys.modules["core.canal_voz"]` antes do próximo
    import não força reexecução do módulo, então uma env var lida só no
    import (`CANAL_VOZ_ATIVADO`) não teria efeito aqui. Por isso o teste
    desativa a flag diretamente no objeto já carregado — o mesmo efeito que
    `CANAL_VOZ_ATIVADO=false` produziria num processo novo — e confirma que o
    gate do pipeline respeita o que `canal_voz.avaliar` disser."""
    pipeline = _import_pipeline_with_fake_dependencies(monkeypatch)
    monkeypatch.setattr(pipeline.canal_voz, "CANAL_VOZ_ATIVADO", False)
    agora = datetime.now()
    historico = [
        (agora - timedelta(hours=3), "texto"),
        (agora - timedelta(hours=2), "texto"),
        (agora - timedelta(minutes=10), "texto"),
    ]
    resultado, _ = _rodar_texto(pipeline, historico)

    assert resultado["sucesso"] is True


def test_gate_consulta_pedidos_atendidos_por_canal_com_numero_e_janela(monkeypatch):
    """Confirma a fiação: o gate chama database.pedidos_atendidos_por_canal
    com o número do ouvinte e a janela configurada em canal_voz
    (CANAL_HISTORICO_DIAS) — não reimplementa o fold, delega para canal_voz."""
    pipeline = _import_pipeline_with_fake_dependencies(monkeypatch)
    consulta = Mock(return_value=[])
    metadados = _Metadados()

    with patch.object(pipeline.intelligence, "analisar", return_value=metadados), \
         patch.object(pipeline.database, "verificar_cooldown", return_value=True), \
         patch.object(pipeline.database, "pedidos_atendidos_por_canal", consulta), \
         patch.object(pipeline.database, "buscar_musica", return_value="/acervo/musica.mp3"), \
         patch.object(pipeline.database, "registrar_pedido"), \
         patch.object(pipeline, "queue_watcher") as fake_queue, \
         patch.object(pipeline, "shutil"):
        fake_queue.enfileirar.return_value = "/fila/musica.mp3"
        pipeline.processar_pedido("5511999999999", texto="toca Evidências")

    consulta.assert_called_once_with("5511999999999", pipeline.canal_voz.CANAL_HISTORICO_DIAS)
