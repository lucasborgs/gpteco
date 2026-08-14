"""Autorização editorial determinística para pedidos confirmáveis.

O Router pode extrair artista, música, gênero e década, mas nunca autoriza um
pedido. Esta regra é a única autoridade antes do cooldown e da confirmação.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from core import luzia


def _key(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().casefold())


def _items(value: str) -> frozenset[str]:
    return frozenset(
        _key(item.removeprefix("-").strip())
        for item in value.replace("\n", ",").split(",")
        if item.removeprefix("-").strip()
    )


@dataclass(frozen=True, slots=True)
class RepertoireRules:
    genres: frozenset[str]
    decades: frozenset[str]
    artists: frozenset[str]
    inclusions: frozenset[str]
    exclusions: frozenset[str]

    @classmethod
    def from_profile(cls) -> "RepertoireRules":
        config = luzia.repertoire_configuration()
        return cls(
            genres=_items(config["generos"]),
            decades=_items(config["decadas"]),
            artists=_items(config["artistas"]),
            inclusions=_items(config["inclusoes"]),
            exclusions=_items(config["exclusoes"]),
        )

    def allows(self, *, artist: str, music: str, genre: str, decade: str) -> bool:
        artist_key, music_key = _key(artist), _key(music)
        genre_key, decade_key = _key(genre), _key(decade)
        if not artist_key or not music_key:
            return False
        candidates = {artist_key, music_key, f"{artist_key} - {music_key}", genre_key, decade_key}
        candidates.discard("")
        # Exclusões sempre vencem inclusões (inclusive artistas específicos).
        if self.exclusions & candidates:
            return False
        if self.inclusions & candidates or artist_key in self.artists:
            return True
        # Sem metadado editorial suficiente, negar é mais seguro que assumir.
        if not genre_key:
            return False
        if "todos" not in self.genres and genre_key not in self.genres:
            return False
        if "todos" not in self.decades:
            if not decade_key or decade_key not in self.decades:
                return False
        return True


class DeterministicRepertoireChecker:
    """Adaptador simples para o seam de autorização editorial."""

    def __init__(self, rules: RepertoireRules) -> None:
        self._rules = rules

    @classmethod
    def from_profile(cls) -> "DeterministicRepertoireChecker":
        return cls(RepertoireRules.from_profile())

    def allows(self, artist: str, music: str, genre: str, decade: str) -> bool:
        return self._rules.allows(artist=artist, music=music, genre=genre, decade=decade)
