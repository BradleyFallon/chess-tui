"""Deterministic opening statistics for the London author prototype."""

from __future__ import annotations

import chess

from .errors import OpeningDataError
from .models import OpeningMove

FixtureRow = tuple[str, str, int, float]

_FIXTURES: tuple[tuple[tuple[str, ...], tuple[FixtureRow, ...]], ...] = (
    (
        ("d4",),
        (
            ("d7d5", "d5", 800_000, 0.46),
            ("g8f6", "Nf6", 600_000, 0.34),
            ("e7e5", "e5", 190_000, 0.11),
            ("e7e6", "e6", 100_000, 0.06),
        ),
    ),
    (
        ("d4", "d5", "Bf4"),
        (
            ("g8f6", "Nf6", 520_000, 0.55),
            ("e7e6", "e6", 260_000, 0.28),
            ("c7c5", "c5", 120_000, 0.13),
        ),
    ),
)


class FixtureOpeningMoveSource:
    """Return stable local data keyed by normalized chess position."""

    def __init__(self) -> None:
        self._moves_by_position = _build_fixture_index()

    async def moves_for(self, board: chess.Board) -> tuple[OpeningMove, ...]:
        return self._moves_by_position.get(_position_key(board), ())


def _build_fixture_index() -> dict[str, tuple[OpeningMove, ...]]:
    index: dict[str, tuple[OpeningMove, ...]] = {}
    for history, rows in _FIXTURES:
        board = chess.Board()
        for san in history:
            board.push_san(san)
        moves = tuple(_validated_move(board, row) for row in rows)
        index[_position_key(board)] = moves
    return index


def _validated_move(board: chess.Board, row: FixtureRow) -> OpeningMove:
    uci, expected_san, games, frequency = row
    try:
        move = chess.Move.from_uci(uci)
    except ValueError as error:
        raise OpeningDataError(f"Invalid fixture UCI {uci!r}.") from error
    if move not in board.legal_moves:
        raise OpeningDataError(f"Fixture move {uci!r} is not legal in {board.fen()}.")
    actual_san = board.san(move)
    if actual_san != expected_san:
        raise OpeningDataError(
            f"Fixture SAN mismatch for {uci!r}: {expected_san!r} != {actual_san!r}."
        )
    if games < 0 or not 0 <= frequency <= 1:
        raise OpeningDataError(f"Invalid fixture statistics for {uci!r}.")
    return OpeningMove(uci, actual_san, games, frequency)


def _position_key(board: chess.Board) -> str:
    fields = board.fen(en_passant="fen").split()
    return " ".join(fields[:4])
