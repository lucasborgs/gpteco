"""
core/config_radio.py

Shim de compatibilidade. O perfil editável da rádio vive em
core/luzia/luzia.md (identidade, tom, repertório e mensagens, com hot-reload).

Este módulo é mantido apenas para não quebrar imports existentes
(`from core import config_radio`). Todo acesso é delegado, em tempo de
execução, para core/luzia — preservando o hot-reload (cada leitura relê o
.md se ele mudou).

Para alterar mensagens ou tom, edite luzia.md. O contrato técnico do
classificador permanece em código e não pode ser substituído pelo perfil.
"""

from __future__ import annotations

from core.luzia import build_system_prompt  # re-export direto (função real)

__all__ = ["build_system_prompt"]


def __getattr__(name: str):
    # Delega MSG_*, NOME_RADIO, GENERO_ACEITO, ANO_MAXIMO etc. para core.luzia,
    # que resolve cada um lendo luzia.md (com cache por mtime).
    from core import luzia
    return getattr(luzia, name)
