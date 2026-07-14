"""Persistent local White-flow authoring screen."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import chess
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.events import DescendantBlur, DescendantFocus, Key, Resize
from textual.screen import Screen
from textual.widgets import Button, Input, Static

from ..flow import (
    AuthorBoardController,
    ConfirmedAuthorMove,
    FlowError,
    Recommendation,
    RuleUnavailableError,
    WhiteFlowAuthor,
)
from ..input_mode import InputMode, InputModeController
from ..layout import QuizLayoutMode, choose_quiz_layout
from ..opening import (
    FixtureOpeningMoveSource,
    OpeningMove,
    OpeningMoveSource,
    OpeningSourceError,
)
from ..renderers.base import PieceRenderer
from ..renderers.colors import LABEL_COLOR, SCREEN_BACKGROUND, STATUS_BACKGROUND
from ..runtime import TerminalCapabilityError
from ..tui import ChessBoard
from ..view import BoardInputMode, BoardViewState, MoveView
from ..widgets import OpeningMovePanel
from .base import RendererController


class AuthorPhase(str, Enum):
    LOADING = "loading"
    WHITE_MOVE = "white-move"
    LOADING_BLACK_MOVES = "loading-black-moves"
    SELECT_BLACK_MOVE = "select-black-move"
    BLACK_MOVE = "black-move"
    NOTE = "note"
    CHOOSE_RULE_CHANGE = "choose-rule-change"
    SAVING = "saving"
    ERROR = "error"


class RuleDecision(str, Enum):
    DEFINE_DEFAULT = "define-default"
    DIFFERENT_FROM_DEFAULT = "different-from-default"
    DIFFERENT_FROM_EXCEPTION = "different-from-exception"


@dataclass(frozen=True, slots=True)
class PendingRuleChange:
    board_before: chess.Board
    history_before: tuple[str, ...]
    step: int
    move_san: str
    recommendation: Recommendation | None
    decision: RuleDecision


class AuthorScreen(Screen[None]):
    AUTO_FOCUS = ""
    CSS = f"""
    AuthorScreen {{ background: {SCREEN_BACKGROUND}; }}
    AuthorScreen > #author-header {{
        dock: top; height: 1; color: {LABEL_COLOR}; background: {STATUS_BACKGROUND};
        text-style: bold; padding: 0 1;
    }}
    AuthorScreen > #author-layout {{ width: 100%; height: 1fr; }}
    AuthorScreen #board-stage {{ align: center middle; }}
    AuthorScreen #author-side {{ padding: 1 2; }}
    AuthorScreen #author-panel {{ height: auto; }}
    AuthorScreen #opening-moves {{ display: none; height: auto; margin-top: 1; }}
    AuthorScreen #move-entry {{ height: 3; margin-top: 1; }}
    AuthorScreen #note {{ display: none; height: 3; margin-top: 1; }}
    AuthorScreen #decision-actions {{ display: none; height: 3; margin-top: 1; }}
    AuthorScreen #decision-actions Button {{ width: 1fr; height: 3; min-width: 12; }}
    AuthorScreen > #author-status {{
        dock: bottom; height: 1; color: {LABEL_COLOR}; background: {STATUS_BACKGROUND};
        text-align: center;
    }}
    AuthorScreen > #debug-status {{
        dock: bottom; height: 1; color: #9eaf74; background: #0d120f;
        padding: 0 1;
    }}
    AuthorScreen.layout-landscape > #author-layout {{ layout: horizontal; }}
    AuthorScreen.layout-landscape #board-stage {{ width: auto; height: 100%; }}
    AuthorScreen.layout-landscape #author-side {{
        width: 1fr; min-width: 34; height: 100%;
    }}
    AuthorScreen.layout-portrait > #author-layout {{ layout: vertical; }}
    AuthorScreen.layout-portrait #board-stage {{ width: 100%; height: auto; }}
    AuthorScreen.layout-portrait #author-side {{
        width: 100%; height: 1fr; padding: 0 2;
    }}
    AuthorScreen.layout-compact > #author-layout {{ layout: vertical; }}
    AuthorScreen.layout-compact #board-stage {{ width: 100%; height: auto; }}
    AuthorScreen.layout-compact #author-side {{
        width: 100%; height: 3; padding: 0;
    }}
    AuthorScreen.layout-compact #author-panel {{ height: 1; }}
    AuthorScreen.layout-compact #opening-moves {{ height: 1; margin: 0; }}
    AuthorScreen.layout-compact #move-entry {{ height: 1; margin: 0; border: none; }}
    AuthorScreen.layout-compact #note {{ height: 1; margin: 0; border: none; }}
    AuthorScreen.layout-compact #decision-actions {{ height: 1; margin: 0; }}
    AuthorScreen.layout-compact #decision-actions Button {{ height: 1; min-width: 8; }}
    AuthorScreen.layout-too-small > #author-layout {{ display: none; }}
    """
    BINDINGS = [
        Binding("q", "request_quit", "Quit"),
        Binding("i", "focus_available_input", "Type"),
        Binding("ctrl+r", "reload_flow", "Reload"),
        Binding("ctrl+n", "restart_line", "Restart"),
        ("enter", "confirm_move", "Confirm"),
        Binding("escape", "cancel", "Cancel", priority=True),
    ]

    def __init__(
        self,
        flow_path: Path,
        renderer: PieceRenderer,
        opening_source: OpeningMoveSource | None = None,
    ) -> None:
        super().__init__()
        self.flow_path = flow_path
        self.author = WhiteFlowAuthor(flow_path)
        start = chess.Board(self.author.flow.start_fen)
        self.controller = AuthorBoardController(start)
        self.renderer_controller = RendererController(renderer)
        self.opening_source = opening_source or FixtureOpeningMoveSource()
        self.board = ChessBoard(
            self.controller.position,
            renderer=renderer,
            input_mode=BoardInputMode.MOVE_ENTRY,
        )
        self.header = Static("", id="author-header")
        self.panel = Static("", id="author-panel", markup=False)
        self.opening_moves = OpeningMovePanel()
        self.move_input = Input(
            placeholder="Type a move in SAN, then press Enter", id="move-entry"
        )
        self.note_input = Input(placeholder="Why?", id="note")
        self.note_input.disabled = True
        self.actions = Horizontal(id="decision-actions")
        self.debug_status = Static("", id="debug-status", markup=False)
        self.status = Static("", id="author-status", markup=False)
        self.input = InputModeController()
        self.phase = AuthorPhase.LOADING
        self.layout_mode: QuizLayoutMode | None = None
        self.history: list[str] = []
        self.recommendation: Recommendation | None = None
        self.pending_change: PendingRuleChange | None = None
        self.failure: Exception | None = None
        self._geometry_error: str | None = None
        self._reload_error: str | None = None
        self._move_error: str | None = None
        self._text_value_before: str | None = None
        self._quit_confirmation = False
        self._opening_request_id = 0

    @property
    def renderer(self) -> PieceRenderer:
        return self.renderer_controller.active

    def compose(self) -> ComposeResult:
        yield self.header
        with Container(id="author-layout"):
            with Container(id="board-stage"):
                yield self.board
            with Vertical(id="author-side"):
                yield self.panel
                yield self.opening_moves
                yield self.move_input
                yield self.note_input
                with self.actions:
                    yield Button("Save default", id="save-default", variant="primary")
                    yield Button("Add exception", id="add-exception", variant="primary")
                    yield Button("Replace exception", id="replace-exception")
                    yield Button("Replace default", id="replace-default")
                    yield Button("Cancel", id="cancel")
        yield self.debug_status
        yield self.status

    def on_mount(self) -> None:
        self._restart()

    def on_resize(self, event: Resize) -> None:
        try:
            layout = choose_quiz_layout(
                event.size,
                event.pixel_size,
                self.renderer.mode,
                additional_chrome_rows=1,
                compact_panel_rows=3,
            )
        except TerminalCapabilityError as error:
            self.failure = error
            self._geometry_error = str(error)
            self.board.unconfigure()
            self.add_class("layout-too-small")
            self._update_status()
            return
        self.remove_class("layout-too-small")
        if layout.mode is not self.layout_mode:
            self._apply_layout_mode(layout.mode)
        self.board.renderer = self.renderer
        self.board.configure(layout.board_geometry)
        self._geometry_error = None
        if isinstance(self.failure, TerminalCapabilityError):
            self.failure = None
        self._update_status()

    def on_chess_board_square_hovered(self, message: ChessBoard.SquareHovered) -> None:
        self.controller.set_hover(message.square)
        self._sync_board()

    def on_chess_board_square_clicked(self, message: ChessBoard.SquareClicked) -> None:
        if self.phase in {AuthorPhase.WHITE_MOVE, AuthorPhase.BLACK_MOVE}:
            if self.input.mode is InputMode.TEXT:
                self._leave_text_mode()
            self.move_input.value = ""
            self.controller.handle_square(message.square)
            pending_san = self.controller.pending_san
            if pending_san is not None:
                self.move_input.value = pending_san
            self._sync_board()

    def on_descendant_focus(self, event: DescendantFocus) -> None:
        field = event.widget
        if isinstance(field, Input) and field in {self.move_input, self.note_input}:
            self._enter_text_mode(field)

    def on_descendant_blur(self, event: DescendantBlur) -> None:
        field = event.widget
        if (
            isinstance(field, Input)
            and field in {self.move_input, self.note_input}
            and self.input.field_blurred(field)
        ):
            self._text_value_before = None
            self._update_status()

    def on_key(self, event: Key) -> None:
        if not self.input.handles_global_shortcuts:
            return
        if self._quit_confirmation:
            return
        if event.key.lower() == "r":
            event.stop()
            self.action_restart_line()
            return
        if self.phase in {AuthorPhase.WHITE_MOVE, AuthorPhase.BLACK_MOVE}:
            return
        if self.phase not in {
            AuthorPhase.CHOOSE_RULE_CHANGE,
            AuthorPhase.ERROR,
        }:
            return
        actions = {
            "s": "save-default",
            "e": "add-exception",
            "x": "replace-exception",
            "d": "replace-default",
            "c": "cancel",
        }
        button_id = actions.get(event.key.lower())
        if button_id is None:
            return
        button = self.query_one(f"#{button_id}", Button)
        if button.display:
            event.stop()
            button.press()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input is self.note_input:
            event.stop()
            self._leave_text_mode()
            return
        if event.input is not self.move_input:
            return
        event.stop()
        move_text = event.value.strip()
        if move_text:
            self._confirm_typed_move(move_text)
        else:
            self.action_confirm_move()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input is self.move_input and self._move_error is not None:
            self._move_error = None
            self._update_status()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        action = event.button.id
        if action == "cancel":
            self.action_cancel()
        elif action == "save-default":
            self._save_default()
        elif action in {"add-exception", "replace-exception"}:
            self._save_exception()
        elif action == "replace-default":
            self._save_default()

    def on_opening_move_panel_move_submitted(
        self, message: OpeningMovePanel.MoveSubmitted
    ) -> None:
        if self.phase is AuthorPhase.SELECT_BLACK_MOVE:
            self._confirm_opening_move(message.move)

    def on_opening_move_panel_manual_requested(
        self, message: OpeningMovePanel.ManualRequested
    ) -> None:
        if self.phase is AuthorPhase.SELECT_BLACK_MOVE:
            self._enter_manual_black_turn()

    def on_opening_move_panel_text_requested(
        self, message: OpeningMovePanel.TextRequested
    ) -> None:
        if self.phase is AuthorPhase.SELECT_BLACK_MOVE:
            self._enter_manual_black_turn(text_entry=True)

    def action_focus_available_input(self) -> None:
        if not self.input.handles_global_shortcuts or self._quit_confirmation:
            return
        if self.phase in {AuthorPhase.WHITE_MOVE, AuthorPhase.BLACK_MOVE}:
            self._enter_text_mode(self.move_input)
        elif self.phase is AuthorPhase.SELECT_BLACK_MOVE:
            self._enter_manual_black_turn(text_entry=True)
        elif self.phase in {AuthorPhase.CHOOSE_RULE_CHANGE, AuthorPhase.ERROR}:
            self._enter_text_mode(self.note_input)

    def action_request_quit(self) -> None:
        if not self.input.handles_global_shortcuts:
            return
        if self._quit_confirmation:
            self.app.exit()
            return
        if self.pending_change is None:
            self.app.exit()
            return
        self._quit_confirmation = True
        self.panel.update(
            "UNSAVED RULE CHANGE\n\n[Q] Quit without saving    [Esc] Return"
        )
        self._update_status()

    def action_confirm_move(self) -> None:
        if self.phase is AuthorPhase.SELECT_BLACK_MOVE:
            self.opening_moves.submit_highlighted()
            return
        if self.phase not in {
            AuthorPhase.WHITE_MOVE,
            AuthorPhase.BLACK_MOVE,
            AuthorPhase.LOADING_BLACK_MOVES,
        }:
            return
        self._reload_error = None
        board_before = self.controller.board.copy(stack=False)
        history_before = tuple(self.history)
        confirmed = self.controller.confirm_move()
        if confirmed is None:
            return
        self._finish_confirmed_move(confirmed, board_before, history_before)

    def _confirm_opening_move(self, move: OpeningMove) -> None:
        board_before = self.controller.board.copy(stack=False)
        history_before = tuple(self.history)
        try:
            confirmed = self.controller.confirm_uci(move.uci)
        except ValueError as error:
            self.failure = error
            self._enter_manual_black_turn()
            self.panel.update(
                f"OPENING MOVE UNAVAILABLE\n\n{move.san} is no longer legal. "
                "Enter Black's move manually."
            )
            return
        self._finish_confirmed_move(confirmed, board_before, history_before)

    def _confirm_typed_move(self, move_text: str) -> None:
        if self.phase not in {AuthorPhase.WHITE_MOVE, AuthorPhase.BLACK_MOVE}:
            return
        self._reload_error = None
        board_before = self.controller.board.copy(stack=False)
        history_before = tuple(self.history)
        try:
            confirmed = self.controller.confirm_san(move_text)
        except ValueError:
            self._move_error = f"{move_text!r} is not a legal SAN move"
            self._update_status()
            return
        self._finish_confirmed_move(confirmed, board_before, history_before)

    def _finish_confirmed_move(
        self,
        confirmed: ConfirmedAuthorMove,
        board_before: chess.Board,
        history_before: tuple[str, ...],
    ) -> None:
        self._move_error = None
        self.move_input.value = ""
        if confirmed.color is chess.BLACK:
            try:
                self.author.record_opponent_reply(
                    board_before,
                    history_before,
                    confirmed.san,
                )
            except FlowError as error:
                self.controller.reset(board_before)
                self.history = list(history_before)
                self.failure = error
                self._enter_manual_black_turn()
                self.panel.update(
                    f"BRANCH SAVE FAILED\n\n{error}\n\n"
                    "The move was not applied; retry after fixing the flow file."
                )
                self._sync_board()
                return
        self.history.append(confirmed.san)
        self._sync_board()
        if confirmed.color is chess.BLACK:
            self.failure = None
            self._enter_white_turn()
            return

        step = (len(history_before) // 2) + 1
        recommendation = self.recommendation
        matches = False
        if recommendation is not None:
            try:
                expected = board_before.parse_san(recommendation.move_san)
                matches = expected.uci() == confirmed.move.uci
            except ValueError:
                matches = False
        if matches:
            self.pending_change = None
            self._enter_black_turn()
            return

        if recommendation is None:
            decision = RuleDecision.DEFINE_DEFAULT
        elif recommendation.source == "default":
            decision = RuleDecision.DIFFERENT_FROM_DEFAULT
        else:
            decision = RuleDecision.DIFFERENT_FROM_EXCEPTION
        self.pending_change = PendingRuleChange(
            board_before,
            history_before,
            step,
            confirmed.san,
            recommendation,
            decision,
        )
        self._show_rule_decision()

    def action_cancel(self) -> None:
        if self.input.mode is InputMode.TEXT:
            self._leave_text_mode(restore=True)
            return
        if self._quit_confirmation:
            self._quit_confirmation = False
            self._refresh_panel()
            self._update_status()
            return
        self._reload_error = None
        pending = self.pending_change
        if pending is not None:
            self.controller.reset(pending.board_before)
            self.history = list(pending.history_before)
            self.pending_change = None
            self.note_input.value = ""
            self._enter_white_turn()
        else:
            self.controller.clear_selection()
            self.move_input.value = ""
            self._sync_board()

    def action_restart_line(self) -> None:
        if not self.input.handles_global_shortcuts:
            return
        self._restart()

    def action_reload_flow(self) -> None:
        if not self.input.handles_global_shortcuts:
            return
        try:
            self.author.reload()
        except FlowError as error:
            self.failure = error
            self._reload_error = f"FLOW RELOAD FAILED\n\n{error}"
            self._refresh_panel()
            self._update_status()
            return
        self.failure = None
        self._reload_error = None
        self._refresh_turn()

    def _restart(self) -> None:
        self._opening_request_id += 1
        self._leave_text_mode()
        self.controller.reset(chess.Board(self.author.flow.start_fen))
        self.history.clear()
        self.pending_change = None
        self.move_input.value = ""
        self.note_input.value = ""
        self._reload_error = None
        self._move_error = None
        self._quit_confirmation = False
        self._enter_white_turn()

    def _enter_white_turn(self) -> None:
        self.phase = AuthorPhase.WHITE_MOVE
        self.pending_change = None
        step = (len(self.history) // 2) + 1
        try:
            self.recommendation = self.author.recommend(self.controller.board, step)
            self.failure = None
        except RuleUnavailableError as error:
            self.recommendation = error.recommendation
            self.failure = error
        self._hide_opening_moves()
        self._hide_decision()
        self._refresh_panel()
        self._sync_board()

    def _enter_black_turn(self) -> None:
        self.phase = AuthorPhase.LOADING_BLACK_MOVES
        self.recommendation = None
        self._hide_decision()
        self._hide_opening_moves()
        self.move_input.display = False
        self.move_input.disabled = True
        self._opening_request_id += 1
        request_id = self._opening_request_id
        self._refresh_panel()
        self._sync_board()
        board = self.controller.board.copy(stack=False)
        self.run_worker(
            self._load_black_moves(request_id, board),
            name="load-black-opening-moves",
            group="opening-moves",
            exclusive=True,
        )

    async def _load_black_moves(self, request_id: int, board: chess.Board) -> None:
        try:
            moves = await self.opening_source.moves_for(board)
        except OpeningSourceError as error:
            if not self._black_move_request_is_current(request_id, board):
                return
            self.failure = error
            self._enter_manual_black_turn()
            self.panel.update(
                f"OPENING DATA UNAVAILABLE\n\n{error}\n\n"
                "Enter Black's move manually."
            )
            return
        if not self._black_move_request_is_current(request_id, board):
            return
        if not moves:
            self._enter_manual_black_turn()
            return
        self.failure = None
        self.phase = AuthorPhase.SELECT_BLACK_MOVE
        self.opening_moves.set_moves(
            moves[:4],
            context=f"After {_format_history(tuple(self.history))}:",
        )
        self.opening_moves.display = True
        self.move_input.display = False
        self.move_input.disabled = True
        self.panel.update("")
        self.opening_moves.focus()
        self._update_status()

    def _black_move_request_is_current(
        self, request_id: int, board: chess.Board
    ) -> bool:
        return (
            request_id == self._opening_request_id
            and self.phase is AuthorPhase.LOADING_BLACK_MOVES
            and self.controller.board.fen(en_passant="fen")
            == board.fen(en_passant="fen")
        )

    def _enter_manual_black_turn(self, *, text_entry: bool = False) -> None:
        self._opening_request_id += 1
        self.phase = AuthorPhase.BLACK_MOVE
        self.recommendation = None
        self._hide_opening_moves()
        self._hide_decision()
        self._refresh_panel()
        self._sync_board()
        if text_entry:
            self._enter_text_mode(self.move_input)

    def _hide_opening_moves(self) -> None:
        if self.opening_moves.has_focus:
            self.set_focus(None)
        self.opening_moves.display = False
        self.opening_moves.clear()

    def _show_rule_decision(self) -> None:
        self.phase = AuthorPhase.CHOOSE_RULE_CHANGE
        self._hide_opening_moves()
        self.move_input.display = False
        self.move_input.disabled = True
        self.note_input.disabled = False
        self.note_input.display = True
        self.actions.display = True
        pending = self.pending_change
        assert pending is not None
        self._set_button_available(
            "save-default", pending.decision is RuleDecision.DEFINE_DEFAULT
        )
        self._set_button_available(
            "add-exception", pending.decision is RuleDecision.DIFFERENT_FROM_DEFAULT
        )
        self._set_button_available(
            "replace-exception",
            pending.decision is RuleDecision.DIFFERENT_FROM_EXCEPTION,
        )
        self._set_button_available(
            "replace-default", pending.decision is not RuleDecision.DEFINE_DEFAULT
        )
        self._set_button_available("cancel", True)
        self._enter_text_mode(self.note_input)
        self._refresh_panel()
        self._update_status()

    def _hide_decision(self) -> None:
        self._leave_text_mode()
        self.note_input.display = False
        self.note_input.disabled = True
        self.actions.display = False
        for button in self.actions.query(Button):
            button.disabled = True
        self.move_input.display = True
        self.move_input.disabled = False

    def _enter_text_mode(self, field: Input) -> None:
        if self.input.active_field is not field:
            self._text_value_before = field.value
        self.input.enter_text(field)
        self._update_status()

    def _leave_text_mode(self, *, restore: bool = False) -> None:
        field = self.input.active_field
        if restore and isinstance(field, Input) and self._text_value_before is not None:
            field.value = self._text_value_before
        self.input.leave_text()
        self._text_value_before = None
        self._move_error = None
        if self.is_mounted:
            self._update_status()

    def _set_button_available(self, button_id: str, available: bool) -> None:
        button = self.query_one(f"#{button_id}", Button)
        button.display = available
        button.disabled = not available

    def _save_default(self) -> None:
        pending = self.pending_change
        if pending is None:
            return
        self.phase = AuthorPhase.SAVING
        try:
            self.author.replace_default(
                pending.board_before,
                pending.step,
                pending.move_san,
                self.note_input.value.strip() or None,
            )
        except FlowError as error:
            self._show_save_error(error)
            return
        self._finish_save()

    def _save_exception(self) -> None:
        pending = self.pending_change
        if pending is None:
            return
        self.phase = AuthorPhase.SAVING
        try:
            self.author.add_exception(
                pending.board_before,
                pending.step,
                pending.history_before,
                pending.move_san,
                self.note_input.value.strip() or None,
            )
        except FlowError as error:
            self._show_save_error(error)
            return
        self._finish_save()

    def _finish_save(self) -> None:
        self.pending_change = None
        self.note_input.value = ""
        self.failure = None
        self._enter_black_turn()

    def _show_save_error(self, error: FlowError) -> None:
        self.failure = error
        self.phase = AuthorPhase.ERROR
        self.panel.update(f"SAVE FAILED\n\n{error}\n\n[C] Cancel")
        self._update_status()

    def _refresh_turn(self) -> None:
        if self.controller.board.turn is chess.WHITE:
            self._enter_white_turn()
        else:
            self._enter_black_turn()

    def _refresh_panel(self) -> None:
        if self._reload_error is not None:
            self.panel.update(
                f"{self._reload_error}\n\nThe current in-memory flow remains active."
            )
            return
        if self.phase is AuthorPhase.LOADING_BLACK_MOVES:
            self.panel.update("BLACK RESPONSE\n\nLoading common opening moves...")
            return
        if self.phase is AuthorPhase.SELECT_BLACK_MOVE:
            self.panel.update("")
            return
        if self.phase is AuthorPhase.BLACK_MOVE:
            self.panel.update(
                "CHOOSE BLACK'S RESPONSE TO EXPLORE\n\n"
                "Play any legal Black move on the board."
            )
            return
        if self.phase is AuthorPhase.CHOOSE_RULE_CHANGE:
            self.panel.update(self._decision_text())
            return
        step = (len(self.history) // 2) + 1
        recommendation = self.recommendation
        if isinstance(self.failure, RuleUnavailableError):
            self.panel.update(str(self.failure))
        elif recommendation is None:
            self.panel.update(
                f"FLOW FRONTIER\n\nNo default move exists for White step {step}.\n\n"
                "Play a move to define it."
            )
        else:
            source = (
                f"Exception {recommendation.exception_id}"
                if recommendation.source == "exception"
                else f"Default step {step}"
            )
            note = f"\n\n{recommendation.note}" if recommendation.note else ""
            self.panel.update(
                f"WHITE STEP {step}\n\nRecommended: {recommendation.move_san}\n"
                f"Source: {source}{note}\n\nPlay White's move on the board."
            )

    def _decision_text(self) -> str:
        pending = self.pending_change
        assert pending is not None
        if pending.decision is RuleDecision.DEFINE_DEFAULT:
            return (
                f"DEFINE DEFAULT STEP {pending.step}\n\nMove: {pending.move_san}\n\n"
                "Add an optional note, then save or cancel."
            )
        recommendation = pending.recommendation
        assert recommendation is not None
        source = recommendation.source.upper()
        return (
            f"YOUR MOVE DIFFERS FROM THE {source}\n\n"
            f"You played: {pending.move_san}\n"
            f"Saved move: {recommendation.move_san}\n\n"
            "Add an exception for this exact position or replace the numbered default."
        )

    def _sync_board(self) -> None:
        interaction = self.controller.interaction
        self.board.update_view(
            BoardViewState(
                position=self.controller.position,
                selected_square=interaction.selected_square,
                quiet_targets=interaction.quiet_targets,
                capture_targets=interaction.capture_targets,
                pending_move=(
                    MoveView(
                        interaction.pending_move.from_square,
                        interaction.pending_move.to_square,
                    )
                    if interaction.pending_move is not None
                    else None
                ),
                hover_square=interaction.hover_square,
                last_move=(
                    MoveView(
                        interaction.last_move.from_square,
                        interaction.last_move.to_square,
                    )
                    if interaction.last_move is not None
                    else None
                ),
                checked_king=interaction.checked_king,
            ),
            flipped=False,
        )
        self._refresh_header()
        self._update_status()

    def _refresh_header(self) -> None:
        line = " ".join(self.history) if self.history else "Starting position"
        self.header.update(f"{self.author.flow.name.upper()}    {line}")

    def _update_status(self) -> None:
        self._update_debug_status()
        if self._geometry_error is not None:
            self.status.update(self._geometry_error.replace("\n", " "))
            return
        if self._quit_confirmation:
            self.status.update("[NAV] Q QUIT WITHOUT SAVING · ESC RETURN")
            return
        if self._move_error is not None:
            self.status.update(
                f"[TEXT: MOVE] INVALID MOVE: {self._move_error} · ESC CANCEL"
            )
            return
        if self.input.mode is InputMode.TEXT:
            if self.input.active_field is self.note_input:
                self.status.update("[TEXT: NOTE] TYPE NOTE · ENTER DONE · ESC CANCEL")
            else:
                self.status.update("[TEXT: MOVE] TYPE SAN · ENTER SUBMIT · ESC CANCEL")
            return
        instructions = {
            AuthorPhase.WHITE_MOVE: "PLAY WHITE · I TYPE SAN · ENTER CONFIRM",
            AuthorPhase.LOADING_BLACK_MOVES: "LOADING BLACK RESPONSES",
            AuthorPhase.SELECT_BLACK_MOVE: (
                "UP/DOWN OR A/S/D/F SELECT · ENTER PLAY · M MANUAL · I TYPE SAN"
            ),
            AuthorPhase.BLACK_MOVE: "PLAY BLACK · I TYPE SAN · ENTER CONFIRM",
            AuthorPhase.CHOOSE_RULE_CHANGE: "CHOOSE RULE CHANGE · I EDIT NOTE",
            AuthorPhase.SAVING: "SAVING",
            AuthorPhase.ERROR: "C CANCEL",
            AuthorPhase.LOADING: "LOADING",
            AuthorPhase.NOTE: "ENTER NOTE",
        }[self.phase]
        self.status.update(f"[NAV] {instructions} · R RESTART · CTRL+R RELOAD · Q QUIT")

    def _update_debug_status(self) -> None:
        turn = "white" if self.controller.board.turn is chess.WHITE else "black"
        white_step = (len(self.history) // 2) + 1
        if self.pending_change is not None:
            rule = f"pending:{self.pending_change.decision.value}"
        elif self.recommendation is not None:
            rule = f"{self.recommendation.source}:{self.recommendation.move_san}"
        else:
            rule = "none"
        error = type(self.failure).__name__ if self.failure is not None else "none"
        self.debug_status.update(
            f"phase={self.phase.value} | input={self.input.mode.value} | "
            f"turn={turn} | white_step={white_step} | ply={len(self.history)} | "
            f"rule={rule} | error={error}"
        )

    def _apply_layout_mode(self, mode: QuizLayoutMode) -> None:
        for class_name in ("layout-landscape", "layout-portrait", "layout-compact"):
            self.remove_class(class_name)
        self.add_class(f"layout-{mode.value}")
        self.layout_mode = mode


def _format_history(history: tuple[str, ...]) -> str:
    parts: list[str] = []
    for index, san in enumerate(history):
        if index % 2 == 0:
            parts.append(f"{(index // 2) + 1}. {san}")
        else:
            parts.append(san)
    return " ".join(parts)
