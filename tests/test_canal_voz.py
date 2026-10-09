import importlib
import sys
import types
from datetime import datetime, timedelta
from unittest.mock import Mock


def _import_canal_voz_with_fake_psycopg2(monkeypatch, **env):
    """
    Importa core.canal_voz (e, por tabela, core.database) sem psycopg2
    instalado, no mesmo padrão de fake de sys.modules que
    tests/test_pipeline_eleitoral.py já usa no repositório.

    `env` define variáveis de ambiente antes do import, para exercer as
    constantes de módulo (CANAL_VOZ_ATIVADO, CANAL_TEXTO_MAX, ...), que são
    lidas uma vez na importação — o mesmo padrão de DISABLE_COOLDOWN em
    core/pipeline.py.
    """
    for nome, valor in env.items():
        monkeypatch.setenv(nome, valor)

    fake_psycopg2 = types.ModuleType("psycopg2")
    fake_psycopg2.extensions = types.SimpleNamespace(connection=object)
    fake_psycopg2_extras = types.ModuleType("psycopg2.extras")

    monkeypatch.setitem(sys.modules, "psycopg2", fake_psycopg2)
    monkeypatch.setitem(sys.modules, "psycopg2.extras", fake_psycopg2_extras)

    sys.modules.pop("core.canal_voz", None)
    sys.modules.pop("core.database", None)

    return importlib.import_module("core.canal_voz")


def _agora_menos(minutos: int) -> datetime:
    return datetime.now() - timedelta(minutes=minutos)


# --- Sequências do fold (seção 8.1) ---


def test_tres_textos_seguidos_bloqueiam(monkeypatch):
    canal_voz = _import_canal_voz_with_fake_psycopg2(monkeypatch)
    historico = [
        (_agora_menos(30), "texto"),
        (_agora_menos(20), "texto"),
        (_agora_menos(10), "texto"),
    ]
    monkeypatch.setattr(canal_voz.database, "pedidos_atendidos_por_canal", Mock(return_value=historico))

    assert canal_voz.bloqueado("5511999999999") is True


def test_sequencia_texto_texto_voz_texto_texto_nao_bloqueia(monkeypatch):
    canal_voz = _import_canal_voz_with_fake_psycopg2(monkeypatch)
    historico = [
        (_agora_menos(50), "texto"),
        (_agora_menos(40), "texto"),
        (_agora_menos(30), "voz"),   # zera o contador
        (_agora_menos(20), "texto"),
        (_agora_menos(10), "texto"),
    ]
    monkeypatch.setattr(canal_voz.database, "pedidos_atendidos_por_canal", Mock(return_value=historico))

    # só 2 textos desde a voz — não atingiu CANAL_TEXTO_MAX (3)
    assert canal_voz.bloqueado("5511999999999") is False


def test_tres_pedidos_por_voz_nunca_bloqueiam(monkeypatch):
    canal_voz = _import_canal_voz_with_fake_psycopg2(monkeypatch)
    historico = [
        (_agora_menos(30), "voz"),
        (_agora_menos(20), "voz"),
        (_agora_menos(10), "voz"),
    ]
    monkeypatch.setattr(canal_voz.database, "pedidos_atendidos_por_canal", Mock(return_value=historico))

    assert canal_voz.bloqueado("5511999999999") is False
    assert canal_voz.tem_historico_de_voz("5511999999999") is True


def test_dois_textos_atendidos_e_terceiro_e_processado(monkeypatch):
    """2 pedidos de texto atendidos: o fold ainda não fechou o ciclo."""
    canal_voz = _import_canal_voz_with_fake_psycopg2(monkeypatch)
    historico = [
        (_agora_menos(20), "texto"),
        (_agora_menos(10), "texto"),
    ]
    monkeypatch.setattr(canal_voz.database, "pedidos_atendidos_por_canal", Mock(return_value=historico))

    assert canal_voz.bloqueado("5511999999999") is False


# --- Linhas com None e "" no meio (coluna sem backfill / chamada sem canal) ---


def test_linhas_com_none_e_vazio_sao_ignoradas_pelo_fold(monkeypatch):
    canal_voz = _import_canal_voz_with_fake_psycopg2(monkeypatch)
    historico = [
        (_agora_menos(40), "texto"),
        (_agora_menos(35), None),      # linha antiga, sem coluna preenchida
        (_agora_menos(30), "texto"),
        (_agora_menos(25), ""),        # chamada que esqueceu de informar o canal
        (_agora_menos(10), "texto"),   # 3º texto de verdade: fecha o ciclo
    ]
    monkeypatch.setattr(canal_voz.database, "pedidos_atendidos_por_canal", Mock(return_value=historico))

    assert canal_voz.bloqueado("5511999999999") is True


def test_apenas_none_e_vazio_nunca_bloqueia(monkeypatch):
    canal_voz = _import_canal_voz_with_fake_psycopg2(monkeypatch)
    historico = [
        (_agora_menos(30), None),
        (_agora_menos(20), ""),
        (_agora_menos(10), "lixo"),
    ]
    monkeypatch.setattr(canal_voz.database, "pedidos_atendidos_por_canal", Mock(return_value=historico))

    assert canal_voz.bloqueado("5511999999999") is False
    assert canal_voz.tem_historico_de_voz("5511999999999") is False


# --- Expiração do bloqueio (60 minutos) ---


def test_bloqueio_de_dez_minutos_atras_ainda_esta_bloqueado(monkeypatch):
    canal_voz = _import_canal_voz_with_fake_psycopg2(monkeypatch)
    historico = [
        (_agora_menos(30), "texto"),
        (_agora_menos(20), "texto"),
        (_agora_menos(10), "texto"),  # fechou o ciclo há 10 min; bloqueio dura 60 min
    ]
    monkeypatch.setattr(canal_voz.database, "pedidos_atendidos_por_canal", Mock(return_value=historico))

    assert canal_voz.bloqueado("5511999999999") is True


def test_bloqueio_de_sessenta_e_um_minutos_atras_esta_liberado(monkeypatch):
    canal_voz = _import_canal_voz_with_fake_psycopg2(monkeypatch)
    historico = [
        (_agora_menos(81), "texto"),
        (_agora_menos(71), "texto"),
        (_agora_menos(61), "texto"),  # fechou o ciclo há 61 min; bloqueio de 60 min já expirou
    ]
    monkeypatch.setattr(canal_voz.database, "pedidos_atendidos_por_canal", Mock(return_value=historico))

    assert canal_voz.bloqueado("5511999999999") is False


# --- CANAL_VOZ_ATIVADO=false desliga o gate sem consultar o banco ---


def test_canal_voz_desativado_nao_bloqueia_e_nao_consulta_banco(monkeypatch):
    canal_voz = _import_canal_voz_with_fake_psycopg2(monkeypatch, CANAL_VOZ_ATIVADO="false")
    mock_consulta = Mock(side_effect=AssertionError("não deveria consultar o banco"))
    monkeypatch.setattr(canal_voz.database, "pedidos_atendidos_por_canal", mock_consulta)

    assert canal_voz.bloqueado("5511999999999") is False
    assert canal_voz.tem_historico_de_voz("5511999999999") is False
    assert canal_voz.avaliar("5511999999999") == (False, False)
    mock_consulta.assert_not_called()


# --- tem_historico_de_voz escolhe a variante de mensagem (seção 8.7) ---


def test_tem_historico_de_voz_falso_sem_nenhum_pedido_por_voz(monkeypatch):
    canal_voz = _import_canal_voz_with_fake_psycopg2(monkeypatch)
    historico = [(_agora_menos(10), "texto")]
    monkeypatch.setattr(canal_voz.database, "pedidos_atendidos_por_canal", Mock(return_value=historico))

    assert canal_voz.tem_historico_de_voz("5511999999999") is False


def test_tem_historico_de_voz_verdadeiro_com_pedido_por_voz_antigo(monkeypatch):
    canal_voz = _import_canal_voz_with_fake_psycopg2(monkeypatch)
    historico = [
        (_agora_menos(500), "voz"),
        (_agora_menos(10), "texto"),
    ]
    monkeypatch.setattr(canal_voz.database, "pedidos_atendidos_por_canal", Mock(return_value=historico))

    assert canal_voz.tem_historico_de_voz("5511999999999") is True


# --- Uma única consulta ao banco por pedido, via avaliar() ---


def test_avaliar_consulta_o_banco_uma_unica_vez(monkeypatch):
    canal_voz = _import_canal_voz_with_fake_psycopg2(monkeypatch)
    historico = [
        (_agora_menos(30), "texto"),
        (_agora_menos(20), "texto"),
        (_agora_menos(10), "texto"),
    ]
    mock_consulta = Mock(return_value=historico)
    monkeypatch.setattr(canal_voz.database, "pedidos_atendidos_por_canal", mock_consulta)

    bloq, teve_voz = canal_voz.avaliar("5511999999999")

    assert (bloq, teve_voz) == (True, False)
    mock_consulta.assert_called_once_with("5511999999999", canal_voz.CANAL_HISTORICO_DIAS)


def test_bloqueado_isolado_tambem_consulta_o_banco(monkeypatch):
    """Uso isolado de bloqueado() faz sua própria consulta (documentado no
    módulo); quem precisa das duas respostas para o mesmo pedido deve usar
    avaliar() para gastar uma única consulta."""
    canal_voz = _import_canal_voz_with_fake_psycopg2(monkeypatch)
    mock_consulta = Mock(return_value=[])
    monkeypatch.setattr(canal_voz.database, "pedidos_atendidos_por_canal", mock_consulta)

    canal_voz.bloqueado("5511999999999")

    mock_consulta.assert_called_once_with("5511999999999", canal_voz.CANAL_HISTORICO_DIAS)


# --- CANAL_HISTORICO_DIAS é repassado para a consulta ---


def test_historico_dias_customizado_e_repassado_a_consulta(monkeypatch):
    canal_voz = _import_canal_voz_with_fake_psycopg2(monkeypatch, CANAL_HISTORICO_DIAS="30")
    mock_consulta = Mock(return_value=[])
    monkeypatch.setattr(canal_voz.database, "pedidos_atendidos_por_canal", mock_consulta)

    canal_voz.avaliar("5511999999999")

    mock_consulta.assert_called_once_with("5511999999999", 30)
