"""Palette and color conversion helpers."""

from __future__ import annotations

from functools import lru_cache

BOARD_BACKGROUND = "#172019"
SCREEN_BACKGROUND = "#172019"
STATUS_BACKGROUND = "#111713"
LIGHT_SQUARE = "#9eaf74"
DARK_SQUARE = "#405e42"
WHITE_PIECE = "#fffdf5"
BLACK_PIECE = "#111713"
LABEL_COLOR = "#d7ddcf"
SELECTED_SQUARE = "#d6a943"
HOVER_SQUARE = "#688869"
LEGAL_SQUARE = "#55895a"
CAPTURE_SQUARE = "#a84d4d"
PENDING_SOURCE = "#bc8436"
PENDING_TARGET = "#f0c95b"
LAST_MOVE_SQUARE = "#71804c"
CHECK_SQUARE = "#d45555"
WHITE_FILL = "#f2e4c6"
WHITE_HIGHLIGHT = "#fff9ea"
WHITE_OUTLINE = "#3f3124"
WHITE_SHADOW = "#b89e7c"
BLACK_FILL = "#262d25"
BLACK_HIGHLIGHT = "#4a5649"
BLACK_OUTLINE = "#f1ead4"
BLACK_SHADOW = "#171c18"
LEGAL_MARKER = "•"


@lru_cache(maxsize=512)
def hex_to_rgba(color: str) -> tuple[int, int, int, int]:
    """Convert `#rrggbb` or `#rrggbbaa` to RGBA."""

    value = color.lstrip("#")
    if len(value) == 6:
        red, green, blue = (
            int(value[0:2], 16),
            int(value[2:4], 16),
            int(value[4:6], 16),
        )
        return red, green, blue, 255
    if len(value) == 8:
        red, green, blue, alpha = (
            int(value[0:2], 16),
            int(value[2:4], 16),
            int(value[4:6], 16),
            int(value[6:8], 16),
        )
        return red, green, blue, alpha
    raise ValueError(f"Invalid hex color: {color!r}.")


def rgba_to_hex(rgba: tuple[int, int, int, int]) -> str:
    """Convert an RGBA tuple to `#rrggbb`."""

    red, green, blue, _ = rgba
    return f"#{red:02x}{green:02x}{blue:02x}"
