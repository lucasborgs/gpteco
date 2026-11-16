"""A troca de modelo mantém as respostas geradas, sem cair no texto fixo."""

from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from core import composer, llm_compat


@pytest.mark.parametrize("modelo", ["gpt-5.6", "gpt-5.6-sol", "gpt-4o"])
def test_resposta_curta_preserva_texto_gerado_e_compatibilidade(monkeypatch, modelo):
    esperado = "Pode mandar o nome da música e do artista que você quer ouvir?"

    def criar(**kwargs):
        # O orçamento de saída dos modelos de raciocínio também inclui o
        # raciocínio. A resposta curta precisa reservar esse espaço ao texto.
        if modelo.startswith("gpt-5.6"):
            assert kwargs["reasoning_effort"] == "none"
            assert kwargs["max_completion_tokens"] == 160
            assert "max_tokens" not in kwargs
        else:
            assert "reasoning_effort" not in kwargs
            assert kwargs["max_tokens"] == 160
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=esperado))])

    cliente = Mock()
    cliente.chat.completions.create.side_effect = criar
    monkeypatch.setattr(llm_compat, "_SEM_TEMPERATURE", set())
    monkeypatch.setattr(llm_compat, "_SEM_MAX_TOKENS", set())
    with patch.object(composer, "_ENABLED", True), \
         patch.object(composer, "_client", cliente), \
         patch.object(composer, "MODELO", modelo):
        assert composer.compor("nao_id", {}, "quero uma música") == esperado
    cliente.chat.completions.create.assert_called_once()
    assert cliente.chat.completions.create.call_args.kwargs["model"] == modelo
