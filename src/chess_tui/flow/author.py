"""Application service for persistent White-flow edits."""

from __future__ import annotations

from pathlib import Path
import re
from dataclasses import dataclass

import chess

from ..board import ParsedFen, parse_fen
from ..game import BoardInteraction, ChessMove
from .models import ExceptionRule, OpponentReply, Recommendation, WhiteFlow
from .policy import WhitePolicy
from .errors import FlowValidationError
from .position import normalized_position_key, parse_legal_san, replay_san
from .store import FlowStore


class WhiteFlowAuthor:
    def __init__(self, path: Path, store: FlowStore | None = None) -> None:
        self.path = path
        self.store = store or FlowStore()
        self.flow = self.store.load(path)
        self.policy = WhitePolicy(self.flow)

    def reload(self) -> WhiteFlow:
        flow = self.store.load(self.path)
        policy = WhitePolicy(flow)
        self.flow = flow
        self.policy = policy
        return flow

    def recommend(self, board: chess.Board, white_step: int) -> Recommendation | None:
        return self.policy.recommend(board, white_step)

    def replace_default(
        self,
        board: chess.Board,
        step: int,
        move_san: str,
        note: str | None,
    ) -> WhiteFlow:
        parse_legal_san(board, move_san, context=f"Default step {step}")
        updated = self.store.replace_default(self.path, step, move_san, note)
        self.flow = updated
        self.policy = WhitePolicy(updated)
        return updated

    def add_exception(
        self,
        board: chess.Board,
        step: int,
        after_san: tuple[str, ...],
        move_san: str,
        note: str | None,
    ) -> WhiteFlow:
        parse_legal_san(board, move_san, context="Position exception")
        replayed = replay_san(self.flow.start_fen, after_san)
        if normalized_position_key(replayed) != normalized_position_key(board):
            raise FlowValidationError(
                "Exception SAN history does not resolve to the authored position."
            )
        exception = ExceptionRule(
            id=_exception_id(after_san),
            step=step,
            after_san=after_san,
            move_san=move_san,
            note=note,
        )
        updated = self.store.add_exception(self.path, exception)
        self.flow = updated
        self.policy = WhitePolicy(updated)
        return updated

    def remove_exception(self, exception_id: str) -> WhiteFlow:
        updated = self.store.remove_exception(self.path, exception_id)
        self.flow = updated
        self.policy = WhitePolicy(updated)
        return updated

    def record_opponent_reply(
        self,
        board: chess.Board,
        after_san: tuple[str, ...],
        move_san: str,
    ) -> WhiteFlow:
        replayed = replay_san(self.flow.start_fen, after_san)
        if normalized_position_key(replayed) != normalized_position_key(board):
            raise FlowValidationError(
                "Opponent reply SAN history does not resolve to the authored position."
            )
        if board.turn is not chess.BLACK:
            raise FlowValidationError("Opponent replies must be recorded for Black.")
        parse_legal_san(board, move_san, context="Opponent reply")
        reply = OpponentReply(
            id=_branch_id(after_san + (move_san,)),
            after_san=after_san,
            move_san=move_san,
        )
        updated = self.store.add_opponent_reply(self.path, reply)
        self.flow = updated
        self.policy = WhitePolicy(updated)
        return updated


@dataclass(frozen=True, slots=True)
class ConfirmedAuthorMove:
    move: ChessMove
    san: str
    color: chess.Color


class AuthorBoardController:
    """Drive board interaction with python-chess as the rules authority."""

    def __init__(self, board: chess.Board) -> None:
        self.board = board.copy(stack=False)
        self.interaction = BoardInteraction()
        self._update_checked_king()

    @property
    def position(self) -> ParsedFen:
        return parse_fen(self.board.fen(en_passant="fen"))

    @property
    def pending_san(self) -> str | None:
        pending = self.interaction.pending_move
        if pending is None:
            return None
        return self.board.san(chess.Move.from_uci(pending.uci))

    def reset(self, board: chess.Board) -> None:
        self.board = board.copy(stack=False)
        self.interaction = BoardInteraction()
        self._update_checked_king()

    def set_hover(self, square: int | None) -> None:
        self.interaction.hover_square = square

    def handle_square(self, square: int) -> None:
        if self.interaction.selected_square is not None and self._choose_destination(
            square
        ):
            return
        self._select_square(square)

    def confirm_move(self) -> ConfirmedAuthorMove | None:
        pending = self.interaction.pending_move
        if pending is None:
            return None
        return self._commit_move(chess.Move.from_uci(pending.uci))

    def confirm_san(self, san: str) -> ConfirmedAuthorMove:
        """Parse and commit a typed legal SAN move."""

        return self._commit_move(self.board.parse_san(san))

    def confirm_uci(self, uci: str) -> ConfirmedAuthorMove:
        """Parse and commit a legal UCI move supplied by a suggestion source."""

        move = chess.Move.from_uci(uci)
        if move not in self.board.legal_moves:
            raise ValueError(f"{uci!r} is not legal in {self.board.fen()}.")
        return self._commit_move(move)

    def _commit_move(self, move: chess.Move) -> ConfirmedAuthorMove:
        san = self.board.san(move)
        color = self.board.turn
        self.board.push(move)
        hover = self.interaction.hover_square
        committed = ChessMove.from_uci(move.uci())
        self.interaction = BoardInteraction(hover_square=hover, last_move=committed)
        self._update_checked_king()
        return ConfirmedAuthorMove(committed, san, color)

    def clear_selection(self) -> None:
        self.interaction.selected_square = None
        self.interaction.legal_moves = ()
        self.interaction.quiet_targets = frozenset()
        self.interaction.capture_targets = frozenset()
        self.interaction.pending_move = None

    def _select_square(self, square: int) -> bool:
        piece = self.board.piece_at(square)
        if piece is None:
            self.clear_selection()
            return False
        if piece.color != self.board.turn:
            return False
        moves = tuple(
            move for move in self.board.legal_moves if move.from_square == square
        )
        if not moves:
            self.clear_selection()
            return False
        converted = tuple(ChessMove.from_uci(move.uci()) for move in moves)
        self.interaction.selected_square = square
        self.interaction.legal_moves = converted
        self.interaction.capture_targets = frozenset(
            move.to_square for move in moves if self.board.is_capture(move)
        )
        self.interaction.quiet_targets = frozenset(
            move.to_square for move in moves if not self.board.is_capture(move)
        )
        self.interaction.pending_move = None
        return True

    def _choose_destination(self, square: int) -> bool:
        candidates = tuple(
            move for move in self.interaction.legal_moves if move.to_square == square
        )
        if not candidates:
            return False
        self.interaction.pending_move = next(
            (move for move in candidates if move.promotion == "q"), candidates[0]
        )
        return True

    def _update_checked_king(self) -> None:
        self.interaction.checked_king = (
            self.board.king(self.board.turn) if self.board.is_check() else None
        )


def _exception_id(history: tuple[str, ...]) -> str:
    return _branch_id(history)


def _branch_id(history: tuple[str, ...]) -> str:
    parts = [re.sub(r"[^a-z0-9]+", "-", san.lower()).strip("-") for san in history]
    suffix = "-".join(part for part in parts if part)
    return f"after-{suffix}" if suffix else "starting-position"
