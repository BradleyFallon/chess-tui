"""Narrow protocol for persistent chess engines."""

from __future__ import annotations

from typing import Protocol

import chess

from .models import AnalysedMove, EngineProfile


class ChessEngineService(Protocol):
    async def choose_move(
        self,
        board: chess.Board,
        profile: EngineProfile,
    ) -> chess.Move: ...

    async def analyse(
        self,
        board: chess.Board,
        *,
        count: int = 4,
        profile: EngineProfile | None = None,
    ) -> tuple[AnalysedMove, ...]: ...

    async def close(self) -> None: ...
