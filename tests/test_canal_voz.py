import importlib
import sys
import types
from datetime import datetime, timedelta
from unittest.mock import Mock

import pytest


def _import_canal_voz_with_fake_psycopg2(monkeypatch, **env):
    """
    Importa core.canal_voz (e, por tabela, core.database) sem psycopg2
    instalado, no mesmo padrão de fake de sys.modules que
    tests/test_pipeline_eleitoral.py já usa no repositório.

    `env` define variáveis de ambiente antes do import, para exercer as
    constantes de módulo (CANAL_VOZ_ATIVADO, CANAL_HISTORICO_DIAS), que são
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




@pytest.mark.parametrize("canais,esperado", [
    ([], False),
    (["texto"], False),
    (["texto", "texto"], True),
    (["texto"] * 10, True),
    (["voz", "voz"], False),
    (["texto", "texto", "voz"], False),
    (["texto", "texto", "voz", "texto"], False),
    (["texto", "voz", "texto", "texto"], True),
    ([None, "", "desconhecido"], False),
    (["texto", None, "", "texto"], True),
])
def test_convite_depende_dos_textos_atendidos_desde_a_ultima_voz(monkeypatch, canais, esperado):
    canal_voz = _import_canal_voz_with_fake_psycopg2(monkeypatch, CANAL_VOZ_ATIVADO="true")
    historico = [(_agora_menos(len(canais) - i), canal) for i, canal in enumerate(canais)]
    consulta = Mock(return_value=historico)
    monkeypatch.setattr(canal_voz.database, "pedidos_atendidos_por_canal", consulta)
    assert canal_voz.sugerir_voz("5511999999999") is esperado
    consulta.assert_called_once_with("5511999999999", canal_voz.CANAL_HISTORICO_DIAS)


def test_convite_desativado_nao_consulta_banco(monkeypatch):
    canal_voz = _import_canal_voz_with_fake_psycopg2(monkeypatch, CANAL_VOZ_ATIVADO="false")
    consulta = Mock(side_effect=AssertionError("não deve consultar"))
    monkeypatch.setattr(canal_voz.database, "pedidos_atendidos_por_canal", consulta)
    assert canal_voz.sugerir_voz("5511999999999") is False
    consulta.assert_not_called()


def test_configuracao_legada_de_bloqueio_e_ignorada(monkeypatch):
    canal_voz = _import_canal_voz_with_fake_psycopg2(
        monkeypatch, CANAL_VOZ_ATIVADO="true", CANAL_TEXTO_MAX="2",
        CANAL_BLOQUEIO_MIN="valor_antigo", CANAL_JANELA_MIN="valor_antigo",
    )
    consulta = Mock(return_value=[(_agora_menos(1), "texto")] * 3)
    monkeypatch.setattr(canal_voz.database, "pedidos_atendidos_por_canal", consulta)
    assert canal_voz.sugerir_voz("5511999999999") is True


def test_contagem_nao_expira_apos_uma_hora_nem_e_cacheada(monkeypatch):
    canal_voz = _import_canal_voz_with_fake_psycopg2(monkeypatch, CANAL_VOZ_ATIVADO="true")
    historico = [(_agora_menos(24 * 60), "texto"), (_agora_menos(6 * 60), "texto")]
    consulta = Mock(side_effect=[historico, historico + [(_agora_menos(1), "voz")]])
    monkeypatch.setattr(canal_voz.database, "pedidos_atendidos_por_canal", consulta)
    assert canal_voz.sugerir_voz("5511999999999") is True
    assert canal_voz.sugerir_voz("5511999999999") is False
    assert consulta.call_count == 2
