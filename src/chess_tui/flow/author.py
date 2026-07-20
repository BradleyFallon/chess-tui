"""Rulebook v4 authoring service and shared board interaction."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
import re

import chess

from ..board import ParsedFen, parse_fen
from ..game import BoardInteraction, ChessMove
from .errors import FlowValidationError
from .models import (
    DevelopmentInstruction,
    InterruptRule,
    OpeningTag,
    OpponentReply,
    PieceScript,
    Rulebook,
)
from .position import normalized_position_key, parse_legal_san, replay_san
from .store import FlowStore


class RulebookAuthor:
    def __init__(self, path: Path, store: FlowStore | None = None) -> None:
        self.path = path
        self.store = store or FlowStore()
        self.rulebook = self.store.load(path)

    def reload(self) -> Rulebook:
        self.rulebook = self.store.load(self.path)
        return self.rulebook

    def save_candidate(self, candidate: Rulebook) -> Rulebook:
        self.store.save(self.path, candidate)
        self.rulebook = candidate
        return candidate

    def candidate_with_piece(self, replacement: PieceScript) -> Rulebook:
        if replacement.id not in self.rulebook.piece_by_alias:
            return replace(self.rulebook, pieces=(*self.rulebook.pieces, replacement))
        return replace(
            self.rulebook,
            pieces=tuple(
                replacement if item.id == replacement.id else item
                for item in self.rulebook.pieces
            ),
        )

    def candidate_with_development(
        self, alias: str, development: DevelopmentInstruction | None
    ) -> Rulebook:
        piece = self._piece(alias)
        candidate = self.candidate_with_piece(replace(piece, development=development))
        ordered = list(candidate.development_order)
        if development is None and alias in ordered:
            ordered.remove(alias)
        elif development is not None and alias not in ordered:
            ordered.append(alias)
        return replace(candidate, development_order=tuple(ordered))

    def candidate_with_interrupt(
        self, alias: str, rule: InterruptRule
    ) -> Rulebook:
        piece = self._piece(alias)
        if rule.piece != piece.ref:
            raise FlowValidationError("Interrupt owner does not match its piece.")
        if any(item.id == rule.id for item in piece.rules):
            rules = tuple(rule if item.id == rule.id else item for item in piece.rules)
        else:
            rules = (*piece.rules, rule)
        candidate = self.candidate_with_piece(replace(piece, rules=rules))
        reference = f"{alias}.{rule.id}"
        if reference not in candidate.interrupt_order:
            candidate = replace(
                candidate, interrupt_order=(*candidate.interrupt_order, reference)
            )
        return candidate

    def candidate_without_interrupt(self, alias: str, rule_id: str) -> Rulebook:
        piece = self._piece(alias)
        if all(item.id != rule_id for item in piece.rules):
            raise FlowValidationError(f"Unknown interrupt {alias}.{rule_id}.")
        candidate = self.candidate_with_piece(
            replace(piece, rules=tuple(item for item in piece.rules if item.id != rule_id))
        )
        reference = f"{alias}.{rule_id}"
        return replace(
            candidate,
            interrupt_order=tuple(
                item for item in candidate.interrupt_order if item != reference
            ),
        )

    def candidate_with_development_order(
        self, order: tuple[str, ...]
    ) -> Rulebook:
        candidate = replace(self.rulebook, development_order=order)
        self.store.validate(candidate)
        return candidate

    def candidate_with_interrupt_order(self, order: tuple[str, ...]) -> Rulebook:
        candidate = replace(self.rulebook, interrupt_order=order)
        self.store.validate(candidate)
        return candidate

    def candidate_with_added_opening_tag(self, tag: OpeningTag) -> Rulebook:
        if tag in self.rulebook.opening_tags:
            raise FlowValidationError(
                f"Rulebook is already labeled {tag.name!r} ({tag.eco})."
            )
        return replace(self.rulebook, opening_tags=(*self.rulebook.opening_tags, tag))

    def candidate_without_opening_tag(self, tag: OpeningTag) -> Rulebook:
        if tag not in self.rulebook.opening_tags:
            raise FlowValidationError(
                f"Rulebook is not labeled {tag.name!r} ({tag.eco})."
            )
        return replace(
            self.rulebook,
            opening_tags=tuple(
                item for item in self.rulebook.opening_tags if item != tag
            ),
        )

    def record_opponent_reply(
        self,
        board: chess.Board,
        after_san: tuple[str, ...],
        move_san: str,
    ) -> Rulebook:
        replayed = replay_san(self.rulebook.start_fen, after_san)
        if normalized_position_key(replayed) != normalized_position_key(board):
            raise FlowValidationError(
                "Opponent reply history does not resolve to the authored position."
            )
        controlled = chess.WHITE if self.rulebook.side == "white" else chess.BLACK
        if board.turn == controlled:
            raise FlowValidationError("Opponent replies target the uncontrolled side.")
        parse_legal_san(board, move_san, context="Opponent reply")
        reply = OpponentReply(
            id=_branch_id(after_san + (move_san,)),
            after_san=after_san,
            move_san=move_san,
        )
        self.rulebook = self.store.add_opponent_reply(self.path, reply)
        return self.rulebook

    def _piece(self, alias: str) -> PieceScript:
        try:
            return self.rulebook.piece_by_alias[alias]
        except KeyError as exc:
            raise FlowValidationError(f"Unknown piece alias {alias!r}.") from exc


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
        return self._commit_move(self.board.parse_san(san))

    def confirm_uci(self, uci: str) -> ConfirmedAuthorMove:
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


def _branch_id(history: tuple[str, ...]) -> str:
    parts = [re.sub(r"[^a-z0-9]+", "-", san.lower()).strip("-") for san in history]
    suffix = "-".join(part for part in parts if part)
    return f"after-{suffix}" if suffix else "starting-position"
