"""Typed building blocks for deterministic version 2 flow policies."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Literal, TypeAlias

ColorName: TypeAlias = Literal["white", "black"]
PieceTypeName: TypeAlias = Literal["pawn", "knight", "bishop", "rook", "queen", "king"]


@dataclass(frozen=True, slots=True)
class OriginalPieceId:
    color: ColorName
    start_square: str

    @classmethod
    def parse(cls, value: str) -> OriginalPieceId:
        parts = value.split(":")
        if len(parts) != 2 or parts[0] not in {"white", "black"}:
            raise ValueError(
                f"Invalid original-piece id {value!r}; expected 'white:e2'."
            )
        import chess

        if parts[1] not in chess.SQUARE_NAMES:
            raise ValueError(f"Invalid original-piece square {parts[1]!r}.")
        return cls(parts[0], parts[1])  # type: ignore[arg-type]

    def __str__(self) -> str:
        return f"{self.color}:{self.start_square}"


@dataclass(frozen=True, slots=True)
class MoveAction:
    piece: OriginalPieceId
    to_square: str


@dataclass(frozen=True, slots=True)
class MovedCondition:
    piece: OriginalPieceId


@dataclass(frozen=True, slots=True)
class AtCondition:
    piece: OriginalPieceId
    square: str


@dataclass(frozen=True, slots=True)
class OccupiedCondition:
    square: str


@dataclass(frozen=True, slots=True)
class EmptyCondition:
    square: str


@dataclass(frozen=True, slots=True)
class OccupiedByCondition:
    square: str
    color: ColorName
    piece_type: PieceTypeName


@dataclass(frozen=True, slots=True)
class AttackedCondition:
    piece: OriginalPieceId


@dataclass(frozen=True, slots=True)
class AttackedByCondition:
    target: OriginalPieceId
    attacker: OriginalPieceId


@dataclass(frozen=True, slots=True)
class InCheckCondition:
    color: ColorName


@dataclass(frozen=True, slots=True)
class StateCondition:
    state_id: str


@dataclass(frozen=True, slots=True)
class AllCondition:
    conditions: tuple[Condition, ...]


@dataclass(frozen=True, slots=True)
class AnyCondition:
    conditions: tuple[Condition, ...]


@dataclass(frozen=True, slots=True)
class NotCondition:
    condition: Condition


Condition: TypeAlias = (
    MovedCondition
    | AtCondition
    | OccupiedCondition
    | EmptyCondition
    | OccupiedByCondition
    | AttackedCondition
    | AttackedByCondition
    | InCheckCondition
    | StateCondition
    | AllCondition
    | AnyCondition
    | NotCondition
)


class RuleLifecycle(str, Enum):
    DORMANT = "dormant"
    ACTIVE = "active"
    RETIRED = "retired"


class EffectiveRuleStatus(str, Enum):
    SELECTED = "selected"
    ACTIVE = "active"
    WAITING = "waiting"
    DORMANT = "dormant"
    RETIRED = "retired"
    DISABLED = "disabled"


@dataclass(frozen=True, slots=True)
class ConditionResult:
    value: bool
    explanation: str
