from __future__ import annotations

import chess
import pytest

from chess_tui.widgets import AdvantageBar


def test_advantage_bar_renders_white_normalized_centipawn_score() -> None:
    bar = AdvantageBar()

    bar.set_evaluation(evaluation_cp=260, mate_in=None)

    assert bar.white_share == pytest.approx(0.63)
    assert "WHITE +2.60" in bar.render().plain
    assert bar.render().plain.startswith("B ")


def test_advantage_bar_renders_black_mate_without_centipawn_conversion() -> None:
    bar = AdvantageBar()

    bar.set_evaluation(evaluation_cp=None, mate_in=-3)

    assert bar.white_share == 0.0
    assert "BLACK M3" in bar.render().plain


def test_advantage_bar_renders_terminal_result() -> None:
    board = chess.Board("7k/8/5KQ1/8/8/8/8/8 w - - 0 1")
    board.push_san("Qg7#")
    outcome = board.outcome()
    assert outcome is not None
    bar = AdvantageBar()

    bar.set_outcome(outcome)

    assert bar.white_share == 1.0
    assert "WHITE WINS" in bar.render().plain


def test_advantage_bar_rejects_ambiguous_engine_score() -> None:
    bar = AdvantageBar()

    with pytest.raises(ValueError, match="centipawns or mate"):
        bar.set_evaluation(evaluation_cp=None, mate_in=None)
