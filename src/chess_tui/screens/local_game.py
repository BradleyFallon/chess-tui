"""Current interactive local chess screen."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.events import Resize
from textual.screen import Screen
from textual.widgets import Static

from ..board import ParsedFen
from ..game import GameController, square_name
from ..renderers.base import PieceRenderer
from ..renderers.colors import LABEL_COLOR, SCREEN_BACKGROUND, STATUS_BACKGROUND
from ..runtime import TerminalCapabilityError
from ..tui import ChessBoard
from ..view import BoardInputMode, board_view_from_game
from .base import RendererController


class LocalGameScreen(Screen[None]):
    CSS = f"""
    LocalGameScreen {{ align: center middle; background: {SCREEN_BACKGROUND}; }}
    LocalGameScreen > ChessBoard {{ pointer: pointer; }}
    LocalGameScreen > #status {{
        dock: bottom; width: 100%; height: auto; color: {LABEL_COLOR};
        background: {STATUS_BACKGROUND}; text-align: center;
    }}
    """
    BINDINGS = [
        ("q", "app.quit", "Quit"),
        ("f", "flip_board", "Flip"),
        ("enter", "confirm_move", "Confirm"),
        ("escape", "cancel_move", "Cancel"),
    ]

    def __init__(self, position: ParsedFen, renderer: PieceRenderer) -> None:
        super().__init__()
        self.renderer_controller = RendererController(renderer)
        self.controller = GameController(position)
        self.board = ChessBoard(
            position, renderer=renderer, input_mode=BoardInputMode.MOVE_ENTRY
        )
        self.status = Static("", id="status", markup=False)
        self.failure: TerminalCapabilityError | None = None
        self.flipped = False
        self._geometry_error: str | None = None

    @property
    def renderer(self) -> PieceRenderer:
        return self.renderer_controller.active

    @property
    def preferred_renderer(self) -> PieceRenderer:
        return self.renderer_controller.active

    def compose(self) -> ComposeResult:
        yield self.board
        yield self.status

    def on_mount(self) -> None:
        self._sync_view()

    def on_resize(self, event: Resize) -> None:
        try:
            renderer, geometry = self.renderer_controller.choose(
                event.size, event.pixel_size, reserved_rows=1
            )
        except TerminalCapabilityError as exc:
            self.failure = exc
            self._geometry_error = str(exc)
            self.board.unconfigure()
            self._update_status()
            return
        self.board.renderer = renderer
        self.failure = None
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

    def action_confirm_move(self) -> None:
        self.controller.confirm_move()
        self._sync_view()

    def action_cancel_move(self) -> None:
        self.controller.clear_selection()
        self._sync_view()

    def _sync_view(self) -> None:
        self.board.update_view(
            board_view_from_game(self.controller), flipped=self.flipped
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
        renderer_text = f"Renderer: {self.renderer.mode.value}"
        self.status.update(f"{renderer_text} | {text}")
