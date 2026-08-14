"""Perfil editável da rádio, separado das regras técnicas da aplicação.

O Markdown externo fornece identidade, tom, repertório e textos de fallback.
Schemas do Router, prioridade de intenções, confirmação, idempotência e
salvaguardas vivem abaixo, em constantes internas que o perfil não substitui.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

_MD_PATH = Path(__file__).parent / "luzia.md"
_cache: dict = {"mtime": 0.0, "path": None, "data": None}

_SECTION_KEYS = [("perfil", "perfil"), ("mensagens", "mensagens"), ("tom", "tom"),
                 ("repert", "repertorio"), ("exempl", "exemplos")]
_MSG_SLUG = {
    "MSG_SUCESSO": "sucesso", "MSG_COOLDOWN": "cooldown",
    "MSG_INAPROPRIADO": "inapropriado", "MSG_NAO_REPERTORIO": "nao_repertorio",
    "MSG_NAO_ID": "nao_id", "MSG_CONFIRMACAO": "confirmacao",
    "MSG_SAUDACAO": "saudacao", "MSG_AGUARDANDO_PEDIDO": "aguardando_pedido",
    "MSG_PRODUCAO_ATIVADO": "producao_ativado", "MSG_MENU_POS_SUCESSO": "menu_pos_sucesso",
    "MSG_ENCERRAMENTO": "encerramento", "MSG_LLM_UNAVAILABLE": "llm_unavailable",
}
SITUACOES_COMPOSER = ("nao_repertorio", "cooldown", "inapropriado", "nao_id", "confirmacao")

# Estas instruções são internas. O perfil só é interpolado como dados de
# marca/repertório, nunca como trecho que muda o protocolo do sistema.
_ROUTER_TECHNICAL_PROMPT = """Você extrai dados para uma assistente musical.
Retorne apenas JSON com intent, artist, music, genre, decade, confidence, answer,
question, missing e inappropriate. Intenções válidas: production, complaint,
report, promotion, music_request, music_question, music_question_and_request,
greeting, off_topic, inappropriate, unclear. Nunca autorize repertório, nunca
execute ações e não prometa que uma faixa entrou na fila. Produção tem prioridade;
pedidos só serão executados após validação determinística e confirmação explícita."""
_LEGACY_CLASSIFIER_TECHNICAL_PROMPT = """Você é o classificador de pedidos
musicais de uma rádio brasileira. Retorne APENAS um objeto JSON válido com as
chaves is_pedido_musical, musica, artista, is_flashback, is_apropriado,
is_confiante, is_saudacao, is_pedido_explicito e genero. Extraia artista e
música quando houver pedido, normalize erros fonéticos apenas se estiver
confiante e deixe artista/musica vazios quando faltar dado. is_apropriado só
avalia ofensa direta. Não execute ações, não prometa inclusão na fila e não
delegue as regras de repertório para o modelo."""
_COMPOSER_GUARDRAILS = """A situação já foi decidida pelo sistema. Escreva uma
mensagem breve sem prometer horário, posição na fila, execução ou aviso futuro.
Não invente artista ou música fora do contexto e não mude a decisão."""
_CURATOR_GUARDRAILS = """Não altere fatos, não invente dados sobre o ouvinte e
não anuncie a mensagem como CURIOSIDADE."""


def _parse_frontmatter(block: str) -> dict[str, str]:
    return {
        key.strip(): value.strip()
        for line in block.splitlines() if ":" in line and not line.lstrip().startswith("#")
        for key, value in [line.split(":", 1)]
    }


def _clean(lines: list[str]) -> str:
    return "\n".join(line for line in lines if not line.lstrip().startswith(">")).strip()


def _subsections(lines: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    current: str | None = None
    buffer: list[str] = []
    for line in lines:
        if line.startswith("## "):
            if current is not None:
                result[current] = _clean(buffer)
            current, buffer = line[3:].strip().casefold(), []
        elif current is not None:
            buffer.append(line)
    if current is not None:
        result[current] = _clean(buffer)
    return result


def _parse(text: str) -> dict:
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    frontmatter: dict[str, str] = {}
    body = text
    match = re.match(r"\s*---\n(.*?)\n---\n(.*)", text, flags=re.DOTALL)
    if match:
        frontmatter, body = _parse_frontmatter(match.group(1)), match.group(2)
    sections: dict[str, dict[str, object]] = {}
    title: str | None = None
    lines: list[str] = []

    def store() -> None:
        if title is None:
            return
        canonical = next((value for needle, value in _SECTION_KEYS if needle in title.casefold()), None)
        # Seções desconhecidas e antigas regras técnicas são ignoradas: elas não
        # entram em nenhum prompt protegido.
        if canonical:
            sections[canonical] = {"subs": _subsections(lines), "_text": _clean(lines)}

    for line in body.splitlines():
        if line.startswith("# "):
            store()
            title, lines = line[2:].strip(), []
        elif title is not None:
            lines.append(line)
    store()
    return {"frontmatter": frontmatter, "secoes": sections}


def _validate_structure(data: dict) -> None:
    sections = data.get("secoes", {})
    required = {"perfil", "mensagens", "tom", "repertorio"}
    missing = required - set(sections)
    if missing:
        raise ValueError(f"seções editáveis ausentes: {sorted(missing)}")
    required_repertoire = {"generos", "decadas", "artistas", "inclusoes", "exclusoes"}
    missing_repertoire = required_repertoire - set(sections["repertorio"]["subs"])
    if missing_repertoire:
        raise ValueError(f"campos de repertório ausentes: {sorted(missing_repertoire)}")
    for field in ("generos", "decadas"):
        if not str(sections["repertorio"]["subs"][field]).strip():
            raise ValueError(f"campo de repertório vazio: '{field}'")
    required_messages = set(_MSG_SLUG.values()) | {"pilula_prefixo"}
    missing_messages = required_messages - set(sections["mensagens"]["subs"])
    if missing_messages:
        raise ValueError(f"mensagens obrigatórias ausentes: {sorted(missing_messages)}")


def _load() -> dict:
    """Hot reload com retenção da última versão de perfil válida."""
    configured = os.getenv("ASSISTANT_PROFILE_PATH", "").strip()
    candidate = Path(configured) if configured else _MD_PATH
    if not candidate.is_file():
        candidate = _MD_PATH
    try:
        mtime = candidate.stat().st_mtime
    except OSError as error:
        if _cache["data"] is not None:
            return _cache["data"]
        raise RuntimeError(f"perfil da assistente não encontrado: {error}") from error
    if mtime != _cache["mtime"] or candidate != _cache["path"] or _cache["data"] is None:
        try:
            data = _parse(candidate.read_text(encoding="utf-8"))
            _validate_structure(data)
            _cache.update(data=data, mtime=mtime, path=candidate)
        except Exception as error:
            if _cache["data"] is not None:
                print(f"[LUZIA] Perfil inválido ({error}); mantendo última versão válida.")
                return _cache["data"]
            if candidate != _MD_PATH:
                data = _parse(_MD_PATH.read_text(encoding="utf-8"))
                _validate_structure(data)
                _cache.update(data=data, mtime=_MD_PATH.stat().st_mtime, path=_MD_PATH)
            else:
                raise
    return _cache["data"]


def _msg(slug: str) -> str:
    return str(_load()["secoes"]["mensagens"]["subs"][slug])


def _frontmatter(key: str, default: str = "") -> str:
    return str(_load()["frontmatter"].get(key, default))


def repertoire_configuration() -> dict[str, str]:
    """Configuração declarativa consumida pelo verificador determinístico."""
    subs = _load()["secoes"]["repertorio"]["subs"]
    return {key: str(subs[key]) for key in ("generos", "decadas", "artistas", "inclusoes", "exclusoes")}


def build_system_prompt() -> str:
    """Prompt legado técnico interno; o perfil externo entra só como dados."""
    profile = _load()
    return (
        f"{_LEGACY_CLASSIFIER_TECHNICAL_PROMPT}\n\nRádio: {_frontmatter('nome_radio')}.\n"
        f"Perfil editorial configurado:\n{profile['secoes']['repertorio']['_text']}"
    )


def router_technical_prompt() -> str:
    """Contrato protegido do Router conversacional, independente do Markdown."""
    return _ROUTER_TECHNICAL_PROMPT


def diretrizes_luzia() -> str:
    return f"{_load()['secoes']['tom']['_text']}\n\n{_COMPOSER_GUARDRAILS}".strip()


def instrucao_composer(situacao: str) -> str:
    if situacao not in SITUACOES_COMPOSER:
        raise KeyError(f"Situação de composer desconhecida: '{situacao}'")
    examples = _load()["secoes"].get("exemplos", {}).get("subs", {})
    return str(examples.get(situacao, "Use o tom e as mensagens fixas configurados."))


def instrucao_curador_contexto() -> str:
    examples = _load()["secoes"].get("exemplos", {}).get("subs", {})
    return f"{_CURATOR_GUARDRAILS}\n{examples.get('curador', '')}".strip()


def __getattr__(name: str):
    if name in _MSG_SLUG:
        return _msg(_MSG_SLUG[name])
    if name == "MSG_PILULA_PREFIXO":
        return _msg("pilula_prefixo") + "\n\n"
    if name == "NOME_RADIO":
        return _frontmatter("nome_radio")
    if name == "ANO_MAXIMO":
        return _frontmatter("ano_maximo", "sem_restricao")
    if name == "GENERO_ACEITO":
        return repertoire_configuration()["generos"]
    raise AttributeError(f"module 'core.luzia' has no attribute '{name}'")
