"""Unicode glyph renderer."""

from __future__ import annotations

from dataclasses import dataclass

from rich.segment import Segment
from rich.style import Style

from ..board import PIECE_GLYPHS
from .base import center_cells
from .colors import (
    BLACK_PIECE,
    LEGAL_MARKER,
    WHITE_PIECE,
)
from .errors import RendererStartupError
from .mode import RendererMode


@dataclass(slots=True)
class UnicodePieceRenderer:
    """Render pieces as a single Unicode glyph centered in each square."""

    mode: RendererMode = RendererMode.UNICODE

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
        rows: list[tuple[Segment, ...]] = []
        center_row = square_height // 2
        for square_row in range(square_height):
            if piece != "." and square_row == center_row:
                glyph = PIECE_GLYPHS[piece]
                color = WHITE_PIECE if piece.isupper() else BLACK_PIECE
                content = center_cells(glyph, square_width)
                rows.append((Segment(content, Style(color=color, bgcolor=background)),))
                continue
            if piece == "." and quiet_target and square_row == center_row:
                content = center_cells(LEGAL_MARKER, square_width)
                rows.append(
                    (
                        Segment(
                            content,
                            Style(color=WHITE_PIECE, bgcolor=background, bold=True),
                        ),
                    )
                )
                continue
            rows.append((Segment(" " * square_width, Style(bgcolor=background)),))
        return tuple(rows)


def build_unicode_renderer() -> UnicodePieceRenderer:
    """Validate Unicode glyph widths and construct the renderer."""

    try:
        from rich.cells import cell_len
    except ImportError as exc:  # pragma: no cover - import failure is environmental
        raise RendererStartupError(
            "Rich is required to validate Unicode renderer glyph widths."
        ) from exc

    invalid_glyphs = [glyph for glyph in PIECE_GLYPHS.values() if cell_len(glyph) != 1]
    if invalid_glyphs:
        rendered = ", ".join(repr(glyph) for glyph in invalid_glyphs)
        raise RendererStartupError(
            "Unicode renderer requires every chess glyph to occupy exactly one "
            f"terminal cell; invalid: {rendered}."
        )

    return UnicodePieceRenderer()
