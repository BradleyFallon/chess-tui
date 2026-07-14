"""Shared renderer sizing behavior for board screens."""

from __future__ import annotations

from textual.geometry import Size

from ..renderers.base import PieceRenderer
from ..renderers.errors import RendererStartupError
from ..renderers.factory import create_piece_renderer
from ..renderers.mode import RendererMode
from ..runtime import TerminalCapabilityError
from ..tui import BoardGeometry, calculate_geometry


class RendererController:
    def __init__(self, preferred: PieceRenderer) -> None:
        self.preferred = preferred
        self.active = preferred
        self._unicode_fallback: PieceRenderer | None = None

    def choose(
        self,
        terminal_cells: Size,
        terminal_pixels: Size | None,
        *,
        reserved_rows: int,
    ) -> tuple[PieceRenderer, BoardGeometry]:
        pixel_failure: str | None = None
        try:
            geometry = calculate_geometry(
                terminal_cells,
                terminal_pixels,
                reserved_rows=reserved_rows,
                renderer_mode=self.preferred.mode,
            )
            self.active = self.preferred
            return self.active, geometry
        except TerminalCapabilityError as error:
            if self.preferred.mode is not RendererMode.PIXEL_MASK:
                raise
            pixel_failure = str(error)

        fallback = self._unicode_fallback
        if fallback is None:
            try:
                fallback = create_piece_renderer(RendererMode.UNICODE)
            except RendererStartupError as exc:
                raise TerminalCapabilityError(
                    f"{pixel_failure}\n\nUnicode fallback is unavailable: {exc}"
                ) from exc
            self._unicode_fallback = fallback
        try:
            geometry = calculate_geometry(
                terminal_cells,
                terminal_pixels,
                reserved_rows=reserved_rows,
                renderer_mode=fallback.mode,
            )
        except TerminalCapabilityError as unicode_error:
            raise TerminalCapabilityError(
                f"{pixel_failure}\n\nUnicode fallback also failed:\n{unicode_error}"
            ) from unicode_error
        self.active = fallback
        return fallback, geometry

    @property
    def fallback_active(self) -> bool:
        return self.active is not self.preferred
