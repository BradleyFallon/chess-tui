"""Strict Textual user interface for displaying a chess position."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING
from rich.segment import Segment
from rich.style import Style
from textual.app import App
from textual.events import Click, Leave, MouseMove
from textual.geometry import Size
from textual.message import Message
from textual.strip import Strip
from textual.widget import Widget

from .board import DEFAULT_STARTING_FEN, FILES, ParsedFen, format_fen, parse_fen
from .game import square_name
from .modes import AppMode
from .renderers.base import PieceRenderer, center_cells
from .renderers.colors import (
    CAPTURE_SQUARE,
    CHECK_SQUARE,
    DARK_SQUARE,
    HOVER_SQUARE,
    LABEL_COLOR,
    LEGAL_SQUARE,
    LIGHT_SQUARE,
    PENDING_SOURCE,
    PENDING_TARGET,
    SELECTED_SQUARE,
)
from .renderers.factory import create_piece_renderer
from .renderers.mode import RendererMode
from .renderers.pixel_mask import (
    PIXEL_MASK_SQUARE_HEIGHT,
    PIXEL_MASK_SQUARE_WIDTH,
)
from .runtime import TerminalCapabilityError
from .view import BoardInputMode, BoardViewState

if TYPE_CHECKING:
    from .opening import OpeningMoveSource

BOARD_LEFT_MARGIN = 3
SQUARE_PRESETS = ((7, 3), (5, 2), (3, 1))


@dataclass(frozen=True, slots=True)
class BoardGeometry:
    """Board dimensions measured in terminal cells."""

    square_width: int
    square_height: int

    @property
    def width(self) -> int:
        return BOARD_LEFT_MARGIN + (8 * self.square_width)

    @property
    def height(self) -> int:
        return 2 + (8 * self.square_height)


def calculate_geometry(
    terminal_cells: Size,
    terminal_pixels: Size | None = None,
    *,
    reserved_rows: int = 0,
    renderer_mode: RendererMode | str = RendererMode.PIXEL_MASK,
) -> BoardGeometry:
    """Calculate geometry without changing or degrading the selected renderer."""

    if terminal_cells.width <= 0 or terminal_cells.height <= 0:
        raise TerminalCapabilityError("The terminal reported an invalid cell size.")
    if reserved_rows < 0:
        raise ValueError("Reserved rows cannot be negative.")
    if terminal_pixels is not None and (
        terminal_pixels.width <= 0 or terminal_pixels.height <= 0
    ):
        raise TerminalCapabilityError("The terminal reported an invalid pixel size.")

    try:
        mode = RendererMode(renderer_mode)
    except ValueError as exc:
        raise TerminalCapabilityError(
            f"Unsupported renderer mode: {renderer_mode!r}."
        ) from exc

    if mode is RendererMode.PIXEL_MASK:
        geometry = BoardGeometry(
            PIXEL_MASK_SQUARE_WIDTH,
            PIXEL_MASK_SQUARE_HEIGHT,
        )
        required_height = geometry.height + reserved_rows
        if (
            terminal_cells.width < geometry.width
            or terminal_cells.height < required_height
        ):
            raise TerminalCapabilityError(
                "CHESS TUI DISPLAY ERROR\n\n"
                "Renderer:\n"
                "pixel-mask\n\n"
                "The retro-8 renderer requires at least:\n"
                f"{geometry.width} columns × {required_height} rows\n\n"
                "Current terminal:\n"
                f"{terminal_cells.width} columns × {terminal_cells.height} rows\n\n"
                "Resize the terminal or explicitly select another mode:\n\n"
                "    chess-tui --renderer unicode"
            )
        return geometry

    candidates = [
        BoardGeometry(square_width, square_height)
        for square_width, square_height in SQUARE_PRESETS
        if BOARD_LEFT_MARGIN + (8 * square_width) <= terminal_cells.width
        and 2 + (8 * square_height) + reserved_rows <= terminal_cells.height
    ]
    if not candidates:
        raise TerminalCapabilityError(
            "The terminal is too small to display the compact chessboard; "
            f"at least {BoardGeometry(*SQUARE_PRESETS[-1]).width}x"
            f"{BoardGeometry(*SQUARE_PRESETS[-1]).height + reserved_rows} "
            "cells are required."
        )
    if terminal_pixels is None:
        return candidates[0]

    cell_width = terminal_pixels.width / terminal_cells.width
    cell_height = terminal_pixels.height / terminal_cells.height

    def physical_aspect_error(geometry: BoardGeometry) -> float:
        square_width = geometry.square_width * cell_width
        square_height = geometry.square_height * cell_height
        return abs(square_width - square_height) / max(square_width, square_height)

    return min(
        candidates,
        key=lambda geometry: (
            physical_aspect_error(geometry),
            -(geometry.square_width * geometry.square_height),
        ),
    )


def display_coordinates_to_square(
    display_file: int, display_rank: int, flipped: bool
) -> int:
    """Convert zero-based display coordinates to an a1-based square index."""

    if not 0 <= display_file < 8 or not 0 <= display_rank < 8:
        raise ValueError("Display file and rank must be between 0 and 7.")
    if flipped:
        file_index = 7 - display_file
        rank = display_rank
    else:
        file_index = display_file
        rank = 7 - display_rank
    return (rank * 8) + file_index


def square_to_display_coordinates(square: int, flipped: bool) -> tuple[int, int]:
    """Convert an a1-based square index to zero-based display coordinates."""

    if not 0 <= square < 64:
        raise ValueError("Square index must be between 0 and 63.")
    file_index = square % 8
    rank = square // 8
    if flipped:
        return 7 - file_index, rank
    return file_index, 7 - rank


def cell_offset_to_square(
    x: int, y: int, geometry: BoardGeometry, flipped: bool
) -> int | None:
    """Map a widget cell offset to a square, excluding board labels."""

    board_x = x - BOARD_LEFT_MARGIN
    board_y = y - 1
    if board_x < 0 or board_y < 0:
        return None
    display_file = board_x // geometry.square_width
    display_rank = board_y // geometry.square_height
    if display_file >= 8 or display_rank >= 8:
        return None
    return display_coordinates_to_square(display_file, display_rank, flipped)


class ChessBoard(Widget):
    """Render a chess position and emit pointer interactions as square messages."""

    class SquareClicked(Message):
        def __init__(self, square: int) -> None:
            self.square = square
            super().__init__()

    class SquareHovered(Message):
        def __init__(self, square: int | None) -> None:
            self.square = square
            super().__init__()

    def __init__(
        self,
        position: ParsedFen,
        renderer: PieceRenderer | None = None,
        *,
        input_mode: BoardInputMode = BoardInputMode.MOVE_ENTRY,
    ) -> None:
        super().__init__()
        self.view_state = BoardViewState(position=position)
        self.geometry: BoardGeometry | None = None
        self.flipped = False
        self.input_mode = input_mode
        self.renderer = (
            renderer
            if renderer is not None
            else create_piece_renderer(RendererMode.PIXEL_MASK)
        )

    def configure(self, geometry: BoardGeometry) -> None:
        """Apply validated terminal geometry to the board."""

        self.geometry = geometry
        self.styles.width = geometry.width
        self.styles.height = geometry.height
        self.refresh(layout=True)

    def unconfigure(self) -> None:
        """Hide board content until the terminal fits a geometry preset."""

        self.geometry = None
        self.styles.width = 1
        self.styles.height = 1
        self.refresh(layout=True)

    def update_view(
        self,
        view_state: BoardViewState,
        *,
        flipped: bool,
    ) -> None:
        """Apply renderer-neutral board presentation state."""

        self.view_state = view_state
        self.flipped = flipped
        self.refresh()

    def square_at(self, x: int, y: int) -> int | None:
        geometry = self.geometry
        if geometry is None:
            return None
        return cell_offset_to_square(x, y, geometry, self.flipped)

    def on_mouse_move(self, event: MouseMove) -> None:
        square = self.square_at(event.x, event.y)
        if square != self.view_state.hover_square:
            self.post_message(self.SquareHovered(square))

    def on_leave(self, event: Leave) -> None:
        if self.view_state.hover_square is not None:
            self.post_message(self.SquareHovered(None))

    def on_click(self, event: Click) -> None:
        if self.input_mode is BoardInputMode.READ_ONLY:
            return
        square = self.square_at(event.x, event.y)
        if square is not None:
            event.stop()
            self.post_message(self.SquareClicked(square))

    def render_line(self, y: int) -> Strip:
        geometry = self.geometry
        if geometry is None:
            return Strip.blank(self.size.width, self.visual_style.rich_style)
        if y < 0 or y >= geometry.height:
            return Strip.blank(geometry.width, self.visual_style.rich_style)
        if y in {0, geometry.height - 1}:
            return self._render_file_labels(geometry)

        board_y = y - 1
        display_rank = board_y // geometry.square_height
        square_row = board_y % geometry.square_height
        if display_rank >= 8:
            return Strip.blank(geometry.width, self.visual_style.rich_style)

        center_row = square_row == geometry.square_height // 2
        rank_square = display_coordinates_to_square(0, display_rank, self.flipped)
        rank_label = square_name(rank_square)[1] if center_row else " "
        segments = [
            Segment(
                f"{rank_label}{' ' * (BOARD_LEFT_MARGIN - 1)}",
                Style(color=LABEL_COLOR),
            )
        ]

        for display_file in range(8):
            square = display_coordinates_to_square(
                display_file, display_rank, self.flipped
            )
            piece = self._piece_at(square)
            background = self._square_background(square)
            visual_state = self._square_visual_state(square)
            rendered_rows = self.renderer.render_square_rows(
                piece=piece,
                square_width=geometry.square_width,
                square_height=geometry.square_height,
                background=background,
                visual_state=visual_state,
                quiet_target=square in self.view_state.quiet_targets,
                capture_target=square in self.view_state.capture_targets,
            )
            segments.extend(rendered_rows[square_row])

        return Strip(segments, geometry.width)

    def _render_file_labels(self, geometry: BoardGeometry) -> Strip:
        files = reversed(FILES) if self.flipped else FILES
        labels = " " * BOARD_LEFT_MARGIN + "".join(
            center_cells(file_, geometry.square_width) for file_ in files
        )
        labels = labels.ljust(geometry.width)
        return Strip([Segment(labels, Style(color=LABEL_COLOR))], geometry.width)

    def _piece_at(self, square: int) -> str:
        rank = square // 8
        file_index = square % 8
        return self.view_state.position.board[7 - rank][file_index]

    def _square_visual_state(self, square: int) -> str:
        interaction = self.view_state
        if square == interaction.checked_king:
            return "check"
        pending_move = interaction.pending_move
        if pending_move is not None:
            if square == pending_move.to_square:
                return "pending-target"
            if square == pending_move.from_square:
                return "pending-source"
        if square == interaction.selected_square:
            return "selected"
        if square in interaction.capture_targets:
            return "capture"
        if square in interaction.quiet_targets:
            return "quiet"
        if square == interaction.hover_square:
            return "hover"
        last_move = interaction.last_move
        if last_move is not None and square in {
            last_move.from_square,
            last_move.to_square,
        }:
            return "last-move"
        return "normal"

    def _square_background(self, square: int) -> str:
        interaction = self.view_state
        if square == interaction.checked_king:
            return CHECK_SQUARE
        pending_move = interaction.pending_move
        if pending_move is not None:
            if square == pending_move.to_square:
                return PENDING_TARGET
            if square == pending_move.from_square:
                return PENDING_SOURCE
        if square == interaction.selected_square:
            return SELECTED_SQUARE
        if square in interaction.capture_targets:
            return CAPTURE_SQUARE
        if square in interaction.quiet_targets:
            return LEGAL_SQUARE
        if square == interaction.hover_square:
            return HOVER_SQUARE
        rank = square // 8
        file_index = square % 8
        return LIGHT_SQUARE if (rank + file_index) % 2 else DARK_SQUARE


class ChessTui(App[None]):
    """Top-level shell routing local-game, quiz, and author modes."""

    def __init__(
        self,
        position: ParsedFen | None = None,
        *,
        mode: AppMode = AppMode.LOCAL_GAME,
        renderer: PieceRenderer | None = None,
        fen: str | None = None,
        flow_path: Path | None = None,
        opening_source: OpeningMoveSource | None = None,
    ) -> None:
        super().__init__()
        from .screens.local_game import LocalGameScreen
        from .screens.quiz import QuizScreen
        from .screens.author import AuthorScreen
        from .sessions.demo import (
            DemoQuizProvider,
            DemoQuizSession,
            list_demo_flows,
        )

        self.mode = AppMode(mode)
        selected_renderer = renderer or create_piece_renderer(RendererMode.PIXEL_MASK)
        if position is None:
            position = parse_fen(fen or DEFAULT_STARTING_FEN)
        elif fen is not None and format_fen(position) != format_fen(parse_fen(fen)):
            raise ValueError("position and fen describe different positions")

        if self.mode is AppMode.LOCAL_GAME:
            self.initial_screen = LocalGameScreen(position, selected_renderer)
        elif self.mode is AppMode.QUIZ_DEMO:
            provider = DemoQuizProvider()
            flow = list_demo_flows()[0]
            self.initial_screen = QuizScreen(
                provider,
                flow,
                DemoQuizSession(flow.id),
                selected_renderer,
            )
        else:
            if flow_path is None:
                raise ValueError("author mode requires a flow_path")
            self.initial_screen = AuthorScreen(
                flow_path,
                selected_renderer,
                opening_source,
            )

    def on_mount(self) -> None:
        self.push_screen(self.initial_screen)

    @property
    def board(self) -> ChessBoard:
        return self.initial_screen.board

    @property
    def renderer(self) -> PieceRenderer:
        return self.initial_screen.renderer

    @property
    def preferred_renderer(self) -> PieceRenderer:
        return self.initial_screen.renderer_controller.active

    @property
    def status(self):
        return self.initial_screen.status

    @property
    def failure(self):
        return self.initial_screen.failure

    @property
    def controller(self):
        from .screens.local_game import LocalGameScreen

        if not isinstance(self.initial_screen, LocalGameScreen):
            raise AttributeError("Quiz mode does not expose a local game controller.")
        return self.initial_screen.controller

    @property
    def flipped(self) -> bool:
        from .screens.local_game import LocalGameScreen

        return (
            self.initial_screen.flipped
            if isinstance(self.initial_screen, LocalGameScreen)
            else False
        )


def run_chess_app(
    position: ParsedFen,
    *,
    renderer: PieceRenderer | None = None,
    mode: AppMode = AppMode.LOCAL_GAME,
    flow_path: Path | None = None,
    opening_source: OpeningMoveSource | None = None,
) -> None:
    """Run the selected application mode."""

    app = ChessTui(
        position,
        mode=mode,
        renderer=renderer,
        flow_path=flow_path,
        opening_source=opening_source,
    )
    app.run()
