"""Opening database presentation models."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class OpeningMove:
    uci: str
    san: str
    games: int
    frequency: float
