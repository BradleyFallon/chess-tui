"""Shared renderer protocol and small layout helpers."""

from __future__ import annotations

from typing import Protocol

from rich.cells import cell_len
from rich.segment import Segment

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
