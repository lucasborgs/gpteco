"""
core/eleitoral.py

Filtro determinístico de conteúdo eleitoral — vigência temporária (período
eleitoral). Duas listas, dois mecanismos:

  - CANDIDATOS: nomes cuja menção no ÁUDIO transcrito do ouvinte bloqueia o
    pedido. Só se aplica a pedido por áudio — é a voz do próprio ouvinte que
    seria sobreposta à música e iria ao ar (core/pipeline.py, Etapa 5); pedido
    digitado não tem essa etapa de mixagem, então não passa por esta checagem.
  - MUSICAS_PROIBIDAS: títulos de música vetados, por conteúdo político,
    independente do canal (áudio ou texto) — checados contra o título já
    identificado pelo LLM.

Deliberadamente fora do classificador LLM (core/intelligence.py): is_apropriado
só avalia ofensa direta e is_flashback só decide gênero — misturar política
aí quebraria a semântica das duas e tornaria a rejeição indistinguível nos
registros de dim_pedidos. motivo_rejeicao="eleitoral" mantém isso auditável e
reversível (basta esvaziar as listas abaixo ao final do período eleitoral).

Risco conhecido: casamento por palavra/frase inteira, não por entidade.
"Lula" é também a palavra usada para o molusco (lula frita, lula à dorê) —
uma transcrição que mencione o prato vai ser bloqueada por engano. Aceito
como erro de recusa (o requisito é errar para esse lado), mas registrado
aqui para não ficar escondido.
"""

from __future__ import annotations

import re
import unicodedata

CANDIDATOS: list[str] = [
    "Lula",
    "Bolsonaro",
    "Caiado",
    "Renan Santos",
    "Zema",
    "Augusto Cury",
    "Pablo Marçal",
    "Cleitinho Azevedo",
    "Ananias",
    "Alexandre Kalil",
    "Mateus Simões",
    "Gabriel Azevedo",
    "Flávio Roscoe",
    "Alexandre de Moraes",
    "Ana Luiza do MLB",
    "Arcanjo Pimenta",
    "Áurea Carolina",
    "Carlin Moura",
    "Carlos Viana",
    "Domingos Sávio",
    "Fidélis Alcântara",
    "Gustavo Galassi",
    "Jordano Metalúrgico",
    "Juiz Ramon Moreira",
    "Manoel Carvalho",
    "Marcelo Aro",
    "Marcelo Heringer",
    "Marco Antônio Superman",
    "Marília Campos",
    "Tião Pessoa",
    "Victória Mello Vic",
]

MUSICAS_PROIBIDAS: list[str] = [
    "Vai dar PT",
    "Lula Lá",
    "Diretas Já",
]


def _normalizar(texto: str) -> str:
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c)
    )
    return sem_acento.lower().strip()


def contem_candidato(texto: str) -> bool:
    """True se `texto` (transcrição de áudio) menciona algum nome de
    CANDIDATOS. Casamento por frase inteira, sem acento/caixa — evita que uma
    palavra vire substring de outra, mas não distingue sentido (ver risco do
    módulo)."""
    if not texto:
        return False
    alvo = _normalizar(texto)
    for nome in CANDIDATOS:
        nome_norm = _normalizar(nome)
        if re.search(rf"\b{re.escape(nome_norm)}\b", alvo):
            return True
    return False


def eh_musica_proibida(musica: str) -> bool:
    """True se `musica` (título já identificado pelo LLM) bate com algum
    item de MUSICAS_PROIBIDAS — por título sozinho, sem considerar artista."""
    if not musica:
        return False
    alvo = _normalizar(musica)
    return any(_normalizar(titulo) == alvo for titulo in MUSICAS_PROIBIDAS)
