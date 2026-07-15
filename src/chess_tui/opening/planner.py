"""Book-first opponent move planning."""

from __future__ import annotations

import chess

from .models import MoveSuggestion, OpeningMove, SuggestionKind
from .source import BotMoveSource, OpeningMoveSource


class OpponentMovePlanner:
    def __init__(
        self,
        book_source: OpeningMoveSource,
        bot_source: BotMoveSource,
    ) -> None:
        self.book_source = book_source
        self.bot_source = bot_source

    async def suggestions_for(
        self,
        board: chess.Board,
    ) -> tuple[MoveSuggestion, ...]:
        book_moves = await self.book_source.moves_for(board)
        if book_moves:
            return tuple(_book_suggestion(move) for move in book_moves[:4])
        return (await self.bot_source.moves_for(board))[:4]

    async def close(self) -> None:
        await self.bot_source.close()


def _book_suggestion(move: OpeningMove) -> MoveSuggestion:
    return MoveSuggestion(
        uci=move.uci,
        san=move.san,
        kind=SuggestionKind.BOOK,
        label="BOOK",
        games=move.games,
        frequency=move.frequency,
    )
