"""Parsing, serialization, validation, and evaluation for v2 conditions."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import chess

from .models import (
    AllCondition,
    AnyCondition,
    AtCondition,
    AttackedByCondition,
    AttackedCondition,
    Condition,
    ConditionResult,
    ColorName,
    EmptyCondition,
    InCheckCondition,
    MovedCondition,
    NotCondition,
    OccupiedByCondition,
    OccupiedCondition,
    OriginalPieceId,
    StateCondition,
)
from .tracker import OriginalPieceTracker

PIECE_TYPES = {
    "pawn": chess.PAWN,
    "knight": chess.KNIGHT,
    "bishop": chess.BISHOP,
    "rook": chess.ROOK,
    "queen": chess.QUEEN,
    "king": chess.KING,
}


def parse_condition(value: object, *, context: str = "condition") -> Condition:
    mapping = _mapping(value, context)
    if len(mapping) != 1:
        raise ValueError(f"{context} must contain exactly one condition operator.")
    kind, payload = next(iter(mapping.items()))
    if kind == "moved":
        return MovedCondition(_piece_id(payload, context))
    if kind == "at":
        item = _exact_mapping(payload, {"piece", "square"}, context)
        return AtCondition(
            _piece_id(item["piece"], context), _square(item["square"], context)
        )
    if kind in {"occupied", "empty"}:
        square = _square(payload, context)
        return (
            OccupiedCondition(square) if kind == "occupied" else EmptyCondition(square)
        )
    if kind == "occupied_by":
        item = _exact_mapping(payload, {"square", "color", "type"}, context)
        color = _color(item["color"], context)
        piece_type = item["type"]
        if not isinstance(piece_type, str) or piece_type not in PIECE_TYPES:
            raise ValueError(f"{context} has invalid piece type {piece_type!r}.")
        return OccupiedByCondition(
            _square(item["square"], context), color, piece_type  # type: ignore[arg-type]
        )
    if kind == "attacked":
        return AttackedCondition(_piece_id(payload, context))
    if kind == "attacked_by":
        item = _exact_mapping(payload, {"target", "attacker"}, context)
        return AttackedByCondition(
            _piece_id(item["target"], context),
            _piece_id(item["attacker"], context),
        )
    if kind == "in_check":
        return InCheckCondition(_color(payload, context))
    if kind == "state":
        if not isinstance(payload, str) or not payload.strip():
            raise ValueError(f"{context} state id must be a non-empty string.")
        return StateCondition(payload)
    if kind in {"all", "any"}:
        if not isinstance(payload, list) or not payload:
            raise ValueError(f"{context} {kind} must be a non-empty array.")
        children = tuple(
            parse_condition(item, context=f"{context}.{kind}[{index}]")
            for index, item in enumerate(payload)
        )
        return AllCondition(children) if kind == "all" else AnyCondition(children)
    if kind == "not":
        return NotCondition(parse_condition(payload, context=f"{context}.not"))
    raise ValueError(f"{context} uses unsupported condition operator {kind!r}.")


def condition_to_data(condition: Condition) -> dict[str, object]:
    if isinstance(condition, MovedCondition):
        return {"moved": str(condition.piece)}
    if isinstance(condition, AtCondition):
        return {"at": {"piece": str(condition.piece), "square": condition.square}}
    if isinstance(condition, OccupiedCondition):
        return {"occupied": condition.square}
    if isinstance(condition, EmptyCondition):
        return {"empty": condition.square}
    if isinstance(condition, OccupiedByCondition):
        return {
            "occupied_by": {
                "square": condition.square,
                "color": condition.color,
                "type": condition.piece_type,
            }
        }
    if isinstance(condition, AttackedCondition):
        return {"attacked": str(condition.piece)}
    if isinstance(condition, AttackedByCondition):
        return {
            "attacked_by": {
                "target": str(condition.target),
                "attacker": str(condition.attacker),
            }
        }
    if isinstance(condition, InCheckCondition):
        return {"in_check": condition.color}
    if isinstance(condition, StateCondition):
        return {"state": condition.state_id}
    if isinstance(condition, AllCondition):
        return {"all": [condition_to_data(item) for item in condition.conditions]}
    if isinstance(condition, AnyCondition):
        return {"any": [condition_to_data(item) for item in condition.conditions]}
    return {"not": condition_to_data(condition.condition)}


def referenced_states(condition: Condition) -> set[str]:
    if isinstance(condition, StateCondition):
        return {condition.state_id}
    if isinstance(condition, (AllCondition, AnyCondition)):
        return set().union(*(referenced_states(item) for item in condition.conditions))
    if isinstance(condition, NotCondition):
        return referenced_states(condition.condition)
    return set()


def referenced_pieces(condition: Condition) -> set[OriginalPieceId]:
    if isinstance(condition, (MovedCondition, AtCondition, AttackedCondition)):
        return {condition.piece}
    if isinstance(condition, AttackedByCondition):
        return {condition.target, condition.attacker}
    if isinstance(condition, (AllCondition, AnyCondition)):
        return set().union(*(referenced_pieces(item) for item in condition.conditions))
    if isinstance(condition, NotCondition):
        return referenced_pieces(condition.condition)
    return set()


class ConditionEvaluator:
    def __init__(
        self,
        board: chess.Board,
        tracker: OriginalPieceTracker,
        states: Mapping[str, Condition],
    ) -> None:
        self.board = board
        self.tracker = tracker
        self.states = states

    def evaluate(self, condition: Condition) -> ConditionResult:
        return self._evaluate(condition, ())

    def _evaluate(
        self, condition: Condition, stack: tuple[str, ...]
    ) -> ConditionResult:
        if isinstance(condition, MovedCondition):
            value = self.tracker.get(condition.piece).has_moved
            return ConditionResult(
                value, f"{condition.piece} has{' ' if value else ' not '}moved"
            )
        if isinstance(condition, AtCondition):
            runtime = self.tracker.get(condition.piece)
            value = runtime.current_square == chess.parse_square(condition.square)
            return ConditionResult(
                value,
                f"{condition.piece} is{' ' if value else ' not '}on {condition.square}",
            )
        if isinstance(condition, OccupiedCondition):
            value = (
                self.board.piece_at(chess.parse_square(condition.square)) is not None
            )
            return ConditionResult(
                value, f"{condition.square} is{' ' if value else ' not '}occupied"
            )
        if isinstance(condition, EmptyCondition):
            value = self.board.piece_at(chess.parse_square(condition.square)) is None
            return ConditionResult(
                value, f"{condition.square} is{' ' if value else ' not '}empty"
            )
        if isinstance(condition, OccupiedByCondition):
            piece = self.board.piece_at(chess.parse_square(condition.square))
            color = chess.WHITE if condition.color == "white" else chess.BLACK
            value = (
                piece is not None
                and piece.color == color
                and piece.piece_type == PIECE_TYPES[condition.piece_type]
            )
            return ConditionResult(
                value,
                f"{condition.square} is{' ' if value else ' not '}occupied by a {condition.color} {condition.piece_type}",
            )
        if isinstance(condition, AttackedCondition):
            runtime = self.tracker.get(condition.piece)
            color = chess.WHITE if condition.piece.color == "white" else chess.BLACK
            value = runtime.current_square is not None and self.board.is_attacked_by(
                not color, runtime.current_square
            )
            return ConditionResult(
                value, f"{condition.piece} is{' ' if value else ' not '}attacked"
            )
        if isinstance(condition, AttackedByCondition):
            target = self.tracker.get(condition.target).current_square
            attacker = self.tracker.get(condition.attacker).current_square
            value = (
                target is not None
                and attacker is not None
                and target in self.board.attacks(attacker)
            )
            return ConditionResult(
                value,
                f"{condition.target} is{' ' if value else ' not '}attacked by {condition.attacker}",
            )
        if isinstance(condition, InCheckCondition):
            color = chess.WHITE if condition.color == "white" else chess.BLACK
            king = self.board.king(color)
            value = king is not None and self.board.is_attacked_by(not color, king)
            return ConditionResult(
                value, f"{condition.color} is{' ' if value else ' not '}in check"
            )
        if isinstance(condition, StateCondition):
            if condition.state_id in stack:
                raise ValueError(f"Recursive named state {condition.state_id!r}.")
            result = self._evaluate(
                self.states[condition.state_id], stack + (condition.state_id,)
            )
            return ConditionResult(
                result.value, f"state {condition.state_id}: {result.explanation}"
            )
        if isinstance(condition, AllCondition):
            results = tuple(
                self._evaluate(item, stack) for item in condition.conditions
            )
            return ConditionResult(
                all(item.value for item in results),
                "; ".join(item.explanation for item in results),
            )
        if isinstance(condition, AnyCondition):
            results = tuple(
                self._evaluate(item, stack) for item in condition.conditions
            )
            return ConditionResult(
                any(item.value for item in results),
                " or ".join(item.explanation for item in results),
            )
        result = self._evaluate(condition.condition, stack)
        return ConditionResult(not result.value, f"not ({result.explanation})")


def _mapping(value: object, context: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise TypeError(f"{context} must be a table/object.")
    return value


def _exact_mapping(value: object, fields: set[str], context: str) -> dict[str, Any]:
    mapping = _mapping(value, context)
    if set(mapping) != fields:
        raise ValueError(f"{context} must contain exactly {sorted(fields)}.")
    return mapping


def _piece_id(value: object, context: str) -> OriginalPieceId:
    if not isinstance(value, str):
        raise TypeError(f"{context} original-piece id must be a string.")
    return OriginalPieceId.parse(value)


def _square(value: object, context: str) -> str:
    if not isinstance(value, str) or value not in chess.SQUARE_NAMES:
        raise ValueError(f"{context} has invalid square {value!r}.")
    return value


def _color(value: object, context: str) -> ColorName:
    if value not in {"white", "black"}:
        raise ValueError(f"{context} has invalid color {value!r}.")
    return value  # type: ignore[return-value]
