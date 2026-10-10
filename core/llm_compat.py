"""
core/llm_compat.py

Compatibilidade de parâmetros entre famílias de modelo da OpenAI.

Os modelos de raciocínio (família gpt-6) divergem dos anteriores em dois
parâmetros que o projeto usa:

  - `temperature`: só aceitam o padrão (1) e devolvem 400 com qualquer outro
    valor. Os modelos antigos (gpt-4o) aceitam.
  - `max_tokens`: foi substituído por `max_completion_tokens`, e mandar o nome
    antigo devolve 400.

Em vez de manter uma lista de nomes de modelo, que envelhece a cada
lançamento, descobrimos a incompatibilidade na primeira chamada e lembramos
pelo resto do processo. O custo é um 400 por modelo por parâmetro, uma vez só.

Isto existe como módulo próprio porque os três pontos que chamam LLM
(intelligence, composer, curador) precisam do mesmo tratamento, e porque o
.env pode apontar cada um deles para uma família diferente.
"""

from __future__ import annotations

# Modelos que recusaram cada parâmetro nesta execução.
_SEM_TEMPERATURE: set[str] = set()
_SEM_MAX_TOKENS: set[str] = set()


def _adaptar(modelo: str, kwargs: dict) -> dict:
    """Aplica as incompatibilidades já conhecidas deste modelo."""
    kw = dict(kwargs)
    if modelo in _SEM_TEMPERATURE:
        kw.pop("temperature", None)
    if modelo in _SEM_MAX_TOKENS and "max_tokens" in kw:
        kw["max_completion_tokens"] = kw.pop("max_tokens")
    return kw


def completar(client, modelo: str, **kwargs):
    """`chat.completions.create` tolerando parâmetro que o modelo recusa.

    Tenta com os parâmetros pedidos; se a API recusar `temperature` ou
    `max_tokens`, anota o modelo e repete adaptado. Qualquer outro erro
    (modelo inexistente, rate limit, rede) sobe para quem chamou.

    Cada volta do laço devolve, propaga, ou anota uma incompatibilidade nova —
    e só existem duas para anotar, então ele termina.
    """
    while True:
        try:
            return client.chat.completions.create(model=modelo, **_adaptar(modelo, kwargs))
        except Exception as e:
            msg = str(e)
            if "'temperature'" in msg and modelo not in _SEM_TEMPERATURE:
                print(f"[LLM] {modelo} não aceita temperature — repetindo sem o parâmetro.")
                _SEM_TEMPERATURE.add(modelo)
            elif "'max_tokens'" in msg and modelo not in _SEM_MAX_TOKENS:
                print(f"[LLM] {modelo} exige max_completion_tokens — repetindo com o nome novo.")
                _SEM_MAX_TOKENS.add(modelo)
            else:
                raise
