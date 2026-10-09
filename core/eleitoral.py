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

Casamento de MUSICAS_PROIBIDAS (lista do apêndice A da spec, 110 entradas):
cada entrada é um MusicaProibida com um ou mais títulos (canônico + aliases).
O título do pedido bloqueia por igualdade exata contra algum título
normalizado da entrada — não por substring, para não pegar títulos que apenas
contêm uma palavra da lista. Entradas de palavra comum (`exige_artista=True`)
só bloqueiam se o artista do pedido também casar com algum artista conhecido
da entrada, por contenção de palavra inteira em qualquer direção (cobre
apelidos/abreviações: "Racionais" casa com "Racionais MC's", "Titãs" casa com
"Os Titãs"). Artista vazio nunca casa — e o gate roda antes da checagem de
campos vazios do pipeline, então chegar aqui sem artista é esperado.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

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


@dataclass(frozen=True)
class MusicaProibida:
    """Uma entrada da lista de bloqueio eleitoral.

    titulos       : título canônico + aliases (casamento por igualdade,
                     depois de normalizado — não por substring).
    artistas      : artistas conhecidos da faixa. Só é usado no casamento
                     quando `exige_artista=True`; nas demais entradas é só
                     documentação.
    exige_artista : False (padrão) bloqueia pelo título sozinho. True exige
                     que o artista do pedido também case com algum nome de
                     `artistas` — usado nos títulos de palavra comum, que
                     bloqueariam faixas homônimas inofensivas se checados só
                     pelo título (ver apêndice A.2 da spec).
    """

    titulos: tuple[str, ...]
    artistas: tuple[str, ...] = ()
    exige_artista: bool = False


# Apêndice A da spec sertanejo-throttle-canal-voz: 91 entradas de bloqueio só
# por título (A.1) + 19 que exigem casamento de artista (A.2). Agrupadas por
# artista, na ordem do apêndice, para a lista ficar revisável em diff.
MUSICAS_PROIBIDAS: list[MusicaProibida] = [
    # --- A.1: bloqueio por título, qualquer artista (91 entradas) ---

    # Eduardo Costa
    MusicaProibida(titulos=("Para e Reflete",), artistas=("Eduardo Costa",)),
    MusicaProibida(titulos=("Olha o Trem",), artistas=("Eduardo Costa",)),

    # Tião Carreiro & Pardinho
    MusicaProibida(titulos=("O Prato do Dia",), artistas=("Tião Carreiro & Pardinho",)),
    MusicaProibida(titulos=("A Viola e a Bíblia",), artistas=("Tião Carreiro & Pardinho",)),

    # João do Vale
    MusicaProibida(titulos=("Sina de Caboclo",), artistas=("João do Vale",)),
    MusicaProibida(titulos=("Carcará",), artistas=("João do Vale",)),

    # Juliano Maderada
    MusicaProibida(titulos=("Faz o L",), artistas=("Juliano Maderada",)),

    # Léo Santana (já na lista atual)
    MusicaProibida(titulos=("Vai Dar PT",), artistas=("Léo Santana",)),

    # Juliano Maderada (continuação)
    MusicaProibida(titulos=("Tá Na Hora do Jair Já Ir Embora",), artistas=("Juliano Maderada",)),
    MusicaProibida(titulos=("Lambadão do 13",), artistas=("Juliano Maderada",)),
    MusicaProibida(titulos=("Tá Com Medo da Parada",), artistas=("Juliano Maderada",)),

    # Diversos artistas (alias já na lista atual)
    MusicaProibida(titulos=("Sem Medo de Ser Feliz", "Lula Lá")),

    # Chico Buarque, Caetano Veloso, Gilberto Gil
    MusicaProibida(
        titulos=("Bora Lula",),
        artistas=("Chico Buarque", "Caetano Veloso", "Gilberto Gil"),
    ),

    # Mateus & Cristiano
    MusicaProibida(titulos=("Capitão do Povo",), artistas=("Mateus & Cristiano",)),

    # MC Bob Rum
    MusicaProibida(titulos=("Rap do Silva",), artistas=("MC Bob Rum",)),

    # Gabriel O Pensador
    MusicaProibida(
        titulos=("Tô Feliz", "Matei o Presidente", "Tô Feliz Matei o Presidente"),
        artistas=("Gabriel O Pensador",),
    ),
    MusicaProibida(titulos=("Ideologia",), artistas=("Cazuza", "Gabriel O Pensador")),
    MusicaProibida(titulos=("2345608", "2 3 4 5 6 0 8"), artistas=("Gabriel O Pensador",)),

    # Racionais MC's
    MusicaProibida(titulos=("Diário de um Detento",), artistas=("Racionais MC's",)),
    MusicaProibida(titulos=("Fim de Semana no Parque",), artistas=("Racionais MC's",)),
    MusicaProibida(
        titulos=("Capítulo 4, Versículo 3", "Capítulo 4 Versículo 3"),
        artistas=("Racionais MC's",),
    ),
    MusicaProibida(titulos=("Jesus Chorou",), artistas=("Racionais MC's",)),
    MusicaProibida(titulos=("Negro Drama",), artistas=("Racionais MC's",)),

    # Criolo (+ Chico Buarque, Gilberto Gil em "Cálice")
    MusicaProibida(
        titulos=("Não Existe Amor em SP", "Não Existe Amor em São Paulo"),
        artistas=("Criolo",),
    ),
    MusicaProibida(titulos=("Boca de Lobo",), artistas=("Criolo",)),
    MusicaProibida(titulos=("Cálice",), artistas=("Chico Buarque", "Gilberto Gil", "Criolo")),

    # Djonga
    MusicaProibida(titulos=("Olho de Tigre",), artistas=("Djonga",)),

    # Emicida
    MusicaProibida(titulos=("AmarElo",), artistas=("Emicida",)),
    MusicaProibida(titulos=("Boa Esperança",), artistas=("Emicida",)),
    MusicaProibida(titulos=("Ismália",), artistas=("Emicida",)),

    # Planet Hemp
    MusicaProibida(titulos=("Mantenha o Respeito",), artistas=("Planet Hemp", "Marcelo D2")),
    MusicaProibida(
        titulos=("Dig Dig Dig", "Hempa", "Dig Dig Dig Hempa"),
        artistas=("Planet Hemp",),
    ),

    # MV Bill
    MusicaProibida(titulos=("Soldado do Morro",), artistas=("MV Bill",)),
    MusicaProibida(titulos=("Só Deus Pode Me Julgar",), artistas=("MV Bill",)),

    # Legião Urbana (+ Capital Inicial em "Que País É Este")
    MusicaProibida(titulos=("Que País É Este",), artistas=("Legião Urbana", "Capital Inicial")),
    MusicaProibida(titulos=("Índios",), artistas=("Legião Urbana",)),
    MusicaProibida(titulos=("Faroeste Caboclo",), artistas=("Legião Urbana",)),
    MusicaProibida(titulos=("Geração Coca-Cola",), artistas=("Legião Urbana",)),
    MusicaProibida(titulos=("Conexão Amazônica",), artistas=("Legião Urbana",)),

    # Titãs
    MusicaProibida(titulos=("Polícia",), artistas=("Titãs",)),
    MusicaProibida(titulos=("O Pulso",), artistas=("Titãs",)),
    MusicaProibida(titulos=("Homem Primata",), artistas=("Titãs",)),

    # Capital Inicial
    MusicaProibida(titulos=("Veraneio Vascaína",), artistas=("Capital Inicial",)),

    # Os Paralamas do Sucesso
    MusicaProibida(
        titulos=("Luís Inácio", "300 Picaretas", "Luís Inácio 300 Picaretas"),
        artistas=("Os Paralamas do Sucesso",),
    ),
    MusicaProibida(titulos=("Alagados",), artistas=("Os Paralamas do Sucesso",)),

    # Engenheiros do Hawaii
    MusicaProibida(titulos=("Toda Forma de Poder",), artistas=("Engenheiros do Hawaii",)),
    MusicaProibida(
        titulos=("Ninguém = Ninguém", "Ninguém Igual Ninguém"),
        artistas=("Engenheiros do Hawaii",),
    ),
    MusicaProibida(titulos=("A Revolta dos Dândis",), artistas=("Engenheiros do Hawaii",)),
    MusicaProibida(titulos=("Tribos e Tribos",), artistas=("Engenheiros do Hawaii",)),

    # Plebe Rude
    MusicaProibida(titulos=("Até Quando Esperar",), artistas=("Plebe Rude",)),

    # Ultraje a Rigor
    MusicaProibida(titulos=("Inútil",), artistas=("Ultraje a Rigor",)),
    MusicaProibida(titulos=("Inviolável",), artistas=("Ultraje a Rigor",)),
    MusicaProibida(titulos=("Nós Vamos Invadir sua Praia",), artistas=("Ultraje a Rigor",)),

    # Cazuza
    MusicaProibida(titulos=("Burguesia",), artistas=("Cazuza",)),
    MusicaProibida(titulos=("O Tempo Não Pára",), artistas=("Cazuza",)),

    # Biquini Cavadão
    MusicaProibida(titulos=("Zé Ninguém",), artistas=("Biquini Cavadão",)),

    # Pitty
    MusicaProibida(titulos=("Admirável Chip Novo",), artistas=("Pitty",)),
    MusicaProibida(titulos=("Teto de Vidro",), artistas=("Pitty",)),

    # Garotos Podres
    MusicaProibida(titulos=("Papai Noel Velho Batuta",), artistas=("Garotos Podres",)),

    # Ratos de Porão
    MusicaProibida(titulos=("Crucificados pelo Sistema",), artistas=("Ratos de Porão",)),

    # Geraldo Vandré
    MusicaProibida(titulos=("Pra Não Dizer Que Não Falei das Flores",), artistas=("Geraldo Vandré",)),
    MusicaProibida(titulos=("Aroeira",), artistas=("Geraldo Vandré",)),

    # Raul Seixas
    MusicaProibida(titulos=("Aluga-se",), artistas=("Raul Seixas",)),
    MusicaProibida(titulos=("Sociedade Alternativa",), artistas=("Raul Seixas",)),
    MusicaProibida(titulos=("O Trem das Sete",), artistas=("Raul Seixas",)),
    MusicaProibida(titulos=("Cowboy Fora da Lei",), artistas=("Raul Seixas",)),
    MusicaProibida(titulos=("Mosca na Sopa",), artistas=("Raul Seixas",)),

    # Chico Buarque
    MusicaProibida(titulos=("Apesar de Você",), artistas=("Chico Buarque",)),
    MusicaProibida(titulos=("Roda Viva",), artistas=("Chico Buarque",)),
    MusicaProibida(titulos=("Construção",), artistas=("Chico Buarque",)),
    MusicaProibida(titulos=("Meu Caro Amigo",), artistas=("Chico Buarque",)),
    MusicaProibida(titulos=("Acorda Amor",), artistas=("Chico Buarque",)),
    MusicaProibida(titulos=("As Caravanas",), artistas=("Chico Buarque",)),

    # Caetano Veloso
    MusicaProibida(titulos=("Alegria, Alegria", "Alegria Alegria"), artistas=("Caetano Veloso",)),
    MusicaProibida(titulos=("É Proibido Proibir",), artistas=("Caetano Veloso",)),
    MusicaProibida(titulos=("Vândalo do Apocalipse",), artistas=("Caetano Veloso",)),
    MusicaProibida(titulos=("Podres Poderes",), artistas=("Caetano Veloso",)),

    # Gilberto Gil
    MusicaProibida(titulos=("Aquele Abraço",), artistas=("Gilberto Gil",)),
    MusicaProibida(titulos=("Nos Barracos da Cidade",), artistas=("Gilberto Gil",)),
    MusicaProibida(titulos=("Aquele Frevo Axé",), artistas=("Gilberto Gil",)),

    # Elis Regina (+ Belchior em "Como Nossos Pais")
    MusicaProibida(titulos=("Como Nossos Pais",), artistas=("Elis Regina", "Belchior")),
    MusicaProibida(
        titulos=("O Bêbado e a Equilibrista", "O Bêbado e o Equilibrista"),
        artistas=("Elis Regina",),
    ),

    # Belchior
    MusicaProibida(titulos=("Sujeito de Sorte",), artistas=("Belchior",)),

    # Gonzaguinha
    MusicaProibida(titulos=("O Oitavo Dia",), artistas=("Gonzaguinha",)),
    MusicaProibida(titulos=("Com a Perna No Mundo",), artistas=("Gonzaguinha",)),
    MusicaProibida(titulos=("Comportamento Geral",), artistas=("Gonzaguinha",)),

    # Noel Rosa
    MusicaProibida(
        titulos=("Onde Está a Honestidade?", "Onde Está a Honestidade"),
        artistas=("Noel Rosa",),
    ),

    # Juca Chaves
    MusicaProibida(titulos=("Presidente Bossa Nova",), artistas=("Juca Chaves",)),

    # Milton Nascimento
    MusicaProibida(titulos=("Coração de Estudante",), artistas=("Milton Nascimento",)),

    # Os Mutantes
    MusicaProibida(titulos=("Panis et Circenses",), artistas=("Os Mutantes",)),

    # Diversos artistas (já na lista atual)
    MusicaProibida(titulos=("Diretas Já",)),

    # --- A.2: bloqueio por título + artista — títulos de palavra comum
    # (19 entradas). Bloquear só pelo título geraria recusa de faixas
    # homônimas sem relação com o conteúdo político. ---

    # Gabriel O Pensador
    MusicaProibida(titulos=("Chega",), artistas=("Gabriel O Pensador",), exige_artista=True),

    # Djonga
    MusicaProibida(titulos=("Ladrão",), artistas=("Djonga",), exige_artista=True),
    MusicaProibida(titulos=("Leal",), artistas=("Djonga",), exige_artista=True),

    # Marcelo D2
    MusicaProibida(titulos=("Qual É?", "Qual É"), artistas=("Marcelo D2",), exige_artista=True),

    # MV Bill
    MusicaProibida(titulos=("O Estilo",), artistas=("MV Bill",), exige_artista=True),

    # Legião Urbana
    MusicaProibida(titulos=("Perfeição",), artistas=("Legião Urbana",), exige_artista=True),

    # Titãs
    MusicaProibida(titulos=("Comida",), artistas=("Titãs",), exige_artista=True),
    MusicaProibida(titulos=("Lugar Nenhum",), artistas=("Titãs",), exige_artista=True),
    MusicaProibida(titulos=("Igreja",), artistas=("Titãs",), exige_artista=True),

    # Capital Inicial
    MusicaProibida(titulos=("Natasha",), artistas=("Capital Inicial",), exige_artista=True),

    # Os Paralamas do Sucesso
    MusicaProibida(titulos=("Selvagem",), artistas=("Os Paralamas do Sucesso",), exige_artista=True),
    MusicaProibida(titulos=("O Beco",), artistas=("Os Paralamas do Sucesso",), exige_artista=True),

    # Plebe Rude
    MusicaProibida(titulos=("Proteção",), artistas=("Plebe Rude",), exige_artista=True),

    # Cazuza, Barão Vermelho
    MusicaProibida(titulos=("Brasil",), artistas=("Cazuza", "Barão Vermelho"), exige_artista=True),

    # Biquini Cavadão
    MusicaProibida(titulos=("Livre",), artistas=("Biquini Cavadão",), exige_artista=True),

    # Pitty
    MusicaProibida(titulos=("Noite Inteira",), artistas=("Pitty",), exige_artista=True),

    # Geraldo Vandré — "Caminhando" é alias de "Pra Não Dizer Que Não Falei
    # das Flores" (A.1), mas entra como entrada própria: é palavra comum e
    # precisa de exige_artista=True, enquanto o título longo bloqueia
    # sozinho. Não unificar as duas entradas.
    MusicaProibida(titulos=("Caminhando",), artistas=("Geraldo Vandré",), exige_artista=True),

    # Gonzaguinha — "É", de uma letra, é o caso degenerado do apêndice: sem
    # artista (ou com artista que não casa), não bloqueia.
    MusicaProibida(titulos=("É",), artistas=("Gonzaguinha",), exige_artista=True),

    # Zé Keti
    MusicaProibida(titulos=("Opinião",), artistas=("Zé Keti",), exige_artista=True),
]


def _normalizar(texto: str) -> str:
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c)
    )
    sem_acento = sem_acento.lower().strip()
    return re.sub(r"\s+", " ", sem_acento)


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


def _artista_casa(artista_pedido_norm: str, artistas_entrada: tuple[str, ...]) -> bool:
    """True se `artista_pedido_norm` (já normalizado) casa com algum nome de
    `artistas_entrada`, por contenção de palavra inteira em qualquer direção
    — cobre apelidos/abreviações: "Racionais" casa com "Racionais MC's",
    "Titãs" casa com "Os Titãs". Artista vazio nunca casa."""
    if not artista_pedido_norm:
        return False
    for nome in artistas_entrada:
        nome_norm = _normalizar(nome)
        if not nome_norm:
            continue
        if re.search(rf"\b{re.escape(nome_norm)}\b", artista_pedido_norm):
            return True
        if re.search(rf"\b{re.escape(artista_pedido_norm)}\b", nome_norm):
            return True
    return False


def eh_musica_proibida(musica: str, artista: str = "") -> bool:
    """True se `musica` (título já identificado pelo LLM) bate com algum
    item de MUSICAS_PROIBIDAS.

    O título casa por igualdade exata (normalizado) contra algum dos
    `titulos` da entrada. Entradas com `exige_artista=False` bloqueiam só
    pelo título. Entradas com `exige_artista=True` (títulos de palavra
    comum) só bloqueiam se `artista` também casar com algum dos `artistas`
    da entrada — ver `_artista_casa`. `artista` é opcional (default `""`)
    para manter compatível qualquer chamada existente; com artista vazio, as
    entradas `exige_artista=True` nunca bloqueiam.
    """
    if not musica:
        return False
    alvo_titulo = _normalizar(musica)
    alvo_artista = _normalizar(artista) if artista else ""
    for entrada in MUSICAS_PROIBIDAS:
        titulos_norm = {_normalizar(titulo) for titulo in entrada.titulos}
        if alvo_titulo not in titulos_norm:
            continue
        if not entrada.exige_artista:
            return True
        if _artista_casa(alvo_artista, entrada.artistas):
            return True
    return False
