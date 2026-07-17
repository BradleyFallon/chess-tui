"""History-sensitive tracking for pieces identified by their starting squares."""

from __future__ import annotations

from dataclasses import dataclass

import chess

from .models import OriginalPieceId


@dataclass(slots=True)
class OriginalPieceRuntime:
    id: OriginalPieceId
    piece_type: chess.PieceType
    current_square: chess.Square | None
    has_moved: bool = False
    captured: bool = False
    first_moved_ply: int | None = None
    captured_ply: int | None = None


class OriginalPieceTracker:
    def __init__(self, start_board: chess.Board) -> None:
        self._pieces: dict[OriginalPieceId, OriginalPieceRuntime] = {}
        self._by_square: dict[chess.Square, OriginalPieceId] = {}
        for square, piece in start_board.piece_map().items():
            color = "white" if piece.color == chess.WHITE else "black"
            piece_id = OriginalPieceId(color, chess.square_name(square))
            self._pieces[piece_id] = OriginalPieceRuntime(
                piece_id, piece.piece_type, square
            )
            self._by_square[square] = piece_id

    @property
    def pieces(self) -> tuple[OriginalPieceRuntime, ...]:
        return tuple(self._pieces.values())

    def has(self, piece_id: OriginalPieceId) -> bool:
        return piece_id in self._pieces

    def get(self, piece_id: OriginalPieceId) -> OriginalPieceRuntime:
        try:
            return self._pieces[piece_id]
        except KeyError as exc:
            raise ValueError(
                f"Original piece {piece_id} is absent from start_fen."
            ) from exc

    def apply_move(
        self, board_before: chess.Board, move: chess.Move, *, ply: int
    ) -> None:
        moving_id = self._by_square.get(move.from_square)
        if moving_id is None:
            raise ValueError(
                f"No tracked original piece is on {chess.square_name(move.from_square)}."
            )

        capture_square = move.to_square
        if board_before.is_en_passant(move):
            capture_square += -8 if board_before.turn == chess.WHITE else 8
        captured_id = self._by_square.pop(capture_square, None)
        if captured_id is not None:
            captured = self._pieces[captured_id]
            captured.current_square = None
            captured.captured = True
            captured.captured_ply = ply

        self._by_square.pop(move.from_square)
        moving = self._pieces[moving_id]
        moving.current_square = move.to_square
        moving.has_moved = True
        if moving.first_moved_ply is None:
            moving.first_moved_ply = ply
        if move.promotion is not None:
            moving.piece_type = move.promotion
        self._by_square[move.to_square] = moving_id

        if board_before.is_castling(move):
            rank = chess.square_rank(move.from_square)
            kingside = chess.square_file(move.to_square) > chess.square_file(
                move.from_square
            )
            rook_from = chess.square(7 if kingside else 0, rank)
            rook_to = chess.square(5 if kingside else 3, rank)
            rook_id = self._by_square.pop(rook_from, None)
            if rook_id is not None:
                rook = self._pieces[rook_id]
                rook.current_square = rook_to
                rook.has_moved = True
                if rook.first_moved_ply is None:
                    rook.first_moved_ply = ply
                self._by_square[rook_to] = rook_id
