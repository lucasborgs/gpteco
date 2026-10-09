"""
tests/test_perfil_defasado.py

O assistente.md vive no PC do cliente e congela no estado em que foi criado:
num release que acrescente uma mensagem nova, o arquivo da rádio NÃO vai ter a
seção correspondente (não sobrescrevemos o arquivo dele, senão apagaríamos as
edições da rádio). Estes testes garantem que esse cenário degrada com
elegância, em vez de virar erro técnico.

É a regressão de um defeito real: `apenas_voz` e `apenas_voz_retorno` tinham
entrado em luzia._MSG_SLUG, que é estrito, e um perfil sem a seção levantava
AttributeError dentro do gate de canal. O ouvinte recebia o erro genérico em
vez do convite para mandar áudio, e o pedido era gravado DUAS vezes (uma como
apenas_voz, na linha anterior, e outra como erro_tecnico, no except).
"""

import importlib
import sys
import types
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

import pytest


# Perfil mínimo que passa no parser e contém TODAS as seções estritas
# (luzia._MSG_SLUG) mas NENHUMA das criadas depois da primeira entrega —
# é o assistente.md de um cliente que não foi atualizado.
_PERFIL_DEFASADO = """---
nome_radio: Luz FM
ano_maximo: 2010
versao: 1.0
---

# 💬 Mensagens fixas

## sucesso
Pedido de {musica} do {artista} anotado!

## saudacao
Oi! Qual música você quer ouvir?

## menu_pos_sucesso
Quer pedir outra?

## aguardando_pedido
Manda o nome da música e do artista.

## producao_ativado
Já avisei a produção.

## encerramento
Até mais!

## cooldown
Você já pediu uma música há pouco.

## inapropriado
Não consigo colocar essa no ar.

## eleitoral
Não posso colocar conteúdo eleitoral no ar.

## nao_repertorio
{musica} do {artista} não é do nosso repertório.

## nao_id
Não consegui identificar a música.

## confirmacao
Você quis dizer {musica} do {artista}?

## pilula_prefixo
*CURIOSIDADE:*
"""


@pytest.fixture
def perfil_defasado(tmp_path, monkeypatch):
    """Aponta ASSISTANT_PROFILE_PATH para um perfil sem as seções novas.

    luzia._load() resolve a variável a cada chamada e invalida o cache por
    troca de caminho, então não é preciso recarregar o módulo.
    """
    caminho = tmp_path / "assistente.md"
    caminho.write_text(_PERFIL_DEFASADO, encoding="utf-8")
    monkeypatch.setenv("ASSISTANT_PROFILE_PATH", str(caminho))
    return caminho


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
            "core.pipeline", "core.audio_mixer", "core.downloader",
            "core.database", "core.intelligence", "core.composer",
            "core.stt", "core.repertorio", "core.canal_voz",
        ):
            sys.modules.pop(mod, None)
        return importlib.import_module("core.pipeline")


class _Metadados:
    def __init__(self):
        self.is_pedido_musical = True
        self.musica = "Evidências"
        self.artista = "Chitãozinho e Xororó"
        self.is_flashback = True
        self.is_apropriado = True
        self.is_confiante = True
        self.is_pedido_explicito = False
        self.genero = "Sertanejo"


# --- O perfil defasado não derruba o composer ---------------------------------

@pytest.mark.parametrize("situacao", ["apenas_voz", "apenas_voz_retorno"])
def test_composer_usa_fallback_quando_slug_falta_no_perfil(
    monkeypatch, perfil_defasado, situacao
):
    pipeline = _import_pipeline_with_fake_dependencies(monkeypatch)
    composer = pipeline.composer

    # _client None força o caminho canned (sem chamar LLM no teste).
    with patch.object(composer, "_client", None):
        msg = composer.compor(situacao, {}, "toca Evidências")

    esperado = {
        "apenas_voz": composer._FALLBACK_APENAS_VOZ,
        "apenas_voz_retorno": composer._FALLBACK_APENAS_VOZ_RETORNO,
    }[situacao]
    assert msg == esperado
    assert msg  # não é string vazia


def test_composer_prefere_o_texto_do_perfil_quando_a_secao_existe(
    monkeypatch, tmp_path
):
    """O fallback é rede de segurança, não o caminho normal: com a seção
    presente, quem manda é o assistente.md (é assim que a rádio edita o tom)."""
    caminho = tmp_path / "assistente.md"
    caminho.write_text(
        _PERFIL_DEFASADO + "\n## apenas_voz\nFala comigo no áudio!\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("ASSISTANT_PROFILE_PATH", str(caminho))

    pipeline = _import_pipeline_with_fake_dependencies(monkeypatch)
    composer = pipeline.composer
    with patch.object(composer, "_client", None):
        msg = composer.compor("apenas_voz", {}, "toca Evidências")

    assert msg == "Fala comigo no áudio!"
    assert msg != composer._FALLBACK_APENAS_VOZ


# --- A mensagem de falha interna também vem do perfil ------------------------

def test_msg_erro_cai_no_fallback_quando_perfil_nao_tem_a_secao(
    monkeypatch, perfil_defasado
):
    pipeline = _import_pipeline_with_fake_dependencies(monkeypatch)
    assert pipeline._msg_erro() == pipeline._MSG_ERRO_FALLBACK


def test_msg_erro_vem_do_perfil_quando_a_secao_existe(monkeypatch, tmp_path):
    """A rádio pode suavizar o texto de falha sem rebuild — era constante fixa
    no código antes desta mudança."""
    caminho = tmp_path / "assistente.md"
    caminho.write_text(
        _PERFIL_DEFASADO + "\n## erro_tecnico\nDeu tilt aqui, manda de novo!\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("ASSISTANT_PROFILE_PATH", str(caminho))

    pipeline = _import_pipeline_with_fake_dependencies(monkeypatch)
    assert pipeline._msg_erro() == "Deu tilt aqui, manda de novo!"


def test_msg_erro_nao_fala_de_erro_tecnico_ao_ouvinte(monkeypatch):
    """O texto padrão é informal e não expõe jargão técnico."""
    pipeline = _import_pipeline_with_fake_dependencies(monkeypatch)
    msg = pipeline._msg_erro().lower()
    for jargao in ("erro", "falha", "técnico", "tecnico", "exception", "processar"):
        assert jargao not in msg, f"'{jargao}' não deveria aparecer: {msg!r}"


# --- Ponta a ponta: o gate de canal com perfil defasado ----------------------

def test_gate_de_canal_com_perfil_defasado_convida_e_registra_uma_vez(
    monkeypatch, perfil_defasado
):
    """O defeito original: o convite virava erro técnico e o pedido entrava
    duas vezes no painel (apenas_voz na linha 165 + erro_tecnico no except)."""
    pipeline = _import_pipeline_with_fake_dependencies(monkeypatch)
    agora = datetime.now()
    historico = [
        (agora - timedelta(hours=3), "texto"),
        (agora - timedelta(hours=2), "texto"),
        (agora - timedelta(minutes=10), "texto"),
    ]
    registrar = Mock()

    with patch.object(pipeline.intelligence, "analisar", return_value=_Metadados()), \
         patch.object(pipeline.database, "verificar_cooldown", return_value=True), \
         patch.object(pipeline.database, "pedidos_atendidos_por_canal", return_value=historico), \
         patch.object(pipeline.database, "buscar_musica", return_value="/acervo/musica.mp3"), \
         patch.object(pipeline.database, "registrar_pedido", registrar), \
         patch.object(pipeline.composer, "_client", None), \
         patch.object(pipeline, "queue_watcher") as fake_queue, \
         patch.object(pipeline, "shutil"):
        fake_queue.enfileirar.return_value = "/fila/musica.mp3"
        resultado = pipeline.processar_pedido("5511999999999", texto="toca Evidências")

    assert resultado["sucesso"] is False
    assert resultado["aguardando_pedido"] is True
    # O convite, não o texto de falha interna.
    assert resultado["mensagem"] == pipeline.composer._FALLBACK_APENAS_VOZ
    assert resultado["mensagem"] != pipeline._msg_erro()
    # UM registro, e como apenas_voz — não um apenas_voz seguido de erro_tecnico.
    registrar.assert_called_once_with(
        "5511999999999", "Chitãozinho e Xororó", "Evidências",
        sucesso=False, motivo_rejeicao="apenas_voz", genero="Sertanejo", canal="texto",
    )
