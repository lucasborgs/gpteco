import threading
import time
from unittest.mock import Mock, patch

import pytest

from core import yt_throttle


@pytest.fixture(autouse=True)
def _estado_limpo():
    """Reseta o estado de módulo antes e depois de cada teste — `_ultimo_fim`
    e o contador de fila são globais e, sem isso, a ordem dos testes mudaria
    o resultado."""
    yt_throttle._resetar()
    yield
    yt_throttle._resetar()


def test_primeira_chamada_nao_espera():
    dormir = Mock()
    orcamento = yt_throttle.Orcamento()

    with patch.object(yt_throttle, "_dormir", dormir):
        with yt_throttle.janela("busca", orcamento):
            pass

    dormir.assert_not_called()
    assert orcamento.gasto_s == 0.0


def test_busca_logo_apos_outra_chamada_espera_entre_30_e_39s():
    relogio = Mock(side_effect=[100.0, 100.0, 100.0])
    dormir = Mock()
    orcamento = yt_throttle.Orcamento()

    with patch.object(yt_throttle, "_agora", relogio), patch.object(yt_throttle, "_dormir", dormir):
        with yt_throttle.janela("busca", orcamento):
            pass
        # Fim da primeira chamada: monotonic() chamado de novo no finally.
        with yt_throttle.janela("busca", orcamento):
            pass

    assert dormir.call_count == 1
    (espera,) = dormir.call_args[0]
    assert 30.0 <= espera <= 39.0
    assert orcamento.gasto_s == pytest.approx(espera)


def test_tentativa_depois_de_busca_espera_entre_8_e_10_4s():
    dormir = Mock()
    orcamento = yt_throttle.Orcamento()

    # _agora avança 0s entre o fim da busca e o início da tentativa, para o
    # intervalo completo da tentativa (8s + jitter) precisar ser dormido.
    with patch.object(yt_throttle, "_agora", Mock(return_value=200.0)), patch.object(
        yt_throttle, "_dormir", dormir
    ):
        with yt_throttle.janela("busca", orcamento):
            pass
        with yt_throttle.janela("tentativa", orcamento):
            pass

    assert dormir.call_count == 1
    (espera,) = dormir.call_args[0]
    assert 8.0 <= espera <= 10.4


def test_espera_acumulada_acima_do_teto_levanta_espera_excedida():
    orcamento = yt_throttle.Orcamento(gasto_s=yt_throttle.MAX_ESPERA_S - 1)
    dormir = Mock()

    with patch.object(yt_throttle, "_agora", Mock(return_value=0.0)), patch.object(
        yt_throttle, "_dormir", dormir
    ):
        with yt_throttle.janela("busca", yt_throttle.Orcamento()):
            pass
        with pytest.raises(yt_throttle.EsperaExcedida):
            with yt_throttle.janela("busca", orcamento):
                pass

    dormir.assert_not_called()


def test_quinto_pedido_aguardando_levanta_fila_cheia_sem_dormir():
    """Com YT_THROTTLE_MAX_FILA pedidos já "aguardando" — um de fato
    executando (dentro do `yield`, com o lock de serialização preso) e os
    demais bloqueados tentando adquirir esse mesmo lock —, o próximo deve
    recusar na hora, sem tentar dormir."""
    primeira_dentro = threading.Event()
    liberar = threading.Event()
    # `_dormir` mockado para TODAS as threads desta janela de tempo — sem
    # isso, as threads de fila, ao serem liberadas, dormiriam ~30s de
    # verdade (uma por vez, serializadas pelo próprio lock) antes do teste
    # conseguir dar join.
    dormir = Mock()

    def ocupar_execucao():
        with yt_throttle.janela("busca", yt_throttle.Orcamento()):
            primeira_dentro.set()
            liberar.wait()

    def ocupar_fila():
        with yt_throttle.janela("busca", yt_throttle.Orcamento()):
            pass

    with patch.object(yt_throttle, "_dormir", dormir):
        thread_execucao = threading.Thread(target=ocupar_execucao)
        thread_execucao.start()
        assert primeira_dentro.wait(timeout=2.0)

        threads_fila = [
            threading.Thread(target=ocupar_fila) for _ in range(yt_throttle.MAX_FILA - 1)
        ]
        for t in threads_fila:
            t.start()

        # Espera as MAX_FILA-1 threads ficarem bloqueadas tentando adquirir
        # a janela (presas no lock de serialização, atrás da que já
        # executa) — juntas, somam MAX_FILA "aguardando".
        for _ in range(300):
            if yt_throttle._fila_contador >= yt_throttle.MAX_FILA:
                break
            time.sleep(0.01)
        assert yt_throttle._fila_contador >= yt_throttle.MAX_FILA

        chamadas_antes_da_recusa = dormir.call_count
        try:
            with pytest.raises(yt_throttle.FilaCheia):
                with yt_throttle.janela("busca", yt_throttle.Orcamento()):
                    pass  # não deve nem chegar aqui
            # A recusa em si não chamou `_dormir` — ela acontece antes de
            # entrar no lock de serialização. As chamadas das threads de
            # fundo (liberadas só abaixo, no cleanup) não contam aqui.
            chamadas_da_recusa = dormir.call_count - chamadas_antes_da_recusa
        finally:
            liberar.set()
            thread_execucao.join()
            for t in threads_fila:
                t.join()

    assert chamadas_da_recusa == 0


def test_throttle_desativado_nao_espera():
    dormir = Mock()
    orcamento = yt_throttle.Orcamento()

    with patch.object(yt_throttle, "ATIVADO", False), patch.object(yt_throttle, "_dormir", dormir):
        with yt_throttle.janela("busca", orcamento):
            pass
        with yt_throttle.janela("tentativa", orcamento):
            pass

    dormir.assert_not_called()
    assert orcamento.gasto_s == 0.0
    assert yt_throttle.espera_estimada("busca") == 0.0


def test_duas_threads_nunca_dentro_da_janela_ao_mesmo_tempo():
    n_threads = 5
    dentro = 0
    maximo_observado = 0
    trava = threading.Lock()
    erros: list[Exception] = []

    def tarefa():
        nonlocal dentro, maximo_observado
        try:
            with yt_throttle.janela("busca", yt_throttle.Orcamento()):
                with trava:
                    dentro += 1
                    maximo_observado = max(maximo_observado, dentro)
                # Simula o tempo da chamada real ao YouTube.
                threading.Event().wait(0.05)
                with trava:
                    dentro -= 1
        except Exception as erro:  # pragma: no cover - não esperado aqui
            erros.append(erro)

    # MAX_FILA alto o bastante para nenhuma das `n_threads` ser recusada por
    # FilaCheia — este teste é sobre serialização, não sobre o limite de
    # fila (testado isoladamente em outro caso).
    with patch.object(yt_throttle, "BUSCA_S", 0.01), patch.object(
        yt_throttle, "JITTER_PCT", 0.0
    ), patch.object(yt_throttle, "MAX_FILA", n_threads):
        threads = [threading.Thread(target=tarefa) for _ in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    assert erros == []
    assert maximo_observado == 1


def test_espera_estimada_sem_chamada_anterior_e_sem_throttle_ativo():
    assert yt_throttle.espera_estimada("busca") == 0.0


def test_espera_estimada_reflete_tempo_restante():
    with patch.object(yt_throttle, "_agora", Mock(side_effect=[100.0, 110.0])):
        with yt_throttle.janela("busca", yt_throttle.Orcamento()):
            pass
        # 10s decorridos desde o fim da busca; faltam ao menos BUSCA_S - 10.
        estimativa = yt_throttle.espera_estimada("busca")

    assert estimativa >= yt_throttle.BUSCA_S - 10.0
