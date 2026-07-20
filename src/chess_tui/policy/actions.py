"""Deterministic action resolution for v4 piece-owned attempts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import chess

from .models import (
    ActionAttempt,
    CaptureAttempt,
    ConditionResult,
    MoveAttempt,
    StartingPieceRef,
)
from .relations import PositionRelations
from .tracker import OriginalPieceTracker


class ActionStatus(str, Enum):
    FAILED = "failed"
    RESOLVED = "resolved"
    AMBIGUOUS = "ambiguous"


@dataclass(frozen=True, slots=True)
class ActionResolution:
    attempt: ActionAttempt
    status: ActionStatus
    candidates: tuple[chess.Move, ...]
    move: chess.Move | None
    move_san: str | None
    reason: str


class ActionResolver:
    def resolve(
        self,
        attempt: ActionAttempt,
        *,
        board: chess.Board,
        tracker: OriginalPieceTracker,
        relations: PositionRelations,
        subject: StartingPieceRef,
        trigger: ConditionResult | None = None,
    ) -> ActionResolution:
        runtime = tracker.get(subject.original_piece_id)
        if runtime.current_square is None:
            return self._result(attempt, (), board, f"{subject.label} is captured.")

        facts = relations.get(subject.original_piece_id)
        if isinstance(attempt, MoveAttempt):
            candidate = chess.Move(
                runtime.current_square, chess.parse_square(attempt.to_square)
            )
            candidates = (candidate,) if candidate in board.legal_moves else ()
            return self._result(
                attempt,
                candidates,
                board,
                (
                    f"{subject.label} can move to {attempt.to_square}."
                    if candidates
                    else f"{candidate.uci()} is not legal."
                ),
            )

        assert isinstance(attempt, CaptureAttempt)
        capture_relations = facts.attacks
        if attempt.triggering_attacker:
            relevant = _triggering_attackers(trigger)
            if relevant:
                capture_relations = tuple(
                    item for item in capture_relations if str(item.target) in relevant
                )
            else:
                current_attackers = {item.attacker for item in facts.attackers}
                capture_relations = tuple(
                    item
                    for item in capture_relations
                    if item.target in current_attackers
                )
        elif attempt.target_piece is not None:
            capture_relations = tuple(
                item
                for item in capture_relations
                if item.target == attempt.target_piece.original_piece_id
            )
        else:
            assert attempt.target_type is not None
            expected = {
                "pawn": chess.PAWN,
                "knight": chess.KNIGHT,
                "bishop": chess.BISHOP,
                "rook": chess.ROOK,
                "queen": chess.QUEEN,
                "king": chess.KING,
            }[attempt.target_type]
            capture_relations = tuple(
                item
                for item in capture_relations
                if tracker.get(item.target).piece_type == expected
            )
        candidates = tuple(dict.fromkeys(item.capture for item in capture_relations))
        return self._result(
            attempt,
            candidates,
            board,
            f"Capture attempt produced {len(candidates)} legal candidate(s).",
        )

    def _result(
        self,
        attempt: ActionAttempt,
        candidates: tuple[chess.Move, ...],
        board: chess.Board,
        reason: str,
    ) -> ActionResolution:
        if not candidates:
            return ActionResolution(
                attempt, ActionStatus.FAILED, (), None, None, reason
            )
        if len(candidates) > 1:
            moves = ", ".join(move.uci() for move in candidates)
            return ActionResolution(
                attempt,
                ActionStatus.AMBIGUOUS,
                candidates,
                None,
                None,
                f"Action is ambiguous: {moves}.",
            )
        move = next(iter(candidates))
        return ActionResolution(
            attempt,
            ActionStatus.RESOLVED,
            candidates,
            move,
            board.san(move),
            reason,
        )


def _triggering_attackers(trigger: ConditionResult | None) -> set[str]:
    if trigger is None:
        return set()
    values = trigger.details.get(
        "matchingAttackers", trigger.details.get("attackers", [])
    )
    if not isinstance(values, list):
        return set()
    return {value for value in values if isinstance(value, str)}
