import importlib

from core import repertorio


def test_genero_liberado_sertanejo_exato():
    assert repertorio.genero_liberado("sertanejo") is True


def test_genero_liberado_sertanejo_universitario_casa_por_prefixo_de_palavra():
    assert repertorio.genero_liberado("Sertanejo Universitário") is True


def test_genero_liberado_ignora_caixa():
    assert repertorio.genero_liberado("SERTANEJO") is True


def test_genero_nao_liberado_rock():
    assert repertorio.genero_liberado("rock") is False


def test_genero_vazio_nao_liberado():
    assert repertorio.genero_liberado("") is False
    assert repertorio.genero_liberado(None) is False


def test_genero_liberado_nao_casa_palavra_diferente_com_prefixo_textual_igual():
    """'sertanejão' compartilha o prefixo textual 'sertanej' com 'sertanejo',
    mas é outra palavra — o casamento é por prefixo de PALAVRA, não de texto."""
    assert repertorio.genero_liberado("sertanejão") is False


def test_lista_vazia_em_generos_sempre_aceitos_desliga_a_liberacao(monkeypatch):
    """GENEROS_SEMPRE_ACEITOS="" desliga o item A em código (seção 10 da
    spec): nenhum gênero é liberado incondicionalmente, nem sertanejo."""
    monkeypatch.setenv("GENEROS_SEMPRE_ACEITOS", "")
    mod = importlib.reload(repertorio)
    try:
        assert mod.GENEROS_SEMPRE_ACEITOS == frozenset()
        assert mod.genero_liberado("sertanejo") is False
        assert mod.genero_liberado("rock") is False
    finally:
        # GENEROS_SEMPRE_ACEITOS é lido em tempo de import (seção 5.2 da spec:
        # mudar a variável exige reiniciar o processo). Restauramos o padrão
        # recarregando de novo sem a variável, para não contaminar outros
        # testes do processo (ex.: test_pipeline_sertanejo.py, que espera o
        # padrão "sertanejo").
        monkeypatch.delenv("GENEROS_SEMPRE_ACEITOS", raising=False)
        importlib.reload(repertorio)


def test_padrao_sem_variavel_no_ambiente_e_sertanejo(monkeypatch):
    monkeypatch.delenv("GENEROS_SEMPRE_ACEITOS", raising=False)
    mod = importlib.reload(repertorio)
    assert mod.GENEROS_SEMPRE_ACEITOS == frozenset({"sertanejo"})
    assert mod.genero_liberado("sertanejo") is True
