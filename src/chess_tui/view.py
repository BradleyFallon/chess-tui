"""Renderer-neutral board presentation state."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from .board import ParsedFen, parse_fen
from .game import GameController

if TYPE_CHECKING:
    from .sessions.models import QuizSessionState


class BoardInputMode(str, Enum):
    READ_ONLY = "read-only"
    MOVE_ENTRY = "move-entry"


@dataclass(frozen=True, slots=True)
class MoveView:
    from_square: int
    to_square: int


@dataclass(frozen=True, slots=True)
class BoardViewState:
    position: ParsedFen
    selected_square: int | None = None
    quiet_targets: frozenset[int] = frozenset()
    capture_targets: frozenset[int] = frozenset()
    pending_move: MoveView | None = None
    last_move: MoveView | None = None
    hover_square: int | None = None
    checked_king: int | None = None


def board_view_from_game(controller: GameController) -> BoardViewState:
    interaction = controller.interaction
    pending = interaction.pending_move
    last = interaction.last_move
    return BoardViewState(
        position=controller.position,
        selected_square=interaction.selected_square,
        quiet_targets=interaction.quiet_targets,
        capture_targets=interaction.capture_targets,
        pending_move=(
            MoveView(pending.from_square, pending.to_square)
            if pending is not None
            else None
        ),
        last_move=(
            MoveView(last.from_square, last.to_square) if last is not None else None
        ),
        hover_square=interaction.hover_square,
        checked_king=interaction.checked_king,
    )


def board_view_from_quiz_state(state: QuizSessionState) -> BoardViewState:
    return BoardViewState(position=parse_fen(state.fen))
