"""
core/luzia/schema.py

Validador de luzia.md. Roda no CI (ou manualmente) para impedir que uma edição
do time da rádio quebre o servidor em produção.

Uso:
    python -m core.luzia.schema

Sai com código 0 se válido, 1 se houver erro (com lista de problemas).
"""

from __future__ import annotations

import sys

from core import luzia

# Mensagens canned obrigatórias e os placeholders permitidos em cada uma.
_MENSAGENS_OBRIGATORIAS = {
    "sucesso": {"artista", "musica"},
    "saudacao": set(),
    "menu_pos_sucesso": set(),
    "aguardando_pedido": set(),
    "producao_ativado": set(),
    "encerramento": set(),
    "cooldown": set(),
    "inapropriado": set(),
    "nao_repertorio": {"musica", "artista"},
    "nao_id": set(),
    "confirmacao": {"musica", "artista"},
    "pilula_prefixo": set(),
}

_FRONTMATTER_OBRIGATORIO = {"nome_radio", "ano_maximo", "versao"}
_TOKENS_CLASSIFICADOR = ("[[nome_radio]]", "[[genero_aceito]]", "[[restricao_ano]]")

import re

_PLACEHOLDER = re.compile(r"\{(\w+)\}")


def validar() -> list[str]:
    erros: list[str] = []
    d = luzia._load()
    fm = d["frontmatter"]
    secoes = d["secoes"]

    # 1. Frontmatter
    faltando = _FRONTMATTER_OBRIGATORIO - set(fm.keys())
    if faltando:
        erros.append(f"Frontmatter sem campos obrigatórios: {sorted(faltando)}")

    # 2. Seções obrigatórias presentes
    for canon in ("mensagens", "tom", "regras_duras", "composer", "curador",
                  "repertorio", "classificador"):
        if canon not in secoes:
            erros.append(f"Seção obrigatória ausente: '{canon}'")

    # 3. Mensagens canned + placeholders válidos
    msgs = secoes.get("mensagens", {}).get("subs", {})
    for slug, permitidos in _MENSAGENS_OBRIGATORIAS.items():
        if slug not in msgs:
            erros.append(f"Mensagem obrigatória ausente: '## {slug}'")
            continue
        usados = set(_PLACEHOLDER.findall(msgs[slug]))
        invalidos = usados - permitidos
        if invalidos:
            erros.append(
                f"Mensagem '{slug}' usa placeholder(s) inválido(s): {sorted(invalidos)} "
                f"(permitidos: {sorted(permitidos) or 'nenhum'})"
            )

    # 4. Situações de composer
    comp = secoes.get("composer", {}).get("subs", {})
    for situacao in luzia.SITUACOES_COMPOSER:
        if situacao not in comp:
            erros.append(f"Instrução de composer ausente: '## {situacao}'")

    # 5. Tokens do classificador presentes
    clf = secoes.get("classificador", {}).get("_text", "")
    for tok in _TOKENS_CLASSIFICADOR:
        if tok not in clf:
            erros.append(f"Classificador sem o token {tok} (substituição quebraria)")

    # 6. build_system_prompt() não pode levantar exceção
    try:
        luzia.build_system_prompt()
    except Exception as e:
        erros.append(f"build_system_prompt() falhou: {e}")

    return erros


def main() -> int:
    erros = validar()
    if erros:
        print("luzia.md INVÁLIDO:")
        for e in erros:
            print(f"  ✗ {e}")
        return 1
    print("luzia.md válido ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
