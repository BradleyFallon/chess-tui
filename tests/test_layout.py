from __future__ import annotations

import pytest
from textual.geometry import Size

from chess_tui.layout import QuizLayoutMode, choose_quiz_layout
from chess_tui.renderers.mode import RendererMode
from chess_tui.runtime import TerminalCapabilityError
from chess_tui.tui import BoardGeometry


@pytest.mark.parametrize(
    ("terminal", "expected_mode"),
    (
        (Size(120, 42), QuizLayoutMode.LANDSCAPE),
        (Size(80, 52), QuizLayoutMode.PORTRAIT),
        (Size(70, 40), QuizLayoutMode.COMPACT),
    ),
)
def test_pixel_mask_quiz_layout_selection(
    terminal: Size, expected_mode: QuizLayoutMode
) -> None:
    layout = choose_quiz_layout(terminal, None, RendererMode.PIXEL_MASK)

    assert layout.mode is expected_mode
    assert layout.board_geometry == BoardGeometry(8, 4)


def test_pixel_mask_quiz_layout_reports_too_small() -> None:
    with pytest.raises(TerminalCapabilityError, match="current renderer will resume"):
        choose_quiz_layout(Size(60, 30), None, RendererMode.PIXEL_MASK)


def test_quiz_layout_scales_terminal_pixel_metrics_to_board_area() -> None:
    layout = choose_quiz_layout(Size(120, 42), Size(1200, 840), RendererMode.PIXEL_MASK)

    assert layout.mode is QuizLayoutMode.LANDSCAPE
    assert layout.board_geometry == BoardGeometry(8, 4)
