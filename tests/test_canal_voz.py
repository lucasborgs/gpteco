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


# --- Janela deslizante de contagem (CANAL_JANELA_MIN) -----------------------
#
# Antes desta janela o contador só zerava num pedido por voz, então textos
# atendidos somavam para sempre dentro dos 90 dias de histórico: quem pedia
# uma música por texto por semana topava no bloqueio na terceira semana. A
# regra existe para conter rajada de pedidos por texto, não uso esparso.


def test_tres_textos_espalhados_fora_da_janela_nao_bloqueiam(monkeypatch):
    """O caso que motivou a janela: 3 textos atendidos, nenhum par dentro de
    60 minutos do outro."""
    canal_voz = _import_canal_voz_with_fake_psycopg2(monkeypatch)
    historico = [
        (_agora_menos(60 * 24 * 14), "texto"),  # 14 dias atrás
        (_agora_menos(60 * 24 * 7), "texto"),   # 7 dias atrás
        (_agora_menos(5), "texto"),             # agora
    ]
    monkeypatch.setattr(canal_voz.database, "pedidos_atendidos_por_canal", Mock(return_value=historico))

    assert canal_voz.bloqueado("5511999999999") is False


def test_dois_na_janela_mais_um_antigo_nao_bloqueia(monkeypatch):
    """O terceiro mais antigo saiu da janela no instante do pedido novo —
    sobram 2 contando, que é abaixo de CANAL_TEXTO_MAX."""
    canal_voz = _import_canal_voz_with_fake_psycopg2(monkeypatch)
    historico = [
        (_agora_menos(90), "texto"),  # fora da janela do pedido de 10 min atrás
        (_agora_menos(40), "texto"),
        (_agora_menos(10), "texto"),
    ]
    monkeypatch.setattr(canal_voz.database, "pedidos_atendidos_por_canal", Mock(return_value=historico))

    assert canal_voz.bloqueado("5511999999999") is False


def test_tres_textos_dentro_da_janela_ainda_bloqueiam(monkeypatch):
    """A janela não afrouxa o caso que a regra quer pegar: rajada."""
    canal_voz = _import_canal_voz_with_fake_psycopg2(monkeypatch)
    historico = [
        (_agora_menos(50), "texto"),
        (_agora_menos(30), "texto"),
        (_agora_menos(2), "texto"),
    ]
    monkeypatch.setattr(canal_voz.database, "pedidos_atendidos_por_canal", Mock(return_value=historico))

    assert canal_voz.bloqueado("5511999999999") is True


def test_pedido_exatamente_na_borda_da_janela_nao_conta(monkeypatch):
    """Corte é `> timestamp - janela`: 60 minutos exatos já saiu. Fixa a
    borda para ela não virar ambígua numa mudança futura."""
    canal_voz = _import_canal_voz_with_fake_psycopg2(monkeypatch)
    historico = [
        (_agora_menos(70), "texto"),
        (_agora_menos(65), "texto"),
        (_agora_menos(5), "texto"),  # 60 e 65 min de distância dos dois anteriores
    ]
    monkeypatch.setattr(canal_voz.database, "pedidos_atendidos_por_canal", Mock(return_value=historico))

    assert canal_voz.bloqueado("5511999999999") is False


def test_janela_customizada_e_respeitada(monkeypatch):
    """Com janela de 24h, os mesmos 3 textos espalhados voltam a bloquear —
    confirma que a janela é o que decide, não o acaso dos timestamps."""
    canal_voz = _import_canal_voz_with_fake_psycopg2(monkeypatch, CANAL_JANELA_MIN="1440")
    historico = [
        (_agora_menos(600), "texto"),
        (_agora_menos(300), "texto"),
        (_agora_menos(10), "texto"),
    ]
    monkeypatch.setattr(canal_voz.database, "pedidos_atendidos_por_canal", Mock(return_value=historico))

    assert canal_voz.bloqueado("5511999999999") is True


def test_bloqueio_expirado_nao_reabre_ciclo_antigo(monkeypatch):
    """Bloqueio de 2h atrás já expirou, e os textos que o fecharam não podem
    voltar a contar: o ouvinte recomeça do zero."""
    canal_voz = _import_canal_voz_with_fake_psycopg2(monkeypatch)
    historico = [
        (_agora_menos(140), "texto"),
        (_agora_menos(130), "texto"),
        (_agora_menos(120), "texto"),  # fechou o ciclo; bloqueio venceu 60 min atrás
        (_agora_menos(5), "texto"),    # 1º de um ciclo novo
    ]
    monkeypatch.setattr(canal_voz.database, "pedidos_atendidos_por_canal", Mock(return_value=historico))

    assert canal_voz.bloqueado("5511999999999") is False


def test_voz_antiga_nao_reaparece_como_credito(monkeypatch):
    """Voz zera o ciclo e marca o histórico; os 3 textos depois dela, dentro
    da janela, fecham normalmente."""
    canal_voz = _import_canal_voz_with_fake_psycopg2(monkeypatch)
    historico = [
        (_agora_menos(60 * 24 * 30), "voz"),  # 30 dias atrás
        (_agora_menos(40), "texto"),
        (_agora_menos(20), "texto"),
        (_agora_menos(10), "texto"),
    ]
    monkeypatch.setattr(canal_voz.database, "pedidos_atendidos_por_canal", Mock(return_value=historico))

    bloq, teve_voz = canal_voz.avaliar("5511999999999")
    assert bloq is True
    assert teve_voz is True
