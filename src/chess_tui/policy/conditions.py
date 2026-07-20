"""Strict v4 condition parsing, serialization, and evaluation."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import chess

from .models import (
    AllCondition,
    AnyCondition,
    AtCondition,
    AttackBalanceCondition,
    AttackedByCondition,
    AttackedCondition,
    CapturableCondition,
    CapturedCondition,
    ColorName,
    Condition,
    ConditionResult,
    EmptyCondition,
    InCheckCondition,
    LastMove,
    LastMoveCondition,
    MovedCondition,
    NotCondition,
    OccupiedByCondition,
    OccupiedCondition,
    PieceSubject,
    PieceTypeName,
    StartingPieceRef,
    UndefendedCondition,
    UnderDefendedCondition,
    UnmovedCondition,
)
from .relations import PositionAnalyzer, PositionRelations
from .tracker import OriginalPieceTracker

PIECE_TYPES: dict[str, chess.PieceType] = {
    "pawn": chess.PAWN,
    "knight": chess.KNIGHT,
    "bishop": chess.BISHOP,
    "rook": chess.ROOK,
    "queen": chess.QUEEN,
    "king": chess.KING,
}


def parse_condition(
    value: object,
    *,
    context: str = "condition",
    aliases: Mapping[str, StartingPieceRef] | None = None,
) -> Condition:
    item = _mapping(value, context)
    if len(item) != 1:
        raise ValueError(f"{context} must contain exactly one condition operator.")
    kind, payload = next(iter(item.items()))
    if kind in {"moved", "unmoved", "captured"}:
        subject = _subject(payload, aliases, context)
        return {
            "moved": MovedCondition,
            "unmoved": UnmovedCondition,
            "captured": CapturedCondition,
        }[kind](subject)
    if kind == "at":
        data = _exact_mapping(payload, {"piece", "square"}, context)
        return AtCondition(
            _subject(data["piece"], aliases, context),
            _square(data["square"], context),
        )
    if kind in {"occupied", "empty"}:
        square = _square(payload, context)
        return (
            OccupiedCondition(square) if kind == "occupied" else EmptyCondition(square)
        )
    if kind == "occupied_by":
        data = _exact_mapping(payload, {"square", "color", "type"}, context)
        piece_type = _piece_type(data["type"], context)
        return OccupiedByCondition(
            _square(data["square"], context),
            _color(data["color"], context),
            piece_type,
        )
    if kind == "attacked":
        return AttackedCondition(_subject(payload, aliases, context))
    if kind == "attacked_by":
        data = _mapping(payload, context)
        if set(data) not in ({"target", "piece"}, {"target", "type"}):
            raise ValueError(
                f"{context}.attacked_by requires target and exactly one of piece or type."
            )
        return AttackedByCondition(
            target=_subject(data["target"], aliases, context),
            attacker=(
                _reference(data["piece"], aliases, context) if "piece" in data else None
            ),
            attacker_type=(
                _piece_type(data["type"], context) if "type" in data else None
            ),
        )
    if kind == "undefended":
        return UndefendedCondition(_subject(payload, aliases, context))
    if kind == "under_defended":
        return UnderDefendedCondition(_subject(payload, aliases, context))
    if kind == "attack_balance":
        data = _exact_mapping(payload, {"target", "at_least"}, context)
        threshold = data["at_least"]
        if not isinstance(threshold, int) or isinstance(threshold, bool):
            raise TypeError(f"{context}.attack_balance.at_least must be an integer.")
        return AttackBalanceCondition(
            _subject(data["target"], aliases, context), threshold
        )
    if kind == "capturable":
        return CapturableCondition(_reference(payload, aliases, context))
    if kind == "in_check":
        return InCheckCondition(_color(payload, context))
    if kind == "last_move":
        data = _exact_mapping(payload, {"piece", "to"}, context)
        return LastMoveCondition(
            _subject(data["piece"], aliases, context),
            _square(data["to"], context),
        )
    if kind in {"all", "any"}:
        if not isinstance(payload, list) or not payload:
            raise ValueError(f"{context}.{kind} must be a non-empty array.")
        children = tuple(
            parse_condition(
                child, context=f"{context}.{kind}[{index}]", aliases=aliases
            )
            for index, child in enumerate(payload)
        )
        return AllCondition(children) if kind == "all" else AnyCondition(children)
    if kind == "not":
        return NotCondition(
            parse_condition(payload, context=f"{context}.not", aliases=aliases)
        )
    raise ValueError(f"{context} uses unsupported condition operator {kind!r}.")


def condition_to_data(
    condition: Condition,
    *,
    aliases: Mapping[StartingPieceRef, str] | None = None,
) -> dict[str, object]:
    def subject(value: PieceSubject) -> str:
        return _serialize_subject(value, aliases)

    if isinstance(condition, MovedCondition):
        return {"moved": subject(condition.piece)}
    if isinstance(condition, UnmovedCondition):
        return {"unmoved": subject(condition.piece)}
    if isinstance(condition, CapturedCondition):
        return {"captured": subject(condition.piece)}
    if isinstance(condition, AtCondition):
        return {"at": {"piece": subject(condition.piece), "square": condition.square}}
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
        return {"attacked": subject(condition.target)}
    if isinstance(condition, AttackedByCondition):
        payload: dict[str, object] = {"target": subject(condition.target)}
        if condition.attacker is not None:
            payload["piece"] = subject(condition.attacker)
        else:
            payload["type"] = condition.attacker_type
        return {"attacked_by": payload}
    if isinstance(condition, UndefendedCondition):
        return {"undefended": subject(condition.target)}
    if isinstance(condition, UnderDefendedCondition):
        return {"under_defended": subject(condition.target)}
    if isinstance(condition, AttackBalanceCondition):
        return {
            "attack_balance": {
                "target": subject(condition.target),
                "at_least": condition.at_least,
            }
        }
    if isinstance(condition, CapturableCondition):
        return {"capturable": subject(condition.target)}
    if isinstance(condition, InCheckCondition):
        return {"in_check": condition.color}
    if isinstance(condition, LastMoveCondition):
        return {
            "last_move": {
                "piece": subject(condition.piece),
                "to": condition.to_square,
            }
        }
    if isinstance(condition, AllCondition):
        return {
            "all": [
                condition_to_data(child, aliases=aliases)
                for child in condition.conditions
            ]
        }
    if isinstance(condition, AnyCondition):
        return {
            "any": [
                condition_to_data(child, aliases=aliases)
                for child in condition.conditions
            ]
        }
    return {"not": condition_to_data(condition.condition, aliases=aliases)}


def referenced_pieces(condition: Condition) -> set[StartingPieceRef]:
    if isinstance(condition, (MovedCondition, UnmovedCondition, CapturedCondition)):
        return _reference_set(condition.piece)
    if isinstance(condition, AtCondition):
        return _reference_set(condition.piece)
    if isinstance(
        condition,
        (
            AttackedCondition,
            UndefendedCondition,
            UnderDefendedCondition,
            AttackBalanceCondition,
        ),
    ):
        return _reference_set(condition.target)
    if isinstance(condition, AttackedByCondition):
        return _reference_set(condition.target) | (
            {condition.attacker} if condition.attacker is not None else set()
        )
    if isinstance(condition, CapturableCondition):
        return {condition.target}
    if isinstance(condition, LastMoveCondition):
        return _reference_set(condition.piece)
    if isinstance(condition, (AllCondition, AnyCondition)):
        return set().union(
            *(referenced_pieces(child) for child in condition.conditions)
        )
    if isinstance(condition, NotCondition):
        return referenced_pieces(condition.condition)
    return set()


class ConditionEvaluator:
    def __init__(
        self,
        board: chess.Board,
        tracker: OriginalPieceTracker,
        *,
        relations: PositionRelations | None = None,
        last_move: LastMove | None = None,
        subject: StartingPieceRef | None = None,
    ) -> None:
        self.board = board
        self.tracker = tracker
        self.relations = relations or PositionAnalyzer().analyze(board, tracker)
        self.last_move = last_move
        self.subject = subject

    def evaluate(self, condition: Condition) -> ConditionResult:
        if isinstance(condition, MovedCondition):
            ref = self._resolve(condition.piece)
            value = self.tracker.get(ref.original_piece_id).has_moved
            return ConditionResult(
                value, f"{ref.label} has{' ' if value else ' not '}moved"
            )
        if isinstance(condition, UnmovedCondition):
            ref = self._resolve(condition.piece)
            runtime = self.tracker.get(ref.original_piece_id)
            value = not runtime.has_moved and not runtime.captured
            return ConditionResult(
                value, f"{ref.label} is{' ' if value else ' not '}unmoved"
            )
        if isinstance(condition, CapturedCondition):
            ref = self._resolve(condition.piece)
            value = self.tracker.get(ref.original_piece_id).captured
            return ConditionResult(
                value, f"{ref.label} is{' ' if value else ' not '}captured"
            )
        if isinstance(condition, AtCondition):
            ref = self._resolve(condition.piece)
            runtime = self.tracker.get(ref.original_piece_id)
            value = runtime.current_square == chess.parse_square(condition.square)
            return ConditionResult(
                value, f"{ref.label} is{' ' if value else ' not '}on {condition.square}"
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
            value = (
                piece is not None
                and piece.color == (condition.color == "white")
                and piece.piece_type == PIECE_TYPES[condition.piece_type]
            )
            return ConditionResult(
                value,
                f"{condition.square} is{' ' if value else ' not '}occupied by "
                f"a {condition.color} {condition.piece_type}",
            )
        if isinstance(condition, AttackedCondition):
            return self._relation_result(self._resolve(condition.target), "attacked")
        if isinstance(condition, UndefendedCondition):
            return self._relation_result(self._resolve(condition.target), "undefended")
        if isinstance(condition, UnderDefendedCondition):
            return self._relation_result(
                self._resolve(condition.target), "under_defended"
            )
        if isinstance(condition, AttackBalanceCondition):
            ref = self._resolve(condition.target)
            facts = self.relations.get(ref.original_piece_id)
            value = facts.attack_balance >= condition.at_least
            return ConditionResult(
                value,
                f"{ref.label} has attack balance {facts.attack_balance}, "
                f"requiring at least {condition.at_least}",
                _relation_details(ref, facts),
            )
        if isinstance(condition, AttackedByCondition):
            ref = self._resolve(condition.target)
            facts = self.relations.get(ref.original_piece_id)
            if condition.attacker is not None:
                attackers = tuple(
                    relation
                    for relation in facts.attackers
                    if relation.attacker == condition.attacker.original_piece_id
                )
                label = condition.attacker.label
            else:
                expected = PIECE_TYPES[condition.attacker_type]  # type: ignore[index]
                attackers = tuple(
                    relation
                    for relation in facts.attackers
                    if self.tracker.get(relation.attacker).piece_type == expected
                )
                label = f"a {condition.attacker_type}"
            value = bool(attackers)
            details = dict(_relation_details(ref, facts))
            details["matchingAttackers"] = [str(item.attacker) for item in attackers]
            return ConditionResult(
                value,
                f"{ref.label} is{' ' if value else ' not '}attacked by {label}",
                details,
            )
        if isinstance(condition, CapturableCondition):
            if self.subject is None:
                raise ValueError("capturable requires an owning piece subject.")
            subject_facts = self.relations.get(self.subject.original_piece_id)
            matches = tuple(
                relation
                for relation in subject_facts.attacks
                if relation.target == condition.target.original_piece_id
            )
            value = len(matches) == 1
            return ConditionResult(
                value,
                f"{self.subject.label} has {len(matches)} legal capture"
                f"{'s' if len(matches) != 1 else ''} of {condition.target.label}",
                {
                    "subject": str(self.subject),
                    "target": str(condition.target),
                    "candidateMoves": [item.capture.uci() for item in matches],
                },
            )
        if isinstance(condition, InCheckCondition):
            color = chess.WHITE if condition.color == "white" else chess.BLACK
            analysis = self.board.copy(stack=False)
            analysis.turn = color
            value = analysis.is_check()
            return ConditionResult(
                value, f"{condition.color} is{' ' if value else ' not '}in check"
            )
        if isinstance(condition, LastMoveCondition):
            ref = self._resolve(condition.piece)
            value = (
                self.last_move is not None
                and self.last_move.piece == ref.original_piece_id
                and self.last_move.to_square == condition.to_square
            )
            return ConditionResult(
                value,
                f"last move was{' ' if value else ' not '}{ref.label} "
                f"to {condition.to_square}",
            )
        if isinstance(condition, AllCondition):
            results = tuple(self.evaluate(child) for child in condition.conditions)
            return ConditionResult(
                all(item.value for item in results),
                "; ".join(item.explanation for item in results),
                {"children": [dict(item.details) for item in results]},
            )
        if isinstance(condition, AnyCondition):
            results = tuple(self.evaluate(child) for child in condition.conditions)
            return ConditionResult(
                any(item.value for item in results),
                " or ".join(item.explanation for item in results),
                {"children": [dict(item.details) for item in results]},
            )
        result = self.evaluate(condition.condition)
        return ConditionResult(
            not result.value, f"not ({result.explanation})", result.details
        )

    def _resolve(self, value: PieceSubject) -> StartingPieceRef:
        if value == "self":
            if self.subject is None:
                raise ValueError("'self' requires an owning piece subject.")
            return self.subject
        return value

    def _relation_result(
        self, ref: StartingPieceRef, attribute: str
    ) -> ConditionResult:
        facts = self.relations.get(ref.original_piece_id)
        value = bool(getattr(facts, attribute))
        label = attribute.replace("_", "-")
        return ConditionResult(
            value,
            f"{ref.label} is{' ' if value else ' not '}{label}",
            _relation_details(ref, facts),
        )


def _relation_details(ref: StartingPieceRef, facts) -> dict[str, object]:
    return {
        "target": str(ref),
        "square": (
            chess.square_name(facts.square) if facts.square is not None else None
        ),
        "attackers": [str(item.attacker) for item in facts.attackers],
        "defenders": [str(item) for item in facts.distinct_defenders],
        "attackerCount": facts.attacker_count,
        "defenderCount": facts.defender_count,
        "balance": facts.attack_balance,
    }


def _serialize_subject(
    value: PieceSubject,
    aliases: Mapping[StartingPieceRef, str] | None,
) -> str:
    if isinstance(value, str):
        return value
    return aliases.get(value, str(value)) if aliases is not None else str(value)


def _reference_set(value: PieceSubject) -> set[StartingPieceRef]:
    return set() if value == "self" else {value}


def _subject(
    value: object,
    aliases: Mapping[str, StartingPieceRef] | None,
    context: str,
) -> PieceSubject:
    if value == "self":
        return "self"
    return _reference(value, aliases, context)


def _reference(
    value: object,
    aliases: Mapping[str, StartingPieceRef] | None,
    context: str,
) -> StartingPieceRef:
    if not isinstance(value, str):
        raise TypeError(f"{context} piece reference must be a string.")
    if aliases is not None and value in aliases:
        return aliases[value]
    return StartingPieceRef.parse(value)


def _mapping(value: object, context: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise TypeError(f"{context} must be a table/object.")
    return value


def _exact_mapping(value: object, fields: set[str], context: str) -> dict[str, Any]:
    mapping = _mapping(value, context)
    if set(mapping) != fields:
        raise ValueError(f"{context} must contain exactly {sorted(fields)}.")
    return mapping


def _square(value: object, context: str) -> str:
    if not isinstance(value, str) or value not in chess.SQUARE_NAMES:
        raise ValueError(f"{context} has invalid square {value!r}.")
    return value


def _color(value: object, context: str) -> ColorName:
    if value not in {"white", "black"}:
        raise ValueError(f"{context} has invalid color {value!r}.")
    return value  # type: ignore[return-value]


def _piece_type(value: object, context: str) -> PieceTypeName:
    if not isinstance(value, str) or value not in PIECE_TYPES:
        raise ValueError(f"{context} has invalid piece type {value!r}.")
    return value  # type: ignore[return-value]
