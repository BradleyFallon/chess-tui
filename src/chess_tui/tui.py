"""Strict Textual user interface for displaying a chess position."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from rich.cells import cell_len
from rich.segment import Segment
from rich.style import Style
from textual.app import App, ComposeResult
from textual.events import Click, Leave, MouseMove, Resize
from textual.geometry import Size
from textual.message import Message
from textual.strip import Strip
from textual.widget import Widget
from textual.widgets import Static

from .board import (
    FILES,
    PIECE_GLYPHS,
    PIECE_SPRITES,
    PIXEL_SPRITE_HEIGHT,
    PIXEL_SPRITE_WIDTH,
    ParsedFen,
)
from .game import BoardInteraction, GameController, square_name
from .runtime import TerminalCapabilityError

BOARD_LEFT_MARGIN = 3
SQUARE_PRESETS = ((7, 3), (5, 2), (3, 1))
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
LEGAL_MARKER = "•"
PieceMode = Literal["pixel", "figurine"]


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
) -> BoardGeometry:
    """Calculate centered board geometry from available terminal metrics."""

    if terminal_cells.width <= 0 or terminal_cells.height <= 0:
        raise TerminalCapabilityError("The terminal reported an invalid cell size.")
    if reserved_rows < 0:
        raise ValueError("Reserved rows cannot be negative.")
    if terminal_pixels is not None and (
        terminal_pixels.width <= 0 or terminal_pixels.height <= 0
    ):
        raise TerminalCapabilityError("The terminal reported an invalid pixel size.")

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


def use_pixel_pieces(geometry: BoardGeometry) -> bool:
    """Return whether a square can contain the full pixel-art piece sprite."""

    return (
        geometry.square_width >= PIXEL_SPRITE_WIDTH
        and geometry.square_height >= PIXEL_SPRITE_HEIGHT
    )


def center_cells(text: str, width: int) -> str:
    """Center text according to rendered terminal-cell width."""

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


def render_piece_row(
    piece: str,
    square_row: int,
    geometry: BoardGeometry,
    piece_mode: PieceMode = "pixel",
) -> str:
    """Render one terminal row of a piece in pixel or figurine mode."""

    if piece == ".":
        return " " * geometry.square_width
    if piece_mode == "figurine" or not use_pixel_pieces(geometry):
        if square_row == geometry.square_height // 2:
            return center_cells(PIECE_GLYPHS[piece], geometry.square_width)
        return " " * geometry.square_width

    sprite = PIECE_SPRITES[piece.upper()]
    vertical_offset = (geometry.square_height - len(sprite)) // 2
    sprite_row = square_row - vertical_offset
    if not 0 <= sprite_row < len(sprite):
        return " " * geometry.square_width
    return center_cells(sprite[sprite_row], geometry.square_width)


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

    def __init__(self, position: ParsedFen) -> None:
        super().__init__()
        self.position = position
        self.interaction = BoardInteraction()
        self.geometry: BoardGeometry | None = None
        self.flipped = False
        self.piece_mode: PieceMode = "pixel"

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
        position: ParsedFen,
        interaction: BoardInteraction,
        *,
        flipped: bool,
        piece_mode: PieceMode,
    ) -> None:
        """Apply the controller's current renderer-facing state."""

        self.position = position
        self.interaction = interaction
        self.flipped = flipped
        self.piece_mode: PieceMode = piece_mode
        self.refresh()

    def square_at(self, x: int, y: int) -> int | None:
        geometry = self.geometry
        if geometry is None:
            return None
        return cell_offset_to_square(x, y, geometry, self.flipped)

    def on_mouse_move(self, event: MouseMove) -> None:
        square = self.square_at(event.x, event.y)
        if square != self.interaction.hover_square:
            self.post_message(self.SquareHovered(square))

    def on_leave(self, event: Leave) -> None:
        if self.interaction.hover_square is not None:
            self.post_message(self.SquareHovered(None))

    def on_click(self, event: Click) -> None:
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
            if piece != ".":
                foreground = WHITE_PIECE if piece.isupper() else BLACK_PIECE
                content = render_piece_row(
                    piece,
                    square_row,
                    geometry,
                    self.piece_mode,
                )
                style = Style(color=foreground, bgcolor=background, bold=True)
            elif center_row and square in self.interaction.quiet_targets:
                content = center_cells(LEGAL_MARKER, geometry.square_width)
                style = Style(color=WHITE_PIECE, bgcolor=background, bold=True)
            else:
                content = " " * geometry.square_width
                style = Style(bgcolor=background)
            segments.append(Segment(content, style))

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
        return self.position.board[7 - rank][file_index]

    def _square_background(self, square: int) -> str:
        interaction = self.interaction
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
        last_move = interaction.last_move
        if last_move is not None and square in {
            last_move.from_square,
            last_move.to_square,
        }:
            return LAST_MOVE_SQUARE
        rank = square // 8
        file_index = square % 8
        return LIGHT_SQUARE if (rank + file_index) % 2 else DARK_SQUARE


class ChessTui(App[None]):
    """Display and interact with a FEN-backed chess position."""

    CSS = """
    Screen {
        align: center middle;
        background: #172019;
    }
    ChessBoard {
        pointer: pointer;
    }
    #status {
        dock: bottom;
        width: 100%;
        height: 1;
        color: #d7ddcf;
        background: #111713;
        text-align: center;
    }
    """
    BINDINGS = [
        ("q", "quit", "Quit"),
        ("f", "flip_board", "Flip"),
        ("v", "toggle_piece_mode", "Pieces"),
        ("enter", "confirm_move", "Confirm"),
        ("escape", "cancel_move", "Cancel"),
    ]

    def __init__(
        self,
        position: ParsedFen,
        *,
        piece_mode: PieceMode = "pixel",
    ) -> None:
        super().__init__()
        self.controller = GameController(position)
        self.board = ChessBoard(position)
        self.status = Static("", id="status", markup=False)
        self.failure: TerminalCapabilityError | None = None
        self.flipped = False
        self.piece_mode: PieceMode = piece_mode
        self._geometry_error: str | None = None

    def compose(self) -> ComposeResult:
        yield self.board
        yield self.status

    def on_mount(self) -> None:
        self._sync_view()

    def on_resize(self, event: Resize) -> None:
        try:
            geometry = calculate_geometry(
                event.size,
                event.pixel_size,
                reserved_rows=1,
            )
        except TerminalCapabilityError as exc:
            self._geometry_error = str(exc)
            self.board.unconfigure()
            self._update_status()
            return
        self._geometry_error = None
        self.board.configure(geometry)
        self._update_status()

    def on_chess_board_square_hovered(self, message: ChessBoard.SquareHovered) -> None:
        self.controller.set_hover(message.square)
        self._sync_view()

    def on_chess_board_square_clicked(self, message: ChessBoard.SquareClicked) -> None:
        self.controller.handle_square(message.square)
        self._sync_view()

    def action_flip_board(self) -> None:
        self.flipped = not self.flipped
        self._sync_view()

    def action_toggle_piece_mode(self) -> None:
        self.piece_mode = "figurine" if self.piece_mode == "pixel" else "pixel"
        self._sync_view()

    def action_confirm_move(self) -> None:
        self.controller.confirm_move()
        self._sync_view()

    def action_cancel_move(self) -> None:
        self.controller.clear_selection()
        self._sync_view()

    def _sync_view(self) -> None:
        self.board.update_view(
            self.controller.position,
            self.controller.interaction,
            flipped=self.flipped,
            piece_mode=self.piece_mode,
        )
        self._update_status()

    def _update_status(self) -> None:
        if self._geometry_error is not None:
            self.status.update(self._geometry_error)
            return

        interaction = self.controller.interaction
        if interaction.pending_move is not None:
            move = interaction.pending_move
            text = (
                f"{square_name(move.from_square)} -> {square_name(move.to_square)} "
                "| ENTER confirm | ESC cancel"
            )
        elif interaction.selected_square is not None:
            text = (
                f"{square_name(interaction.selected_square)} selected | "
                "choose a highlighted destination | ESC cancel"
            )
        else:
            side = "White" if self.controller.position.active_color == "w" else "Black"
            text = f"{side} to move | click a piece | F flip | Q quit"
        geometry = self.board.geometry
        effective_mode = (
            "pixel"
            if self.piece_mode == "pixel"
            and geometry is not None
            and use_pixel_pieces(geometry)
            else "figurine"
        )
        if self.piece_mode == "pixel" and effective_mode == "figurine":
            effective_mode = "figurine (compact)"
        text += f" | V pieces: {effective_mode}"
        self.status.update(text)


def run_chess_app(
    position: ParsedFen,
    *,
    piece_mode: PieceMode = "pixel",
) -> None:
    """Run the Textual application and propagate strict capability failures."""

    app = ChessTui(position, piece_mode=piece_mode)
    app.run()
