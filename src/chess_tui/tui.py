"""Strict Textual user interface for displaying a chess position."""

from __future__ import annotations

from dataclasses import dataclass

from rich.segment import Segment
from rich.style import Style
from textual.app import App, ComposeResult
from textual.events import Resize
from textual.geometry import Size
from textual.strip import Strip
from textual.widget import Widget

from .board import FILES, PIECE_GLYPHS, ParsedFen
from .runtime import TerminalCapabilityError

BOARD_LEFT_MARGIN = 3
SQUARE_HEIGHT = 3
DEFAULT_SQUARE_WIDTH = 5
LIGHT_SQUARE = "#dfe8bd"
DARK_SQUARE = "#527a4b"
WHITE_PIECE = "#fffdf5"
BLACK_PIECE = "#111713"
LABEL_COLOR = "#d7ddcf"


@dataclass(frozen=True, slots=True)
class BoardGeometry:
    """Board dimensions measured in terminal cells."""

    square_width: int
    square_height: int = SQUARE_HEIGHT

    @property
    def width(self) -> int:
        return BOARD_LEFT_MARGIN + (8 * self.square_width)

    @property
    def height(self) -> int:
        return 2 + (8 * self.square_height)


def calculate_geometry(
    terminal_cells: Size, terminal_pixels: Size | None = None
) -> BoardGeometry:
    """Calculate centered board geometry from available terminal metrics."""

    if terminal_cells.width <= 0 or terminal_cells.height <= 0:
        raise TerminalCapabilityError("The terminal reported an invalid cell size.")
    if terminal_pixels is not None:
        if terminal_pixels.width <= 0 or terminal_pixels.height <= 0:
            raise TerminalCapabilityError(
                "The terminal reported an invalid pixel size."
            )

        cell_width = terminal_pixels.width / terminal_cells.width
        cell_height = terminal_pixels.height / terminal_cells.height
        ideal_width = SQUARE_HEIGHT * cell_height / cell_width
        candidates = range(3, 12, 2)
        square_width = min(
            candidates, key=lambda width: (abs(width - ideal_width), width)
        )
        geometry = BoardGeometry(square_width)
        square_pixel_width = geometry.square_width * cell_width
        square_pixel_height = geometry.square_height * cell_height
        aspect_error = (
            abs(square_pixel_width - square_pixel_height) / square_pixel_height
        )
        if aspect_error > 0.20:
            raise TerminalCapabilityError(
                "The terminal cell aspect ratio cannot produce centered square cells "
                "within the required 20% tolerance."
            )
    else:
        geometry = BoardGeometry(DEFAULT_SQUARE_WIDTH)

    if geometry.width > terminal_cells.width or geometry.height > terminal_cells.height:
        raise TerminalCapabilityError(
            f"The terminal is {terminal_cells.width}x{terminal_cells.height} cells, "
            f"but the board requires at least {geometry.width}x{geometry.height}."
        )
    return geometry


class ChessBoard(Widget):
    """Render an immutable chess position using Textual's line API."""

    def __init__(self, position: ParsedFen) -> None:
        super().__init__()
        self.position = position
        self.geometry: BoardGeometry | None = None

    def configure(self, geometry: BoardGeometry) -> None:
        """Apply validated terminal geometry to the board."""

        self.geometry = geometry
        self.styles.width = geometry.width
        self.styles.height = geometry.height
        self.refresh(layout=True)

    def render_line(self, y: int) -> Strip:
        geometry = self.geometry
        if geometry is None:
            return Strip.blank(self.size.width, self.visual_style.rich_style)
        if y < 0 or y >= geometry.height:
            return Strip.blank(geometry.width, self.visual_style.rich_style)
        if y in {0, geometry.height - 1}:
            return self._render_file_labels(geometry)

        board_y = y - 1
        rank_index = board_y // geometry.square_height
        square_row = board_y % geometry.square_height
        if rank_index >= 8:
            return Strip.blank(geometry.width, self.visual_style.rich_style)

        center_row = square_row == geometry.square_height // 2
        rank_label = str(8 - rank_index) if center_row else " "
        segments = [
            Segment(
                f"{rank_label}{' ' * (BOARD_LEFT_MARGIN - 1)}",
                Style(color=LABEL_COLOR),
            )
        ]

        for file_index, square in enumerate(self.position.board[rank_index]):
            background = (
                LIGHT_SQUARE if (rank_index + file_index) % 2 == 0 else DARK_SQUARE
            )
            if center_row and square != ".":
                foreground = WHITE_PIECE if square.isupper() else BLACK_PIECE
                content = PIECE_GLYPHS[square].center(geometry.square_width)
                style = Style(color=foreground, bgcolor=background, bold=True)
            else:
                content = " " * geometry.square_width
                style = Style(bgcolor=background)
            segments.append(Segment(content, style))

        return Strip(segments, geometry.width)

    @staticmethod
    def _render_file_labels(geometry: BoardGeometry) -> Strip:
        labels = " " * BOARD_LEFT_MARGIN + "".join(
            file_.center(geometry.square_width) for file_ in FILES
        )
        labels = labels.ljust(geometry.width)
        return Strip([Segment(labels, Style(color=LABEL_COLOR))], geometry.width)


class ChessTui(App[None]):
    """Display a FEN position with validated terminal-cell geometry."""

    CSS = """
    Screen {
        align: center middle;
        background: #172019;
    }
    """
    BINDINGS = [("q", "quit", "Quit")]

    def __init__(self, position: ParsedFen) -> None:
        super().__init__()
        self.board = ChessBoard(position)
        self.failure: TerminalCapabilityError | None = None

    def compose(self) -> ComposeResult:
        yield self.board

    def on_resize(self, event: Resize) -> None:
        try:
            geometry = calculate_geometry(event.size, event.pixel_size)
        except TerminalCapabilityError as exc:
            self._fail(exc)
            return
        self.board.configure(geometry)

    def _fail(self, error: TerminalCapabilityError) -> None:
        self.failure = error
        self.exit()


def run_chess_app(position: ParsedFen) -> None:
    """Run the Textual application and propagate strict capability failures."""

    app = ChessTui(position)
    app.run(mouse=False)
    if app.failure is not None:
        raise app.failure
