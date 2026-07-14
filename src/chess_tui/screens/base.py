"""Shared renderer sizing behavior for board screens."""

from __future__ import annotations

from textual.geometry import Size

from ..renderers.base import PieceRenderer
from ..tui import BoardGeometry, calculate_geometry


class RendererController:
    """Calculate geometry without changing the selected renderer."""

    def __init__(self, renderer: PieceRenderer) -> None:
        self.renderer = renderer

    @property
    def active(self) -> PieceRenderer:
        return self.renderer

    def choose(
        self,
        terminal_cells: Size,
        terminal_pixels: Size | None,
        *,
        reserved_rows: int,
    ) -> tuple[PieceRenderer, BoardGeometry]:
        geometry = calculate_geometry(
            terminal_cells,
            terminal_pixels,
            reserved_rows=reserved_rows,
            renderer_mode=self.renderer.mode,
        )
        return self.renderer, geometry
