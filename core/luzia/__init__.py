"""
core/luzia/__init__.py

Carrega a "constituição" da LuzIA a partir de core/luzia/luzia.md e expõe a
mesma API pública que core/config_radio.py tinha — mais alguns acessos novos
usados pelo composer (recusas) e pelo curador contextual.

Por que markdown?
  - Versionável e revisável em git como qualquer texto.
  - Editável pelo time da rádio (tom e mensagens) sem mexer em Python.
  - Hot-reload: o servidor relê o arquivo quando ele muda (sem rebuild Docker).

Compatibilidade:
  As constantes MSG_* e build_system_prompt() continuam disponíveis com os
  mesmos nomes e valores de antes (ver core/luzia/schema.py para validação).

API pública:
    NOME_RADIO, GENERO_ACEITO, ANO_MAXIMO         (atributos)
    MSG_SUCESSO, MSG_COOLDOWN, ... MSG_ENCERRAMENTO (atributos)
    build_system_prompt() -> str
    diretrizes_luzia()    -> str   (tom + regras duras, p/ system prompt gerado)
    instrucao_composer(situacao) -> str
    instrucao_curador_contexto() -> str
"""

from __future__ import annotations

import re
from pathlib import Path

_MD_PATH = Path(__file__).parent / "luzia.md"

# Cache com invalidação por mtime + memória do último parse válido (resiliência:
# se alguém salvar um .md quebrado em produção, seguimos servindo o último bom).
_cache: dict = {"mtime": 0.0, "data": None}

# Mapeia título de seção (por palavra-chave, tolerante a emoji/acento) → chave canônica
_SECTION_KEYS = [
    ("mensagens", "mensagens"),
    ("tom da luzia", "tom"),
    ("regras duras", "regras_duras"),
    ("composer", "composer"),
    ("curador", "curador"),
    ("repert", "repertorio"),
    ("classificador", "classificador"),
]

# Constante MSG_* → slug da subseção em "# Mensagens fixas"
_MSG_SLUG = {
    "MSG_SUCESSO": "sucesso",
    "MSG_COOLDOWN": "cooldown",
    "MSG_INAPROPRIADO": "inapropriado",
    "MSG_ELEITORAL": "eleitoral",
    "MSG_NAO_REPERTORIO": "nao_repertorio",
    "MSG_NAO_ID": "nao_id",
    "MSG_CONFIRMACAO": "confirmacao",
    "MSG_SAUDACAO": "saudacao",
    "MSG_AGUARDANDO_PEDIDO": "aguardando_pedido",
    "MSG_PRODUCAO_ATIVADO": "producao_ativado",
    "MSG_MENU_POS_SUCESSO": "menu_pos_sucesso",
    "MSG_ENCERRAMENTO": "encerramento",
}

# Situações de recusa esperadas (usadas pelo composer)
SITUACOES_COMPOSER = ("nao_repertorio", "cooldown", "inapropriado", "nao_id", "confirmacao")


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def _parse_frontmatter(bloco: str) -> dict:
    """Frontmatter simples chave: valor (sem dependência de PyYAML)."""
    fm: dict = {}
    for linha in bloco.split("\n"):
        linha = linha.strip()
        if not linha or linha.startswith("#") or ":" not in linha:
            continue
        chave, valor = linha.split(":", 1)
        fm[chave.strip()] = valor.strip()
    return fm


def _clean_block(linhas: list[str]) -> str:
    """Remove linhas de orientação (começam com '>') e apara as pontas,
    preservando linhas em branco internas (relevante p/ mensagens com \\n\\n)."""
    mantidas = [l for l in linhas if not l.lstrip().startswith(">")]
    return "\n".join(mantidas).strip()


def _split_subsections(linhas: list[str]) -> dict:
    """Divide um bloco em subseções '## slug'. Ignora o preâmbulo antes da 1ª."""
    subs: dict = {}
    slug = None
    buf: list[str] = []
    for l in linhas:
        if l.startswith("## "):
            if slug is not None:
                subs[slug] = _clean_block(buf)
            slug = l[3:].strip()
            buf = []
        elif slug is not None:
            buf.append(l)
    if slug is not None:
        subs[slug] = _clean_block(buf)
    return subs


def _canonical(titulo: str) -> str | None:
    t = titulo.lower()
    for chave, canon in _SECTION_KEYS:
        if chave in t:
            return canon
    return None


def _parse(texto: str) -> dict:
    # Remove comentários HTML (<!-- ... -->) em qualquer posição
    texto = re.sub(r"<!--.*?-->", "", texto, flags=re.DOTALL)

    # Frontmatter entre os dois primeiros '---'
    frontmatter: dict = {}
    corpo = texto
    m = re.match(r"\s*---\n(.*?)\n---\n(.*)", texto, flags=re.DOTALL)
    if m:
        frontmatter = _parse_frontmatter(m.group(1))
        corpo = m.group(2)

    # Quebra o corpo em seções de nível 1 ('# ...')
    secoes_raw: list[tuple[str, list[str]]] = []
    atual: tuple[str, list[str]] | None = None
    for linha in corpo.split("\n"):
        if linha.startswith("# "):
            atual = (linha[2:].strip(), [])
            secoes_raw.append(atual)
        elif atual is not None:
            atual[1].append(linha)

    secoes: dict = {}
    for titulo, linhas in secoes_raw:
        canon = _canonical(titulo)
        if not canon:
            continue
        subs = _split_subsections(linhas)
        secoes[canon] = {"subs": subs, "_text": _clean_block(linhas)}

    return {"frontmatter": frontmatter, "secoes": secoes}


def _load() -> dict:
    """Relê luzia.md se o arquivo mudou; senão devolve o cache."""
    try:
        mtime = _MD_PATH.stat().st_mtime
    except OSError as e:
        if _cache["data"] is not None:
            return _cache["data"]
        raise RuntimeError(f"luzia.md não encontrado: {e}") from e

    if mtime != _cache["mtime"] or _cache["data"] is None:
        try:
            data = _parse(_MD_PATH.read_text(encoding="utf-8"))
            _cache["data"] = data
            _cache["mtime"] = mtime
        except Exception as e:  # parse quebrado → mantém último bom, loga
            if _cache["data"] is not None:
                print(f"[LUZIA] Falha ao reler luzia.md ({e}); mantendo versão anterior.")
                return _cache["data"]
            raise
    return _cache["data"]


# ---------------------------------------------------------------------------
# Acessos internos
# ---------------------------------------------------------------------------

def _msg(slug: str) -> str:
    d = _load()
    try:
        return d["secoes"]["mensagens"]["subs"][slug]
    except KeyError as e:
        raise AttributeError(f"Mensagem '{slug}' ausente em luzia.md") from e


def _frontmatter(chave: str, default: str = "") -> str:
    return _load()["frontmatter"].get(chave, default)


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

def build_system_prompt() -> str:
    """System prompt do classificador (intelligence.py). Reproduz o texto
    histórico: substitui [[nome_radio]], [[genero_aceito]] e [[restricao_ano]]."""
    d = _load()
    meta = d["frontmatter"]
    template = d["secoes"]["classificador"]["_text"]
    genero = d["secoes"]["repertorio"]["_text"]
    ano = meta.get("ano_maximo", "sem_restricao")
    restricao = (
        ""
        if ano == "sem_restricao"
        else f"Músicas lançadas após {ano} NÃO se qualificam para a programação desta rádio.\n"
    )
    return (
        template
        .replace("[[nome_radio]]", meta.get("nome_radio", ""))
        .replace("[[genero_aceito]]", genero)
        .replace("[[restricao_ano]]", restricao)
    ).strip()


def diretrizes_luzia() -> str:
    """Tom + regras duras concatenados — base do system prompt das mensagens
    geradas pela LuzIA (composer e curador contextual)."""
    d = _load()["secoes"]
    tom = d.get("tom", {}).get("_text", "")
    regras = d.get("regras_duras", {}).get("_text", "")
    return f"{tom}\n\n{regras}".strip()


def instrucao_composer(situacao: str) -> str:
    """Instrução específica de redação para uma situação de recusa."""
    d = _load()
    try:
        return d["secoes"]["composer"]["subs"][situacao]
    except KeyError as e:
        raise KeyError(f"Situação de composer desconhecida: '{situacao}'") from e


def instrucao_curador_contexto() -> str:
    """Instrução de como personalizar a pílula com o contexto do ouvinte."""
    return _load()["secoes"]["curador"]["_text"]


def __getattr__(name: str):
    """PEP 562: resolve MSG_*, NOME_RADIO, GENERO_ACEITO, ANO_MAXIMO sob demanda
    (garante hot-reload — cada acesso passa por _load())."""
    if name in _MSG_SLUG:
        return _msg(_MSG_SLUG[name])
    if name == "MSG_PILULA_PREFIXO":
        # O "\n\n" é estrutural (separa o prefixo do texto da curiosidade).
        return _msg("pilula_prefixo") + "\n\n"
    if name == "NOME_RADIO":
        return _frontmatter("nome_radio")
    if name == "ANO_MAXIMO":
        return _frontmatter("ano_maximo", "sem_restricao")
    if name == "GENERO_ACEITO":
        return _load()["secoes"]["repertorio"]["_text"]
    raise AttributeError(f"module 'core.luzia' has no attribute '{name}'")
