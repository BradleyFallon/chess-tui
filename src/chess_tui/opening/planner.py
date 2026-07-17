"""Book-first opponent move planning."""

from __future__ import annotations

import chess

from .errors import OpponentPlannerError
from .classification import BookContinuation, OpeningClassifier
from .models import MoveSuggestion, SuggestionKind
from .source import BotMoveSource


class OpponentMovePlanner:
    def __init__(
        self,
        opening_classifier: OpeningClassifier,
        bot_source: BotMoveSource,
    ) -> None:
        self.opening_classifier = opening_classifier
        self.bot_source = bot_source

    async def suggestions_for(
        self,
        board: chess.Board,
    ) -> tuple[MoveSuggestion, ...]:
        book_moves = self.opening_classifier.book_continuations(board)
        if book_moves:
            suggestions = tuple(_book_suggestion(move) for move in book_moves)
        else:
            suggestions = await self.bot_source.moves_for(board)
        _validate_suggestions(board, suggestions)
        return suggestions[:4]

    async def close(self) -> None:
        await self.bot_source.close()


def _book_suggestion(move: BookContinuation) -> MoveSuggestion:
    return MoveSuggestion(
        uci=move.uci,
        san=move.san,
        kind=SuggestionKind.BOOK,
        label="BOOK",
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

        if suggestion.kind is SuggestionKind.BOT:
            if suggestion.profile_id is None or not suggestion.profile_id.strip():
                raise OpponentPlannerError(f"{context} has an empty BOT profile_id.")
