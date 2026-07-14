"""SAN replay and normalized chess-position identity."""

from __future__ import annotations

import chess

from .errors import FlowValidationError


def normalized_position_key(board: chess.Board) -> str:
    """Identify a position while ignoring move clocks."""

    turn = "w" if board.turn is chess.WHITE else "b"
    castling = board.castling_xfen() or "-"
    en_passant = chess.square_name(board.ep_square) if board.ep_square else "-"
    return " ".join((board.board_fen(), turn, castling, en_passant))


def replay_san(
    start_fen: str,
    history: tuple[str, ...],
    *,
    context: str = "move history",
) -> chess.Board:
    try:
        board = chess.Board(start_fen)
    except ValueError as exc:
        raise FlowValidationError(f"Invalid start_fen: {exc}") from exc

    for ply, san in enumerate(history, start=1):
        try:
            move = board.parse_san(san)
        except ValueError as exc:
            raise FlowValidationError(
                f"{context}: {san!r} is illegal at ply {ply}."
            ) from exc
        board.push(move)
    return board


def parse_legal_san(board: chess.Board, san: str, *, context: str) -> chess.Move:
    try:
        return board.parse_san(san)
    except ValueError as exc:
        raise FlowValidationError(
            f"{context}: {san!r} is not legal in {board.fen()}."
        ) from exc
