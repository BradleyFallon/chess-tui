from __future__ import annotations

import asyncio

import chess

from chess_tui.opening import FixtureOpeningMoveSource
from chess_tui.widgets import OpeningMovePanel


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

    unknown = asyncio.run(source.moves_for(_board_after("e4")))
    assert unknown == ()


def test_opening_move_panel_has_one_authoritative_highlight() -> None:
    moves = asyncio.run(FixtureOpeningMoveSource().moves_for(_board_after("d4")))
    panel = OpeningMovePanel()

    panel.set_moves(moves, context="After 1. d4:")
    assert panel.highlighted_move == moves[0]

    panel.move_highlight(1)
    assert panel.highlighted_move == moves[1]

    panel.highlight(3)
    assert panel.highlighted_move == moves[3]
