from __future__ import annotations

import asyncio

import chess

from chess_tui.opening import (
    FixtureBotMoveSource,
    FixtureOpeningMoveSource,
    OpponentMovePlanner,
    SuggestionKind,
)
from chess_tui.widgets import MoveSuggestionPanel


def _board_after(*moves: str) -> chess.Board:
    board = chess.Board()
    for san in moves:
        board.push_san(san)
    return board


def test_fixture_source_returns_ranked_london_responses() -> None:
    source = FixtureOpeningMoveSource()

    after_d4 = asyncio.run(source.moves_for(_board_after("d4")))
    assert [(move.san, move.uci) for move in after_d4] == [
        ("d5", "d7d5"),
        ("Nf6", "g8f6"),
        ("e5", "e7e5"),
        ("e6", "e7e6"),
    ]
    assert after_d4[0].games == 800_000
    assert after_d4[0].frequency == 0.46

    after_bf4 = asyncio.run(source.moves_for(_board_after("d4", "d5", "Bf4")))
    assert [move.san for move in after_bf4] == ["Nf6", "e6", "c5"]

    after_e3 = asyncio.run(
        source.moves_for(_board_after("d4", "d5", "Bf4", "Nf6", "e3"))
    )
    assert [move.san for move in after_e3] == ["e6", "c5", "g6"]

    after_nf3 = asyncio.run(
        source.moves_for(_board_after("d4", "d5", "Bf4", "Nf6", "e3", "e6", "Nf3"))
    )
    assert [move.san for move in after_nf3] == ["c5", "Be7", "Bd6"]

    unknown = asyncio.run(source.moves_for(_board_after("e4")))
    assert unknown == ()


def test_planner_uses_book_then_falls_back_to_bot() -> None:
    planner = OpponentMovePlanner(
        FixtureOpeningMoveSource(),
        FixtureBotMoveSource(),
    )

    book = asyncio.run(planner.suggestions_for(_board_after("d4")))
    assert [suggestion.san for suggestion in book] == ["d5", "Nf6", "e5", "e6"]
    assert all(suggestion.kind is SuggestionKind.BOOK for suggestion in book)
    assert book[0].games == 800_000
    assert book[0].frequency == 0.46

    bot = asyncio.run(planner.suggestions_for(_board_after("e4")))
    assert len(bot) == 4
    assert all(suggestion.kind is SuggestionKind.BOT for suggestion in bot)
    assert all(
        chess.Move.from_uci(suggestion.uci) in _board_after("e4").legal_moves
        for suggestion in bot
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
        FixtureOpeningMoveSource(),
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


def test_move_suggestion_panel_shows_source_and_explored_state() -> None:
    planner = OpponentMovePlanner(
        FixtureOpeningMoveSource(),
        FixtureBotMoveSource(),
    )
    suggestions = asyncio.run(planner.suggestions_for(_board_after("d4")))
    panel = MoveSuggestionPanel()

    panel.set_suggestions(
        suggestions,
        context="After 1. d4:",
        explored_sans=frozenset({"d5"}),
    )

    rendered = panel.render().plain
    assert "d5    BOOK · 46% · 800,000 games · explored" in rendered
    assert rendered.count("explored") == 1

    bot = asyncio.run(planner.suggestions_for(_board_after("e4")))
    panel.set_suggestions(bot, context="After 1. e4:")
    assert "BOT · DETERMINISTIC PROTOTYPE" in panel.render().plain
