"""Deterministic engine service for tests and dependency injection."""

from __future__ import annotations

import hashlib

import chess

from .errors import EngineProcessError, EngineResultError
from .models import EngineProfile


class FixtureEngineService:
    """Choose one reproducible legal move without starting a process."""

    def __init__(self, *, session_seed: int | str = 0) -> None:
        self.session_seed = str(session_seed)
        self.closed = False

    async def choose_move(
        self,
        board: chess.Board,
        profile: EngineProfile,
    ) -> chess.Move:
        if self.closed:
            raise EngineProcessError("The fixture engine service is closed.")
        legal_moves = tuple(board.legal_moves)
        if not legal_moves:
            raise EngineResultError("The position has no legal engine move.")
        material = f"{board.fen(en_passant='fen')}|{profile.id}|{self.session_seed}"
        return min(
            legal_moves,
            key=lambda move: hashlib.sha256(
                f"{material}|{move.uci()}".encode("utf-8")
            ).digest(),
        )

    async def close(self) -> None:
        self.closed = True
