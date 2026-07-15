"""Opponent move source backed by a reusable chess-engine service."""

from __future__ import annotations

import chess

from ..engine import (
    ENGINE_PROTOTYPE_PROFILE,
    ChessEngineService,
    EngineProfile,
)
from .models import MoveSuggestion, SuggestionKind


class StockfishBotMoveSource:
    """Return exactly one canonical engine-backed BOT suggestion."""

    def __init__(
        self,
        engine: ChessEngineService,
        *,
        profile: EngineProfile = ENGINE_PROTOTYPE_PROFILE,
    ) -> None:
        self.engine = engine
        self.profile = profile

    async def moves_for(self, board: chess.Board) -> tuple[MoveSuggestion, ...]:
        move = await self.engine.choose_move(board, self.profile)
        return (
            MoveSuggestion(
                uci=move.uci(),
                san=board.san(move),
                kind=SuggestionKind.BOT,
                label=self.profile.label,
                profile_id=self.profile.id,
            ),
        )

    async def close(self) -> None:
        await self.engine.close()
