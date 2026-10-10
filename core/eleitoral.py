"""
core/eleitoral.py

Filtro determinístico de conteúdo eleitoral — vigência temporária (período
eleitoral). Duas listas, dois mecanismos:

  - candidatos: nomes cuja menção no ÁUDIO transcrito do ouvinte bloqueia o
    pedido. Só se aplica a pedido por áudio — é a voz do próprio ouvinte que
    seria sobreposta à música e iria ao ar (core/pipeline.py, Etapa 5); pedido
    digitado não tem essa etapa de mixagem, então não passa por esta checagem.
  - musicas_proibidas: títulos de música vetados, por conteúdo político,
    independente do canal (áudio ou texto) — checados contra o título já
    identificado pelo LLM.

As duas listas moram em `core/eleitoral.json`, FORA do código. Quais faixas
barrar é decisão da emissora, e decisão da emissora não pode depender de
rebuild da imagem: o caminho é resolvido por ELEITORAL_LISTA_PATH (arquivo do
cliente, montado por bind mount e editável no host); se a variável estiver
vazia ou apontar para algo que não é arquivo, vale o eleitoral.json embutido
no pacote. A releitura é por mtime a cada consulta — mesmo mecanismo de
core/luzia, então editar o arquivo no cliente vale no pedido seguinte, sem
restart.

O filtro nunca fica sem lista: JSON inválido mantém em memória a última
versão boa, e arquivo do cliente que nunca carregou com sucesso cai no
embutido em vez de derrubar o servidor. Lista VAZIA, por outro lado, é estado
legítimo — é assim que o filtro é desligado ao fim do período eleitoral —
então é aceita, e apenas registrada no log.

Deliberadamente fora do classificador LLM (core/intelligence.py): is_apropriado
só avalia ofensa direta e is_flashback só decide gênero — misturar política
aí quebraria a semântica das duas e tornaria a rejeição indistinguível nos
registros de dim_pedidos. motivo_rejeicao="eleitoral" mantém isso auditável e
reversível (basta esvaziar as listas do JSON ao final do período eleitoral).

Risco conhecido: casamento por palavra/frase inteira, não por entidade.
"Lula" é também a palavra usada para o molusco (lula frita, lula à dorê) —
uma transcrição que mencione o prato vai ser bloqueada por engano. Aceito
como erro de recusa (o requisito é errar para esse lado), mas registrado
aqui para não ficar escondido.

Casamento de musicas_proibidas (lista do apêndice A da spec, 111 entradas):
cada entrada tem um ou mais títulos (canônico + aliases). O título do pedido
bloqueia por igualdade exata contra algum título normalizado da entrada — não
por substring, para não pegar títulos que apenas contêm uma palavra da lista.
Entradas de palavra comum (`exige_artista: true`, 20 delas) só bloqueiam se o
artista do pedido também casar com algum artista conhecido da entrada, por
contenção de palavra inteira em qualquer direção (cobre apelidos/abreviações:
"Racionais" casa com "Racionais MC's", "Titãs" casa com "Os Titãs"). Artista
vazio nunca casa — e o gate roda antes da checagem de campos vazios do
pipeline, então chegar aqui sem artista é esperado.

Validação do arquivo editado: `python -m core.eleitoral`.
"""

from __future__ import annotations

import json
import os
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

# Lista embutida na imagem: é o padrão quando o cliente não monta a dele, e a
# rede de segurança quando a dele está quebrada.
_JSON_PATH = Path(__file__).parent / "eleitoral.json"

_cache: dict = {"data": None, "mtime": None, "path": None}


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


# ---------------------------------------------------------------------------
# Carga da lista
# ---------------------------------------------------------------------------

def _normalizar(texto: str) -> str:
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c)
    )
    sem_acento = sem_acento.lower().strip()
    return re.sub(r"\s+", " ", sem_acento)


def _parse(bruto: str) -> dict:
    """Valida o JSON e devolve `{"candidatos": [...], "musicas_proibidas": [...]}`.

    Levanta ValueError apontando a entrada e a causa. A mensagem é o que o
    cliente vê no `python -m core.eleitoral` e no log do servidor, então ela
    precisa dizer qual linha do arquivo corrigir.

    As duas últimas checagens eram testes de integridade quando a lista era
    código-fonte, e passam a valer na carga agora que ela é editada à mão:
    `exige_artista` sem artista nunca bloqueia nada, e título repetido entre
    entradas quase sempre é alias duplicado.
    """
    doc = json.loads(bruto)
    if not isinstance(doc, dict):
        raise ValueError("a raiz do arquivo precisa ser um objeto JSON")

    candidatos_raw = doc.get("candidatos", [])
    if not isinstance(candidatos_raw, list) or any(
        not isinstance(n, str) for n in candidatos_raw
    ):
        raise ValueError("'candidatos' precisa ser uma lista de textos")

    musicas_raw = doc.get("musicas_proibidas", [])
    if not isinstance(musicas_raw, list):
        raise ValueError("'musicas_proibidas' precisa ser uma lista")

    musicas: list[MusicaProibida] = []
    vistos: dict[str, int] = {}
    for i, item in enumerate(musicas_raw):
        if not isinstance(item, dict):
            raise ValueError(f"entrada {i} de 'musicas_proibidas' precisa ser um objeto")

        titulos = item.get("titulos", [])
        artistas = item.get("artistas", [])
        exige = item.get("exige_artista", False)
        rotulo = f"entrada {i}" + (f" ({titulos[0]!r})" if titulos and isinstance(titulos[0], str) else "")

        if (
            not isinstance(titulos, list)
            or not titulos
            or any(not isinstance(t, str) or not t.strip() for t in titulos)
        ):
            raise ValueError(f"{rotulo}: 'titulos' precisa ter ao menos um texto não vazio")
        if not isinstance(artistas, list) or any(not isinstance(a, str) for a in artistas):
            raise ValueError(f"{rotulo}: 'artistas' precisa ser uma lista de textos")
        if not isinstance(exige, bool):
            raise ValueError(f"{rotulo}: 'exige_artista' precisa ser true ou false")
        if exige and not artistas:
            raise ValueError(
                f"{rotulo}: exige_artista=true sem 'artistas' — a entrada nunca bloquearia"
            )

        for titulo in titulos:
            norm = _normalizar(titulo)
            if norm in vistos:
                raise ValueError(
                    f"{rotulo}: título {norm!r} já aparece na entrada {vistos[norm]}"
                )
            vistos[norm] = i

        musicas.append(MusicaProibida(tuple(titulos), tuple(artistas), exige))

    return {"candidatos": candidatos_raw, "musicas_proibidas": musicas}


def _load() -> dict:
    """Relê a lista se o arquivo ou o caminho mudou; senão devolve o cache.

    Espelha core/luzia._load(): ELEITORAL_LISTA_PATH tem prioridade, o
    embutido é o fallback, e nenhuma falha de leitura deixa o filtro sem
    lista.
    """
    configurado = os.getenv("ELEITORAL_LISTA_PATH", "").strip()
    caminho = Path(configurado) if configurado else _JSON_PATH
    # is_file() também cobre o caso em que o bind mount, sem o arquivo no
    # host, criou uma PASTA com esse nome dentro do container.
    if not caminho.is_file():
        caminho = _JSON_PATH

    try:
        mtime = caminho.stat().st_mtime
    except OSError as e:
        if _cache["data"] is not None:
            return _cache["data"]
        raise RuntimeError(f"eleitoral.json não encontrado: {e}") from e

    if mtime != _cache["mtime"] or caminho != _cache["path"] or _cache["data"] is None:
        try:
            data = _parse(caminho.read_text(encoding="utf-8"))
        except Exception as e:
            if _cache["data"] is not None:
                print(f"[ELEITORAL] Falha ao reler a lista ({e}); mantendo a versão anterior.")
                return _cache["data"]
            if caminho != _JSON_PATH:
                # Lista do cliente nunca carregou: usa a embutida em vez de
                # derrubar o servidor — e em vez de rodar sem filtro nenhum.
                print(f"[ELEITORAL] Lista do cliente inválida ({e}); usando a embutida na imagem.")
                data = _parse(_JSON_PATH.read_text(encoding="utf-8"))
                caminho, mtime = _JSON_PATH, _JSON_PATH.stat().st_mtime
            else:
                raise

        _cache.update(data=data, mtime=mtime, path=caminho)
        n_musicas, n_candidatos = len(data["musicas_proibidas"]), len(data["candidatos"])
        print(
            f"[ELEITORAL] Lista carregada de {caminho}: "
            f"{n_musicas} músicas, {n_candidatos} candidatos."
        )
        if not n_musicas and not n_candidatos:
            print("[ELEITORAL] ATENÇÃO: as duas listas estão vazias — nada será bloqueado.")

    return _cache["data"]


def candidatos() -> list[str]:
    """Nomes vetados na transcrição do áudio, segundo a lista em vigor."""
    return _load()["candidatos"]


def musicas_proibidas() -> list[MusicaProibida]:
    """Entradas de bloqueio por título, segundo a lista em vigor."""
    return _load()["musicas_proibidas"]


# A lista deixou de ser código-fonte: este log no boot é o que registra, nos
# logs do cliente, qual versão dela entrou em vigor. Uma exceção aqui só
# acontece se o JSON embutido na imagem estiver quebrado — defeito de build,
# que deve impedir a subida em vez de passar a rodar sem filtro.
#
# Fora do `python -m core.eleitoral`: lá o módulo é o programa, faz a própria
# carga, e esta adiantaria o relatório de fallback antes do veredito.
if __name__ != "__main__":
    _load()


# ---------------------------------------------------------------------------
# Casamento
# ---------------------------------------------------------------------------

def contem_candidato(texto: str) -> bool:
    """True se `texto` (transcrição de áudio) menciona algum nome da lista de
    candidatos. Casamento por frase inteira, sem acento/caixa — evita que uma
    palavra vire substring de outra, mas não distingue sentido (ver risco do
    módulo)."""
    if not texto:
        return False
    alvo = _normalizar(texto)
    for nome in candidatos():
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
    item da lista de músicas proibidas.

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
    for entrada in musicas_proibidas():
        titulos_norm = {_normalizar(titulo) for titulo in entrada.titulos}
        if alvo_titulo not in titulos_norm:
            continue
        if not entrada.exige_artista:
            return True
        if _artista_casa(alvo_artista, entrada.artistas):
            return True
    return False


if __name__ == "__main__":
    # `python -m core.eleitoral` — valida o arquivo em vigor ANTES de o
    # servidor tentar usá-lo. Mesmo papel do `python -m core.luzia.schema`
    # para o perfil da assistente.
    import sys

    _configurado = os.getenv("ELEITORAL_LISTA_PATH", "").strip()
    _alvo = Path(_configurado) if _configurado else _JSON_PATH
    if not _alvo.is_file():
        print(f"✗ arquivo não encontrado: {_alvo}")
        sys.exit(1)
    try:
        _data = _parse(_alvo.read_text(encoding="utf-8"))
    except Exception as _e:
        print(f"✗ {_alvo}: {_e}")
        sys.exit(1)
    print(
        f"✓ {_alvo} válido — {len(_data['musicas_proibidas'])} músicas, "
        f"{len(_data['candidatos'])} candidatos."
    )
