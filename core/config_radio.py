"""
core/config_radio.py

Shim de compatibilidade. A configuração da rádio agora vive em
core/luzia/luzia.md (editável pelo time da rádio, com hot-reload).

Este módulo é mantido apenas para não quebrar imports existentes
(`from core import config_radio`). Todo acesso é delegado, em tempo de
execução, para core/luzia — preservando o hot-reload (cada leitura relê o
.md se ele mudou).

Para alterar mensagens, tom ou o prompt da LuzIA: edite luzia.md.
"""

from __future__ import annotations

from core.luzia import build_system_prompt  # re-export direto (função real)

__all__ = ["build_system_prompt"]


def __getattr__(name: str):
    # Delega MSG_*, NOME_RADIO, GENERO_ACEITO, ANO_MAXIMO etc. para core.luzia,
    # que resolve cada um lendo luzia.md (com cache por mtime).
    from core import luzia
    return getattr(luzia, name)
