from __future__ import annotations

import asyncio

import chess
import pytest

from chess_tui.opening import (
    FixtureBotMoveSource,
    MoveSuggestion,
    OpeningClassifier,
    OpponentMovePlanner,
    OpponentPlannerError,
    SuggestionKind,
)
from chess_tui.widgets import MoveSuggestionPanel


def _board_after(*moves: str) -> chess.Board:
    board = chess.Board()
    for san in moves:
        board.push_san(san)
    return board


def test_bundled_classifier_supplies_deterministic_book_responses() -> None:
    classifier = OpeningClassifier.bundled()
    after_d4 = classifier.book_continuations(_board_after("d4"))
    primary = classifier.primary_match_for(_board_after("d4"))

    assert {"d5", "Nf6", "e5", "e6"} <= {move.san for move in after_d4}
    assert all(move.opening_names for move in after_d4)
    assert primary is not None
    assert primary.name == "Queen's Pawn Game"


def test_planner_uses_opening_index_then_falls_back_to_bot() -> None:
    planner = OpponentMovePlanner(
        OpeningClassifier.bundled(),
        FixtureBotMoveSource(),
    )

    book = asyncio.run(planner.suggestions_for(_board_after("d4")))
    assert len(book) == 4
    assert all(suggestion.kind is SuggestionKind.BOOK for suggestion in book)
    assert all(suggestion.kind is SuggestionKind.BOOK for suggestion in book)

    unknown = _board_after("a3", "a6", "h3", "h6")
    bot = asyncio.run(planner.suggestions_for(unknown))
    assert len(bot) == 4
    assert all(suggestion.kind is SuggestionKind.BOT for suggestion in bot)
    assert all(
        chess.Move.from_uci(suggestion.uci) in unknown.legal_moves for suggestion in bot
    )


def test_fixture_bot_is_deterministic_by_position_profile_and_seed() -> None:
    board = _board_after("e4")

    first = asyncio.run(FixtureBotMoveSource().moves_for(board))
    repeated = asyncio.run(FixtureBotMoveSource().moves_for(board))
    changed_seed = asyncio.run(FixtureBotMoveSource(session_seed=1).moves_for(board))
    changed_profile = asyncio.run(
        FixtureBotMoveSource(profile_id="alternate").moves_for(board)
    )

    assert first == repeated
    assert [move.uci for move in first] != [move.uci for move in changed_seed]
    assert [move.uci for move in first] != [move.uci for move in changed_profile]
    assert all(move.profile_id == "prototype" for move in first)


def test_move_suggestion_panel_has_one_authoritative_highlight() -> None:
    planner = OpponentMovePlanner(
        OpeningClassifier.bundled(),
        FixtureBotMoveSource(),
    )
    suggestions = asyncio.run(planner.suggestions_for(_board_after("d4")))
    panel = MoveSuggestionPanel()

    panel.set_suggestions(suggestions, context="After 1. d4:")
    assert panel.highlighted_suggestion == suggestions[0]

    panel.move_highlight(1)
    assert panel.highlighted_suggestion == suggestions[1]

    panel.highlight(3)
    assert panel.highlighted_suggestion == suggestions[3]


def test_move_suggestion_panel_shows_factual_source_without_statistics() -> None:
    planner = OpponentMovePlanner(
        OpeningClassifier.bundled(),
        FixtureBotMoveSource(),
    )
    suggestions = asyncio.run(planner.suggestions_for(_board_after("d4")))
    panel = MoveSuggestionPanel()

    panel.set_suggestions(
        suggestions,
        context="After 1. d4:",
        explored_sans=frozenset({suggestions[0].san}),
    )

    rendered = panel.render().plain
    assert "BOOK" in rendered
    assert "games" not in rendered
    assert rendered.count("explored") == 1

    bot = asyncio.run(planner.suggestions_for(_board_after("a3", "a6", "h3", "h6")))
    panel.set_suggestions(bot, context="Unknown position:")
    assert "BOT · DETERMINISTIC PROTOTYPE" in panel.render().plain


class StubBotSource:
    def __init__(self, suggestions: tuple[MoveSuggestion, ...]) -> None:
        self.suggestions = suggestions

    async def moves_for(self, board: chess.Board) -> tuple[MoveSuggestion, ...]:
        return self.suggestions

    async def close(self) -> None:
        return None


def _bot_suggestion(
    *,
    uci: str = "b2b4",
    san: str = "b4",
    profile_id: str | None = "prototype",
) -> MoveSuggestion:
    return MoveSuggestion(
        uci=uci,
        san=san,
        kind=SuggestionKind.BOT,
        label="BOT",
        profile_id=profile_id,
    )


@pytest.mark.parametrize(
    ("suggestions", "message"),
    [
        ((_bot_suggestion(uci="bad"),), "invalid UCI"),
        ((_bot_suggestion(uci="e7e5", san="e5"),), "not legal"),
        ((_bot_suggestion(san="wrong"),), "canonical SAN"),
        ((_bot_suggestion(), _bot_suggestion()), "duplicates UCI"),
        ((_bot_suggestion(profile_id=""),), "empty BOT profile_id"),
    ],
)
def test_planner_rejects_malformed_bot_suggestions(
    suggestions: tuple[MoveSuggestion, ...],
    message: str,
) -> None:
    planner = OpponentMovePlanner(
        OpeningClassifier.bundled(), StubBotSource(suggestions)
    )

    with pytest.raises(OpponentPlannerError, match=message):
        asyncio.run(planner.suggestions_for(_board_after("a3", "a6", "h3", "h6")))
