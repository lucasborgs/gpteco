"""
core/repertorio.py

Item A da liberação de repertório: alguns gêneros são aceitos de forma
INCONDICIONAL, independente do veredito `is_flashback` do classificador LLM.
Hoje é usado só para sertanejo (ver sdd/sertanejo-throttle-canal-voz-spec.md,
seção 5), para que subgêneros modernos (piseiro, sofrência eletrônica,
feminejo, sertanejo funk, arrocha) não dependam do julgamento do modelo — a
liberação passa a ser determinística em código.

A lista de gêneros liberados vem de GENEROS_SEMPRE_ACEITOS no .env, separada
por vírgula. Lida em tempo de import: mudar a variável exige reiniciar o
processo (o mesmo vale para o resto do .env neste repositório — não há
hot-reload de ambiente, só de core/luzia/luzia.md). Testes que precisem variar
a variável usam `importlib.reload(core.repertorio)` após `monkeypatch.setenv`.

Lista vazia (`GENEROS_SEMPRE_ACEITOS=""`) desliga o item A em código: nenhum
gênero é liberado incondicionalmente e a decisão volta a ser 100% do
`is_flashback` do LLM.
"""

from __future__ import annotations

import os
import re
import unicodedata


def _normalizar(texto: str) -> str:
    """Sem acento, minúsculas, espaços internos colapsados — mesmo critério
    de core/eleitoral.py._normalizar, duplicado aqui para este módulo não
    depender de outro (interface mínima, sem import cruzado)."""
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c)
    )
    sem_acento = sem_acento.lower().strip()
    return re.sub(r"\s+", " ", sem_acento)


def _carregar_generos() -> frozenset[str]:
    bruto = os.getenv("GENEROS_SEMPRE_ACEITOS", "sertanejo")
    return frozenset(
        termo_norm
        for termo in bruto.split(",")
        if (termo_norm := _normalizar(termo))
    )


# Gêneros liberados incondicionalmente, já normalizados (sem acento, minúsculas).
GENEROS_SEMPRE_ACEITOS: frozenset[str] = _carregar_generos()


def genero_liberado(genero: str) -> bool:
    """True se `genero` (vindo do classificador) está coberto por algum termo
    de GENEROS_SEMPRE_ACEITOS.

    Casamento por PREFIXO DE PALAVRA, não por igualdade nem por substring:
    "sertanejo universitário" casa com "sertanejo" (a palavra "sertanejo" é
    um prefixo de palavra inteira do gênero informado), mas "sertanejão" NÃO
    casa (a palavra inteira é diferente, mesmo compartilhando o prefixo
    textual "sertanej"). Isso é feito ancorando a busca no início da string
    normalizada e exigindo fronteira de palavra (`\\b`) logo depois do termo.

    Gênero vazio ou None → False. GENEROS_SEMPRE_ACEITOS vazio → sempre False
    (lista vazia desliga o item A).
    """
    if not genero:
        return False
    genero_norm = _normalizar(genero)
    if not genero_norm:
        return False
    return any(
        re.match(rf"{re.escape(termo)}\b", genero_norm)
        for termo in GENEROS_SEMPRE_ACEITOS
    )
