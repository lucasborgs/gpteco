"""Validação do perfil editável da assistente.

Uso: ``python -m core.luzia.schema``. Regras técnicas não pertencem ao arquivo
e são verificadas no código que monta os prompts protegidos.
"""

from __future__ import annotations

import sys

from core import luzia


def validar() -> list[str]:
    try:
        data = luzia._load()
        luzia._validate_structure(data)
        luzia.repertoire_configuration()
        prompt = luzia.build_system_prompt()
    except Exception as error:
        return [str(error)]
    if not prompt:
        return ["prompt técnico interno vazio"]
    return []


def main() -> int:
    errors = validar()
    if errors:
        print("perfil da assistente INVÁLIDO:")
        for error in errors:
            print(f"  ✗ {error}")
        return 1
    print("perfil da assistente válido ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
