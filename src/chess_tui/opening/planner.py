"""Book-first opponent move planning."""

from __future__ import annotations

import chess

from .errors import OpponentPlannerError
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
            suggestions = tuple(_book_suggestion(move) for move in book_moves)
        else:
            suggestions = await self.bot_source.moves_for(board)
        _validate_suggestions(board, suggestions)
        return suggestions[:4]

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


def _validate_suggestions(
    board: chess.Board,
    suggestions: tuple[MoveSuggestion, ...],
) -> None:
    seen_uci: set[str] = set()
    for index, suggestion in enumerate(suggestions, start=1):
        context = f"Suggestion {index} ({suggestion.uci!r})"
        try:
            move = chess.Move.from_uci(suggestion.uci)
        except ValueError as error:
            raise OpponentPlannerError(
                f"{context} has invalid UCI notation."
            ) from error
        if move not in board.legal_moves:
            raise OpponentPlannerError(
                f"{context} is not legal in the requested position."
            )
        canonical_san = board.san(move)
        if suggestion.san != canonical_san:
            raise OpponentPlannerError(
                f"{context} has SAN {suggestion.san!r}; "
                f"canonical SAN is {canonical_san!r}."
            )
        if suggestion.uci in seen_uci:
            raise OpponentPlannerError(
                f"{context} duplicates UCI move {suggestion.uci!r}."
            )
        seen_uci.add(suggestion.uci)

        if suggestion.kind is SuggestionKind.BOOK:
            if suggestion.games is None or suggestion.games < 0:
                raise OpponentPlannerError(f"{context} has an invalid BOOK game count.")
            if suggestion.frequency is None or not 0 <= suggestion.frequency <= 1:
                raise OpponentPlannerError(f"{context} has an invalid BOOK frequency.")
        elif suggestion.kind is SuggestionKind.BOT:
            if suggestion.profile_id is None or not suggestion.profile_id.strip():
                raise OpponentPlannerError(f"{context} has an empty BOT profile_id.")
