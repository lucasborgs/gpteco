"""
tests/test_llm_compat.py

Regressão de 2026-10-09/10. A família gpt-6 diverge dos modelos anteriores em
dois parâmetros que o projeto usa, e cada um deu um defeito diferente:

  - `temperature`: devolve 400 e as pílulas pararam de ser geradas em silêncio
    (`except Exception: return None` no curador, mais o cache do banco
    servindo as antigas, esconderam o problema por completo).

  - `max_tokens`: devolve 400 pedindo `max_completion_tokens`. Pega o composer
    (160) e a personalização da pílula (220), que também engolem exceção e
    caem no texto fixo — degradação invisível.

Os dois erros vêm da mesma chamada em alguns casos, e a API reclama de
`max_tokens` primeiro. Por isso o tratamento não pode olhar só um parâmetro.
"""

from unittest.mock import Mock

import pytest

from core import llm_compat


class _Erro400(Exception):
    """Imita o 400 da OpenAI citando um parâmetro específico."""

    def __init__(self, mensagem):
        self._mensagem = mensagem

    def __str__(self):
        return self._mensagem


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


@pytest.fixture(autouse=True)
def _limpa_memoria_de_modelos():
    """A memória dura a vida do processo de propósito; nos testes não pode
    vazar de um caso para o outro."""
    llm_compat._SEM_TEMPERATURE.clear()
    llm_compat._SEM_MAX_TOKENS.clear()
    yield
    llm_compat._SEM_TEMPERATURE.clear()
    llm_compat._SEM_MAX_TOKENS.clear()


def _cliente(recusa=(), modelos=None):
    """Cliente falso que recusa os parâmetros listados, como a API real.

    Checa `max_tokens` antes de `temperature` porque é essa a ordem em que a
    OpenAI reclama quando os dois vêm na mesma chamada. `modelos=None` recusa
    em qualquer modelo; uma lista restringe a recusa a esses nomes.
    """
    def create(**kwargs):
        if modelos is not None and kwargs.get("model") not in modelos:
            return "resposta-ok"
        if "max_tokens" in recusa and "max_tokens" in kwargs:
            raise _Erro400(_ERRO_MAX_TOKENS)
        if "temperature" in recusa and "temperature" in kwargs:
            raise _Erro400(_ERRO_TEMPERATURE)
        return "resposta-ok"

    cliente = Mock()
    cliente.chat.completions.create.side_effect = create
    return cliente


def test_modelo_que_aceita_tudo_recebe_os_parametros_pedidos():
    """O temperature baixo é o que segura a alucinação na pílula — não pode
    ser descartado por precaução num modelo que aceita o parâmetro."""
    cliente = _cliente()

    assert llm_compat.completar(cliente, "gpt-4o", temperature=0.35, max_tokens=160) == "resposta-ok"

    assert cliente.chat.completions.create.call_count == 1
    kwargs = cliente.chat.completions.create.call_args.kwargs
    assert kwargs["temperature"] == 0.35
    assert kwargs["max_tokens"] == 160
    assert "max_completion_tokens" not in kwargs


def test_repete_sem_temperature_quando_o_modelo_recusa():
    cliente = _cliente(recusa=("temperature",))

    assert llm_compat.completar(cliente, "gpt-6-sol", temperature=0.35) == "resposta-ok"

    assert cliente.chat.completions.create.call_count == 2
    primeira, segunda = cliente.chat.completions.create.call_args_list
    assert primeira.kwargs["temperature"] == 0.35
    assert "temperature" not in segunda.kwargs
    assert segunda.kwargs["model"] == "gpt-6-sol"


def test_renomeia_max_tokens_quando_o_modelo_recusa():
    cliente = _cliente(recusa=("max_tokens",))

    assert llm_compat.completar(cliente, "gpt-6-sol", max_tokens=160) == "resposta-ok"

    assert cliente.chat.completions.create.call_count == 2
    _, segunda = cliente.chat.completions.create.call_args_list
    assert "max_tokens" not in segunda.kwargs
    assert segunda.kwargs["max_completion_tokens"] == 160


def test_resolve_os_dois_parametros_na_mesma_chamada():
    """Caso do composer: manda temperature=0.5 e max_tokens=160 juntos, e a
    API só reclama de um por vez."""
    cliente = _cliente(recusa=("temperature", "max_tokens"))

    assert llm_compat.completar(
        cliente, "gpt-6-sol", temperature=0.5, max_tokens=160
    ) == "resposta-ok"

    assert cliente.chat.completions.create.call_count == 3
    ultima = cliente.chat.completions.create.call_args.kwargs
    assert "temperature" not in ultima
    assert "max_tokens" not in ultima
    assert ultima["max_completion_tokens"] == 160


def test_nao_repete_a_descoberta_nas_chamadas_seguintes():
    """A primeira chamada custa uma tentativa perdida; as próximas não."""
    cliente = _cliente(recusa=("temperature", "max_tokens"))

    llm_compat.completar(cliente, "gpt-6-sol", temperature=0.5, max_tokens=160)
    cliente.chat.completions.create.reset_mock()
    llm_compat.completar(cliente, "gpt-6-sol", temperature=0.35, max_tokens=220)

    assert cliente.chat.completions.create.call_count == 1
    kwargs = cliente.chat.completions.create.call_args.kwargs
    assert "temperature" not in kwargs
    assert kwargs["max_completion_tokens"] == 220


def test_a_descoberta_e_por_modelo():
    """Cada entrada do .env pode apontar para uma família diferente; o que
    valeu para um modelo não pode ser aplicado ao outro."""
    cliente = _cliente(recusa=("temperature",), modelos=["gpt-6-sol"])

    llm_compat.completar(cliente, "gpt-6-sol", temperature=0.35)
    cliente.chat.completions.create.reset_mock()
    llm_compat.completar(cliente, "gpt-4o", temperature=0.35)

    assert cliente.chat.completions.create.call_count == 1
    assert cliente.chat.completions.create.call_args.kwargs["temperature"] == 0.35


def test_erro_de_outra_natureza_sobe_sem_repetir():
    """Sem isto, qualquer falha (chave inválida, rate limit, modelo
    inexistente) viraria chamada repetida e o modelo entraria na memória de
    incompatibilidade por engano."""
    cliente = Mock()
    cliente.chat.completions.create.side_effect = RuntimeError("rate limit exceeded")

    with pytest.raises(RuntimeError, match="rate limit"):
        llm_compat.completar(cliente, "gpt-4o", temperature=0.35)

    assert cliente.chat.completions.create.call_count == 1
    assert "gpt-4o" not in llm_compat._SEM_TEMPERATURE
    assert "gpt-4o" not in llm_compat._SEM_MAX_TOKENS
