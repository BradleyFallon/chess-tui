"""Book data and generic opponent suggestion models."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


@dataclass(frozen=True, slots=True)
class OpeningMove:
    uci: str
    san: str
    games: int
    frequency: float


class SuggestionKind(str, Enum):
    BOOK = "book"
    BOT = "bot"
    ENGINE_BEST = "engine-best"
    GENERATED_MISTAKE = "generated-mistake"


@dataclass(frozen=True, slots=True)
class MoveSuggestion:
    uci: str
    san: str
    kind: SuggestionKind
    label: str
    games: int | None = None
    frequency: float | None = None
    profile_id: str | None = None
    evaluation_cp: int | None = None
    loss_cp: int | None = None
