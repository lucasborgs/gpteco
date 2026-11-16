"""Convite opcional para voz após o segundo pedido atendido por texto.

A contagem vem dos pedidos atendidos, incluindo o recém-registrado, desde o
último pedido por voz no histórico consultado. Pedidos por texto continuam
aceitos, sem período de bloqueio. Um pedido por voz zera a contagem.
A consulta não é armazenada em memória, preservando a regra após reinícios.
"""

from __future__ import annotations

import os

from core import database

CANAL_VOZ_ATIVADO: bool = os.getenv("CANAL_VOZ_ATIVADO", "true").strip().lower() == "true"
CANAL_HISTORICO_DIAS: int = int(os.getenv("CANAL_HISTORICO_DIAS", "90"))


def sugerir_voz(numero: str) -> bool:
    """Indica se a confirmação deve convidar para áudio, sem recusar texto."""
    if not CANAL_VOZ_ATIVADO:
        return False

    textos = 0
    for _, canal in database.pedidos_atendidos_por_canal(numero, CANAL_HISTORICO_DIAS):
        if canal == "voz":
            textos = 0
        elif canal == "texto":
            textos += 1
        # Linhas antigas sem canal não alteram a contagem.
    return textos >= 2
