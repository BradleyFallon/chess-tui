"""Legacy three-row sprite renderer."""

from __future__ import annotations

from dataclasses import dataclass

from rich.segment import Segment
from rich.style import Style

from ..board import PIECE_GLYPHS, PIECE_SPRITES, PIXEL_SPRITE_HEIGHT, PIXEL_SPRITE_WIDTH
from .base import center_cells
from .colors import (
    BLACK_PIECE,
    LEGAL_MARKER,
    WHITE_PIECE,
)
from .errors import RendererStartupError
from .mode import RendererMode


@dataclass(slots=True)
class LegacySpriteRenderer:
    """Render the historical three-row handcrafted piece sprites."""

    mode: RendererMode = RendererMode.LEGACY_SPRITE

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
        if piece != ".":
            sprite = PIECE_SPRITES[piece.upper()]
            vertical_offset = (square_height - len(sprite)) // 2
            for square_row in range(square_height):
                sprite_row = square_row - vertical_offset
                if 0 <= sprite_row < len(sprite):
                    content = center_cells(sprite[sprite_row], square_width)
                    color = WHITE_PIECE if piece.isupper() else BLACK_PIECE
                    rows.append(
                        (
                            Segment(
                                content,
                                Style(color=color, bgcolor=background, bold=True),
                            ),
                        )
                    )
                else:
                    rows.append(
                        (Segment(" " * square_width, Style(bgcolor=background)),)
                    )
            return tuple(rows)

        center_row = square_height // 2
        for square_row in range(square_height):
            if quiet_target and square_row == center_row:
                content = center_cells(LEGAL_MARKER, square_width)
                rows.append(
                    (
                        Segment(
                            content,
                            Style(color=WHITE_PIECE, bgcolor=background, bold=True),
                        ),
                    )
                )
            else:
                rows.append((Segment(" " * square_width, Style(bgcolor=background)),))
        return tuple(rows)


def build_legacy_sprite_renderer() -> LegacySpriteRenderer:
    """Validate sprite dimensions and construct the legacy renderer."""

    try:
        from rich.cells import cell_len
    except ImportError as exc:  # pragma: no cover - import failure is environmental
        raise RendererStartupError(
            "Rich is required to validate legacy sprite widths."
        ) from exc

    expected_pieces = {piece for piece in PIECE_GLYPHS if piece.isupper()}
    if set(PIECE_SPRITES) != expected_pieces:
        missing = ", ".join(sorted(expected_pieces - set(PIECE_SPRITES)))
        raise RendererStartupError(
            f"Legacy sprite renderer requires all six white sprites; missing: {missing or 'none'}."
        )

    if any(len(sprite) != PIXEL_SPRITE_HEIGHT for sprite in PIECE_SPRITES.values()):
        raise RendererStartupError(
            f"Legacy sprite renderer requires {PIXEL_SPRITE_HEIGHT}-row sprites."
        )

    invalid_rows = [
        row
        for sprite in PIECE_SPRITES.values()
        for row in sprite
        if cell_len(row) != PIXEL_SPRITE_WIDTH
    ]
    if invalid_rows:
        rendered = ", ".join(repr(row) for row in invalid_rows)
        raise RendererStartupError(
            f"Legacy sprite rows must occupy exactly {PIXEL_SPRITE_WIDTH} cells; "
            f"invalid: {rendered}."
        )

    return LegacySpriteRenderer()
