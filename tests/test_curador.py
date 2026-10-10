"""
tests/test_curador.py

Regressão de 2026-10-09: com PILULAS_MODELO apontando para um modelo de
raciocínio (gpt-6-luna), toda chamada morria com HTTP 400 —

    Unsupported value: 'temperature' does not support 0.35 with this model.
    Only the default (1) value is supported.

A falha é engolida por `except Exception: return None`, então nada aparecia
quebrado: as pílulas simplesmente paravam de ser geradas. Só continuavam
saindo as que já estavam no cache do banco (database.buscar_pilula), o que
escondeu o problema por completo.
"""

from unittest.mock import Mock, patch

import pytest

from core import curador


class _ErroTemperature(Exception):
    """Imita o 400 da OpenAI para um modelo que só aceita o temperature padrão."""
    def __str__(self):
        return (
            "Error code: 400 - {'error': {'message': \"Unsupported value: "
            "'temperature' does not support 0.35 with this model. Only the "
            "default (1) value is supported.\", 'param': 'temperature'}}"
        )


@pytest.fixture(autouse=True)
def _limpa_memoria_de_modelos():
    """_SEM_TEMPERATURE dura a vida do processo de propósito; nos testes não
    pode vazar de um caso para o outro."""
    curador._SEM_TEMPERATURE.clear()
    yield
    curador._SEM_TEMPERATURE.clear()


def _cliente_que_recusa_temperature():
    """Cliente falso que só aceita a chamada quando `temperature` não vem."""
    def create(**kwargs):
        if "temperature" in kwargs:
            raise _ErroTemperature()
        return "resposta-ok"

    cliente = Mock()
    cliente.chat.completions.create.side_effect = create
    return cliente


def test_mantem_temperature_no_modelo_que_aceita():
    """O valor baixo é o que segura a alucinação — não pode ser descartado
    por precaução num modelo que aceita o parâmetro."""
    cliente = Mock()
    cliente.chat.completions.create.return_value = "resposta-ok"

    with patch.object(curador, "_client", cliente):
        assert curador._completar("gpt-4o", 0.35, messages=[]) == "resposta-ok"

    assert cliente.chat.completions.create.call_count == 1
    assert cliente.chat.completions.create.call_args.kwargs["temperature"] == 0.35
    assert "gpt-4o" not in curador._SEM_TEMPERATURE


def test_repete_sem_temperature_quando_o_modelo_recusa():
    cliente = _cliente_que_recusa_temperature()

    with patch.object(curador, "_client", cliente):
        assert curador._completar("gpt-6-luna", 0.35, messages=[]) == "resposta-ok"

    assert cliente.chat.completions.create.call_count == 2
    primeira, segunda = cliente.chat.completions.create.call_args_list
    assert primeira.kwargs["temperature"] == 0.35
    assert "temperature" not in segunda.kwargs
    assert segunda.kwargs["model"] == "gpt-6-luna"


def test_nao_repete_a_descoberta_nas_chamadas_seguintes():
    """A primeira chamada custa uma tentativa perdida; as próximas não."""
    cliente = _cliente_que_recusa_temperature()

    with patch.object(curador, "_client", cliente):
        curador._completar("gpt-6-luna", 0.35, messages=[])
        cliente.chat.completions.create.reset_mock()
        curador._completar("gpt-6-luna", 0.5, messages=[])

    assert cliente.chat.completions.create.call_count == 1
    assert "temperature" not in cliente.chat.completions.create.call_args.kwargs


def test_erro_que_nao_e_de_temperature_sobe_sem_repetir():
    """Sem isto, qualquer falha (chave inválida, rate limit) viraria duas
    chamadas e o modelo entraria em _SEM_TEMPERATURE por engano."""
    cliente = Mock()
    cliente.chat.completions.create.side_effect = RuntimeError("rate limit exceeded")

    with patch.object(curador, "_client", cliente):
        with pytest.raises(RuntimeError, match="rate limit"):
            curador._completar("gpt-4o", 0.35, messages=[])

    assert cliente.chat.completions.create.call_count == 1
    assert "gpt-4o" not in curador._SEM_TEMPERATURE


def test_gerar_pilula_funciona_com_modelo_que_recusa_temperature():
    """Ponta a ponta do defeito: antes, isto devolvia None."""
    cliente = _cliente_que_recusa_temperature()
    resposta = Mock()
    resposta.choices = [
        Mock(message=Mock(content='{"texto": "Fato curioso.", "tem_certeza": true}'))
    ]

    def create(**kwargs):
        if "temperature" in kwargs:
            raise _ErroTemperature()
        return resposta

    cliente.chat.completions.create.side_effect = create

    with patch.object(curador, "_client", cliente), \
         patch.object(curador, "PILULAS_MODELO", "gpt-6-luna"):
        assert curador.gerar_pilula("Dead Fish", "Messias") == "Fato curioso."
