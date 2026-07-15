"""Protocols for book and bot move providers."""

from __future__ import annotations

from typing import Protocol

import chess

from .models import MoveSuggestion, OpeningMove


class OpeningMoveSource(Protocol):
    async def moves_for(self, board: chess.Board) -> tuple[OpeningMove, ...]: ...


class BotMoveSource(Protocol):
    async def moves_for(self, board: chess.Board) -> tuple[MoveSuggestion, ...]: ...

    async def close(self) -> None: ...
