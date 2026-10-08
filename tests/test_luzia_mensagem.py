"""Testes de core.luzia.mensagem() — leitura tolerante de slug (F0.4).

Diferente das constantes MSG_* (estritas, levantam se o slug faltar),
mensagem(slug, default) nunca levanta: serve o texto do perfil quando o slug
existe, ou o default do chamador quando não existe. É o mecanismo que evita
que um slug novo (ex.: "busca_ocupada") derrube o pipeline com erro_tecnico
enquanto o assistente.md do cliente ainda não tiver a seção correspondente.
"""

from core import luzia


def test_mensagem_devolve_texto_do_perfil_quando_slug_existe():
    # "sucesso" já existe em core/luzia/luzia.md — mesmo texto de MSG_SUCESSO.
    assert luzia.mensagem("sucesso") == luzia.MSG_SUCESSO
    assert luzia.mensagem("sucesso") != ""


def test_mensagem_devolve_default_quando_slug_nao_existe():
    assert luzia.mensagem("slug_inexistente", "texto de reserva") == "texto de reserva"


def test_mensagem_devolve_string_vazia_por_padrao_quando_slug_nao_existe():
    assert luzia.mensagem("slug_inexistente") == ""
