"""Shared renderer protocol and small layout helpers."""

from __future__ import annotations

from typing import Protocol

from rich.cells import cell_len
from rich.segment import Segment
from rich.style import Style

from .mode import RendererMode


def center_cells(text: str, width: int) -> str:
    """Center text according to terminal-cell width."""

    rendered_width = cell_len(text)
    if rendered_width > width:
        raise ValueError(
            f"Content occupies {rendered_width} terminal cells, "
            f"but only {width} are available."
        )

    padding = width - rendered_width
    left_padding = padding // 2
    right_padding = padding - left_padding
    return (" " * left_padding) + text + (" " * right_padding)


def render_text_square_row(
    content: str,
    *,
    foreground: str | None,
    background: str,
    bold: bool = False,
    square_row: int,
    square_height: int,
    outline: str | None = None,
) -> tuple[Segment, ...]:
    """Render one text-based square row with an optional perimeter outline."""

    style = Style(color=foreground, bgcolor=background, bold=bold)
    if outline is None:
        return (Segment(content, style),)

    outline_style = Style(color=foreground, bgcolor=outline, bold=bold)
    if square_row in {0, square_height - 1} or len(content) <= 2:
        return (Segment(content, outline_style),)

    return (
        Segment(content[0], outline_style),
        Segment(content[1:-1], style),
        Segment(content[-1], outline_style),
    )


class PieceRenderer(Protocol):
    """Render a chess piece into square-sized terminal rows."""

    mode: RendererMode

    def render_square_rows(
        self,
        *,
        piece: str,
        square_width: int,
        square_height: int,
        background: str,
        visual_state: str,
        quiet_target: bool,
        capture_target: bool,
    ) -> tuple[tuple[Segment, ...], ...]:
        """Render exactly `square_height` terminal rows."""
        ...
