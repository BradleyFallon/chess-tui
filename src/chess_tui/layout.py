"""Responsive screen-layout decisions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from textual.geometry import Size

from .renderers.mode import RendererMode
from .runtime import TerminalCapabilityError
from .tui import BoardGeometry, calculate_geometry


class QuizLayoutMode(str, Enum):
    LANDSCAPE = "landscape"
    PORTRAIT = "portrait"
    COMPACT = "compact"


@dataclass(frozen=True, slots=True)
class QuizLayout:
    mode: QuizLayoutMode
    board_geometry: BoardGeometry


HEADER_ROWS = 1
STATUS_ROWS = 1
LANDSCAPE_SIDE_WIDTH = 34
LANDSCAPE_GAP = 2
PORTRAIT_PANEL_ROWS = 11
COMPACT_PANEL_ROWS = 4


def _pixel_size_for_area(
    full_cells: Size,
    full_pixels: Size | None,
    area_cells: Size,
) -> Size | None:
    if full_pixels is None:
        return None
    return Size(
        max(1, round(full_pixels.width * area_cells.width / full_cells.width)),
        max(1, round(full_pixels.height * area_cells.height / full_cells.height)),
    )


def choose_quiz_layout(
    terminal_cells: Size,
    terminal_pixels: Size | None,
    renderer_mode: RendererMode,
) -> QuizLayout:
    """Choose a screen arrangement without changing the selected renderer."""

    chrome_rows = HEADER_ROWS + STATUS_ROWS
    attempts = (
        (
            QuizLayoutMode.LANDSCAPE,
            Size(
                terminal_cells.width - LANDSCAPE_SIDE_WIDTH - LANDSCAPE_GAP,
                terminal_cells.height - chrome_rows,
            ),
        ),
        (
            QuizLayoutMode.PORTRAIT,
            Size(
                terminal_cells.width,
                terminal_cells.height - chrome_rows - PORTRAIT_PANEL_ROWS,
            ),
        ),
        (
            QuizLayoutMode.COMPACT,
            Size(
                terminal_cells.width,
                terminal_cells.height - chrome_rows - COMPACT_PANEL_ROWS,
            ),
        ),
    )
    failures: list[str] = []
    for mode, board_area in attempts:
        if board_area.width <= 0 or board_area.height <= 0:
            continue
        area_pixels = _pixel_size_for_area(terminal_cells, terminal_pixels, board_area)
        try:
            geometry = calculate_geometry(
                board_area,
                area_pixels,
                reserved_rows=0,
                renderer_mode=renderer_mode,
            )
        except TerminalCapabilityError as error:
            failures.append(f"{mode.value}: {error}")
            continue
        return QuizLayout(mode=mode, board_geometry=geometry)

    detail = "\n\n".join(failures)
    raise TerminalCapabilityError(
        "The selected renderer cannot fit in the current terminal "
        "with the quiz controls visible.\n\n"
        f"Renderer: {renderer_mode.value}\n"
        f"Terminal: {terminal_cells.width}x{terminal_cells.height}\n\n"
        f"{detail}\n\n"
        "Resize the terminal. The current renderer will resume when enough "
        "space is available."
    )
