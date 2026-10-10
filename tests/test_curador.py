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

O tratamento do parâmetro em si mora em core/llm_compat.py e é testado em
tests/test_llm_compat.py. Aqui ficam as duas pontas do curador, que são o que
o ouvinte recebe.
"""

from unittest.mock import Mock, patch

import pytest

from core import curador, llm_compat


_ERRO_TEMPERATURE = (
    "Error code: 400 - {'error': {'message': \"Unsupported value: "
    "'temperature' does not support 0.35 with this model. Only the "
    "default (1) value is supported.\", 'param': 'temperature'}}"
)
_ERRO_MAX_TOKENS = (
    "Error code: 400 - {'error': {'message': \"Unsupported parameter: "
    "'max_tokens' is not supported with this model. Use "
    "'max_completion_tokens' instead.\", 'param': 'max_tokens'}}"
)


class _Erro400(Exception):
    def __init__(self, mensagem):
        self._mensagem = mensagem

    def __str__(self):
        return self._mensagem


@pytest.fixture(autouse=True)
def _limpa_memoria_de_modelos():
    llm_compat._SEM_TEMPERATURE.clear()
    llm_compat._SEM_MAX_TOKENS.clear()
    yield
    llm_compat._SEM_TEMPERATURE.clear()
    llm_compat._SEM_MAX_TOKENS.clear()


def _cliente_familia_gpt6(resposta):
    """Cliente falso com as duas recusas da família gpt-6, na ordem real."""
    def create(**kwargs):
        if "max_tokens" in kwargs:
            raise _Erro400(_ERRO_MAX_TOKENS)
        if "temperature" in kwargs:
            raise _Erro400(_ERRO_TEMPERATURE)
        return resposta

    cliente = Mock()
    cliente.chat.completions.create.side_effect = create
    return cliente


def test_gerar_pilula_funciona_em_modelo_que_recusa_temperature():
    """Ponta a ponta do defeito: antes, isto devolvia None."""
    resposta = Mock()
    resposta.choices = [
        Mock(message=Mock(content='{"texto": "Fato curioso.", "tem_certeza": true}'))
    ]
    cliente = _cliente_familia_gpt6(resposta)

    with patch.object(curador, "_client", cliente), \
         patch.object(curador, "PILULAS_MODELO", "gpt-6-sol"):
        assert curador.gerar_pilula("Dead Fish", "Messias") == "Fato curioso."


def test_personalizar_pilula_funciona_em_modelo_que_recusa_max_tokens():
    """A personalização manda max_tokens=220. Sem o tratamento, o 400 caía no
    `except` e o ouvinte recebia sempre a pílula base — sem erro visível."""
    base = "Gravada em 1973, a faixa é de Edson Trindade."
    resposta = Mock()
    resposta.choices = [
        Mock(message=Mock(content=base + " Boa viagem de carro com a família!"))
    ]
    cliente = _cliente_familia_gpt6(resposta)

    with patch.object(curador, "_client", cliente), \
         patch.object(curador, "PILULAS_CONTEXTO_MODELO", "gpt-6-sol"):
        texto = curador.personalizar_pilula(base, "vou ouvir no carro com a família")

    assert texto != base
    assert "família" in texto
    # O nome novo do parâmetro chegou na chamada que funcionou.
    assert cliente.chat.completions.create.call_args.kwargs["max_completion_tokens"] == 220
