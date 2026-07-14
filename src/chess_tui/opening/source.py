"""Protocol for opening-move data providers."""

from __future__ import annotations

from typing import Protocol

import chess

from .models import OpeningMove


class OpeningMoveSource(Protocol):
    async def moves_for(self, board: chess.Board) -> tuple[OpeningMove, ...]: ...
