"""Unified test-first flow screen with inline editing."""

from __future__ import annotations

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
    AttemptResult,
    FlowError,
    FlowWorkspace,
    Recommendation,
    WhiteMoveAttempt,
    WhiteTurn,
)
from ..engine import (
    DEFAULT_QUALITY_THRESHOLDS,
    ChessEngineService,
    EngineError,
    MoveAssessment,
    QualityThresholds,
    assess_white_move,
)
from ..input_mode import InputMode, InputModeController
from ..layout import QuizLayoutMode, choose_quiz_layout
from ..opening import MoveSuggestion, OpeningSourceError, OpponentMovePlanner
from ..renderers.base import PieceRenderer
from ..renderers.colors import LABEL_COLOR, SCREEN_BACKGROUND, STATUS_BACKGROUND
from ..runtime import TerminalCapabilityError
from ..tui import ChessBoard
from ..view import BoardInputMode, BoardViewState, MoveView
from ..widgets import MoveSuggestionPanel
from .base import RendererController


class FlowPhase(str, Enum):
    LOADING = "loading"
    WHITE_TEST = "white-test"
    WHITE_RESULT_CORRECT = "white-result-correct"
    WHITE_RESULT_MISMATCH = "white-result-mismatch"
    BLACK_LOADING = "black-loading"
    BLACK_SELECT = "black-select"
    BLACK_ENGINE_ERROR = "black-engine-error"
    BLACK_MANUAL = "black-manual"
    GAME_OVER = "game-over"
    FRONTIER_MOVE = "frontier-move"
    RULE_NOTE = "rule-note"
    SAVING = "saving"
    ERROR = "error"


class RuleNoteAction(str, Enum):
    SAVE_DEFAULT = "save-default"
    SAVE_EXCEPTION = "save-exception"
    EDIT_SAVED_NOTE = "edit-saved-note"


class AuthorScreen(Screen[None]):
    """Run, test, and edit one persistent White flow."""

    AUTO_FOCUS = ""
    CORRECT_FEEDBACK_SECONDS = 0.35
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
    AuthorScreen #move-suggestions {{ display: none; height: auto; margin-top: 1; }}
    AuthorScreen #move-entry {{ display: none; height: 3; margin-top: 1; }}
    AuthorScreen #note {{ display: none; height: 3; margin-top: 1; }}
    AuthorScreen #decision-actions {{ display: none; height: auto; margin-top: 1; }}
    AuthorScreen #decision-actions Button {{ width: 1fr; height: 3; min-width: 10; }}
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
    AuthorScreen.layout-compact #move-suggestions {{ height: 1; margin: 0; }}
    AuthorScreen.layout-compact #move-entry {{ height: 1; margin: 0; border: none; }}
    AuthorScreen.layout-compact #note {{ height: 1; margin: 0; border: none; }}
    AuthorScreen.layout-compact #decision-actions {{ height: 1; margin: 0; }}
    AuthorScreen.layout-compact #decision-actions Button {{
        height: 1; min-width: 7;
    }}
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
        opponent_planner: OpponentMovePlanner,
        *,
        analysis_engine: ChessEngineService | None = None,
        analysis_engine_owned_by_planner: bool = False,
        quality_thresholds: QualityThresholds | None = None,
    ) -> None:
        super().__init__()
        self.flow_path = flow_path
        self.workspace = FlowWorkspace(flow_path)
        self.author = self.workspace.author
        self.controller = self.workspace.controller
        self.history = self.workspace.history
        self.renderer_controller = RendererController(renderer)
        self.opponent_planner = opponent_planner
        self.analysis_engine = analysis_engine
        self.analysis_engine_owned_by_planner = analysis_engine_owned_by_planner
        self.quality_thresholds = quality_thresholds or DEFAULT_QUALITY_THRESHOLDS
        self.board = ChessBoard(
            self.controller.position,
            renderer=renderer,
            input_mode=BoardInputMode.MOVE_ENTRY,
        )
        self.header = Static("", id="author-header")
        self.panel = Static("", id="author-panel", markup=False)
        self.move_suggestions = MoveSuggestionPanel()
        self.move_input = Input(
            placeholder="Type a move in SAN, then press Enter", id="move-entry"
        )
        self.note_input = Input(placeholder="Why?", id="note")
        self.note_input.disabled = True
        self.actions = Horizontal(id="decision-actions")
        self.debug_status = Static("", id="debug-status", markup=False)
        self.status = Static("", id="author-status", markup=False)
        self.input = InputModeController()
        self.phase = FlowPhase.LOADING
        self.layout_mode: QuizLayoutMode | None = None
        self.failure: Exception | None = None
        self._geometry_error: str | None = None
        self._reload_error: str | None = None
        self._move_error: str | None = None
        self._text_value_before: str | None = None
        self._quit_confirmation = False
        self._suggestion_request_id = 0
        self._note_action: RuleNoteAction | None = None
        self._note_return_phase: FlowPhase | None = None
        self._assessment: MoveAssessment | None = None
        self._assessment_error: EngineError | None = None
        self._assessment_loading = False
        self._assessment_request_id = 0

    @property
    def renderer(self) -> PieceRenderer:
        return self.renderer_controller.active

    @property
    def recommendation(self) -> Recommendation | None:
        attempt = self.workspace.attempt
        if attempt is not None:
            return attempt.recommendation
        turn = self.workspace.white_turn
        return turn.recommendation if turn is not None else None

    def compose(self) -> ComposeResult:
        yield self.header
        with Container(id="author-layout"):
            with Container(id="board-stage"):
                yield self.board
            with Vertical(id="author-side"):
                yield self.panel
                yield self.move_suggestions
                yield self.move_input
                yield self.note_input
                with self.actions:
                    yield Button("Retry", id="retry")
                    yield Button("Keep rule", id="keep-rule", variant="primary")
                    yield Button("Save default", id="save-default", variant="primary")
                    yield Button("Add exception", id="add-exception", variant="primary")
                    yield Button("Replace exception", id="replace-exception")
                    yield Button("Replace default", id="replace-default")
                    yield Button("Save note", id="save-note")
                    yield Button("Edit note", id="edit-note")
                    yield Button("Delete exception", id="delete-exception")
                    yield Button("Cancel", id="cancel")
        yield self.debug_status
        yield self.status

    def on_mount(self) -> None:
        self._restart()

    async def on_unmount(self) -> None:
        try:
            await self.opponent_planner.close()
        finally:
            if (
                self.analysis_engine is not None
                and not self.analysis_engine_owned_by_planner
            ):
                await self.analysis_engine.close()

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
        if self.phase not in {
            FlowPhase.WHITE_TEST,
            FlowPhase.FRONTIER_MOVE,
            FlowPhase.BLACK_MANUAL,
        }:
            return
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
        if not self.input.handles_global_shortcuts or self._quit_confirmation:
            return
        key = event.key.lower()
        if self.phase is FlowPhase.BLACK_ENGINE_ERROR:
            if key == "m":
                event.stop()
                self._enter_manual_black_turn()
            elif key == "i":
                event.stop()
                self._enter_manual_black_turn(text_entry=True)
            elif key == "r":
                event.stop()
                self._retry_engine()
            return
        if self.phase is FlowPhase.WHITE_RESULT_MISMATCH:
            actions = {
                "r": "retry",
                "e": "add-exception",
                "d": "replace-default",
                "x": "replace-exception",
                "n": "edit-note",
                "delete": "delete-exception",
            }
            button_id = actions.get(key)
            if button_id is not None:
                button = self.query_one(f"#{button_id}", Button)
                if button.display:
                    event.stop()
                    button.press()
            return
        if self.phase is FlowPhase.RULE_NOTE and key == "s":
            event.stop()
            self._save_rule_note()
            return
        if key == "r":
            event.stop()
            self.action_restart_line()

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
        if action == "retry":
            self._retry_white_move()
        elif action == "keep-rule":
            self._keep_saved_rule()
        elif action == "add-exception":
            if self.phase is FlowPhase.RULE_NOTE:
                self._save_rule_note()
            else:
                self._start_rule_note(RuleNoteAction.SAVE_EXCEPTION)
        elif action == "replace-exception":
            self._start_rule_note(RuleNoteAction.SAVE_EXCEPTION, retain_note=True)
        elif action == "replace-default":
            self._start_rule_note(RuleNoteAction.SAVE_DEFAULT, retain_note=True)
        elif action == "edit-note":
            self._start_rule_note(RuleNoteAction.EDIT_SAVED_NOTE, retain_note=True)
        elif action in {"save-default", "save-note"}:
            self._save_rule_note()
        elif action == "delete-exception":
            self._delete_exception_and_continue()
        elif action == "cancel":
            self.action_cancel()

    def on_move_suggestion_panel_suggestion_submitted(
        self, message: MoveSuggestionPanel.SuggestionSubmitted
    ) -> None:
        if self.phase is FlowPhase.BLACK_SELECT:
            self._confirm_suggestion(message.suggestion)

    def on_move_suggestion_panel_manual_requested(
        self, message: MoveSuggestionPanel.ManualRequested
    ) -> None:
        if self.phase is FlowPhase.BLACK_SELECT:
            self._enter_manual_black_turn()

    def on_move_suggestion_panel_text_requested(
        self, message: MoveSuggestionPanel.TextRequested
    ) -> None:
        if self.phase is FlowPhase.BLACK_SELECT:
            self._enter_manual_black_turn(text_entry=True)

    def action_focus_available_input(self) -> None:
        if not self.input.handles_global_shortcuts or self._quit_confirmation:
            return
        if self.phase in {
            FlowPhase.WHITE_TEST,
            FlowPhase.FRONTIER_MOVE,
            FlowPhase.BLACK_MANUAL,
        }:
            self._enter_text_mode(self.move_input)
        elif self.phase is FlowPhase.BLACK_SELECT:
            self._enter_manual_black_turn(text_entry=True)
        elif self.phase is FlowPhase.BLACK_ENGINE_ERROR:
            self._enter_manual_black_turn(text_entry=True)
        elif self.phase in {FlowPhase.RULE_NOTE, FlowPhase.ERROR}:
            self._enter_text_mode(self.note_input)

    def action_request_quit(self) -> None:
        if not self.input.handles_global_shortcuts:
            return
        if self._quit_confirmation:
            self.app.exit()
            return
        if self.phase not in {
            FlowPhase.WHITE_RESULT_MISMATCH,
            FlowPhase.RULE_NOTE,
            FlowPhase.ERROR,
        }:
            self.app.exit()
            return
        self._quit_confirmation = True
        self.panel.update("UNFINISHED FLOW EDIT\n\n[Q] Quit    [Esc] Return")
        self._update_status()

    def action_confirm_move(self) -> None:
        if self.phase is FlowPhase.WHITE_RESULT_CORRECT:
            self._continue_after_correct()
            return
        if self.phase is FlowPhase.WHITE_RESULT_MISMATCH:
            self._keep_saved_rule()
            return
        if self.phase is FlowPhase.RULE_NOTE:
            self._save_rule_note()
            return
        if self.phase is FlowPhase.BLACK_SELECT:
            self.move_suggestions.submit_highlighted()
            return
        if self.phase in {FlowPhase.WHITE_TEST, FlowPhase.FRONTIER_MOVE}:
            attempt = self.workspace.submit_pending_white_move()
            if attempt is not None:
                self._handle_white_attempt(attempt)
            return
        if self.phase is FlowPhase.BLACK_MANUAL:
            try:
                confirmed = self.workspace.submit_pending_black_move()
            except FlowError as error:
                self._show_black_save_error(error)
                return
            if confirmed is not None:
                self._finish_black_move()

    def _confirm_typed_move(self, move_text: str) -> None:
        self._reload_error = None
        try:
            if self.phase in {FlowPhase.WHITE_TEST, FlowPhase.FRONTIER_MOVE}:
                attempt = self.workspace.submit_white_san(move_text)
                self._handle_white_attempt(attempt)
            elif self.phase is FlowPhase.BLACK_MANUAL:
                self.workspace.submit_black_san(move_text)
                self._finish_black_move()
        except ValueError:
            self._move_error = f"{move_text!r} is not a legal SAN move"
            self._update_status()
        except FlowError as error:
            self._show_black_save_error(error)

    def _handle_white_attempt(self, attempt: WhiteMoveAttempt) -> None:
        self._move_error = None
        self.move_input.value = ""
        self._sync_board()
        if self.workspace.outcome is not None:
            self._enter_game_over()
            return
        if attempt.result is AttemptResult.CORRECT:
            self.phase = FlowPhase.WHITE_RESULT_CORRECT
            self._hide_interaction_controls()
            self._refresh_panel()
            self._update_status()
            self.set_timer(
                self.CORRECT_FEEDBACK_SECONDS,
                self._continue_after_correct,
            )
        elif attempt.result in {
            AttemptResult.FRONTIER,
            AttemptResult.RULE_UNAVAILABLE,
        }:
            action = (
                RuleNoteAction.SAVE_DEFAULT
                if attempt.result is AttemptResult.FRONTIER
                else RuleNoteAction.SAVE_EXCEPTION
            )
            self._start_rule_note(action)
        else:
            self.phase = FlowPhase.WHITE_RESULT_MISMATCH
            self._start_engine_review(attempt)
            self._show_mismatch_controls()
            self._refresh_panel()
            self._update_status()

    def _continue_after_correct(self) -> None:
        if self.phase is not FlowPhase.WHITE_RESULT_CORRECT:
            return
        try:
            self.workspace.complete_correct_move()
        except FlowError as error:
            self._show_save_error(error)
            return
        self._enter_black_turn()

    def _retry_white_move(self) -> None:
        try:
            turn = self.workspace.retry_white_move()
        except FlowError as error:
            self._show_save_error(error)
            return
        self.note_input.value = ""
        self._enter_white_turn(turn)

    def _keep_saved_rule(self) -> None:
        try:
            self.workspace.keep_saved_rule()
        except FlowError as error:
            self._show_save_error(error)
            return
        self._sync_board()
        self._enter_black_turn()

    def _delete_exception_and_continue(self) -> None:
        try:
            self.workspace.remove_exception_and_keep_default()
        except FlowError as error:
            self._show_save_error(error)
            return
        self._sync_board()
        self._enter_black_turn()

    def _start_rule_note(
        self,
        action: RuleNoteAction,
        *,
        retain_note: bool = False,
    ) -> None:
        attempt = self.workspace.attempt
        if attempt is None:
            return
        self._note_action = action
        self._note_return_phase = (
            FlowPhase.WHITE_RESULT_MISMATCH
            if attempt.result
            in {AttemptResult.MISMATCH_DEFAULT, AttemptResult.MISMATCH_EXCEPTION}
            else FlowPhase.FRONTIER_MOVE
        )
        self.phase = FlowPhase.RULE_NOTE
        if retain_note and attempt.recommendation is not None:
            self.note_input.value = attempt.recommendation.note or ""
        else:
            self.note_input.value = ""
        self._hide_move_suggestions()
        self._hide_interaction_controls()
        self.note_input.display = True
        self.note_input.disabled = False
        self.actions.display = True
        self._set_button_available(
            "save-default", action is RuleNoteAction.SAVE_DEFAULT
        )
        self._set_button_available(
            "add-exception", action is RuleNoteAction.SAVE_EXCEPTION
        )
        self._set_button_available(
            "save-note", action is RuleNoteAction.EDIT_SAVED_NOTE
        )
        self._set_button_available("cancel", True)
        self._enter_text_mode(self.note_input)
        self._refresh_panel()
        self._update_status()

    def _save_rule_note(self) -> None:
        action = self._note_action
        if action is None or self.workspace.attempt is None:
            return
        self.phase = FlowPhase.SAVING
        note = self.note_input.value.strip() or None
        try:
            if action is RuleNoteAction.SAVE_DEFAULT:
                self.workspace.save_selected_default(note)
            elif action is RuleNoteAction.SAVE_EXCEPTION:
                self.workspace.save_selected_exception(note)
            else:
                self.workspace.edit_saved_note(note)
        except FlowError as error:
            self._show_save_error(error)
            return
        self._clear_failure()
        self.note_input.value = ""
        if action is RuleNoteAction.EDIT_SAVED_NOTE:
            self.phase = FlowPhase.WHITE_RESULT_MISMATCH
            self._note_action = None
            self._show_mismatch_controls()
            self._refresh_panel()
            self._update_status()
        else:
            self._note_action = None
            self._enter_black_turn()

    def _confirm_suggestion(self, suggestion: MoveSuggestion) -> None:
        try:
            self.workspace.submit_black_uci(suggestion.uci)
        except ValueError:
            self.failure = ValueError(
                f"Suggested move {suggestion.san} is no longer legal."
            )
            self._enter_manual_black_turn()
            self.panel.update(
                f"SUGGESTED MOVE UNAVAILABLE\n\n{suggestion.san} is no longer legal. "
                "Enter Black's move manually."
            )
            return
        except FlowError as error:
            self._show_black_save_error(error)
            return
        self._finish_black_move()

    def _finish_black_move(self) -> None:
        self._clear_failure()
        self._move_error = None
        self.move_input.value = ""
        self._sync_board()
        if self.workspace.outcome is not None:
            self._enter_game_over()
        else:
            self._enter_white_turn()

    def action_cancel(self) -> None:
        if self.input.mode is InputMode.TEXT:
            self._leave_text_mode(restore=True)
            return
        if self._quit_confirmation:
            self._quit_confirmation = False
            self._refresh_panel()
            self._update_status()
            return
        if self.phase is FlowPhase.WHITE_RESULT_MISMATCH:
            self._retry_white_move()
            return
        if self.phase is FlowPhase.RULE_NOTE:
            if self._note_return_phase is FlowPhase.WHITE_RESULT_MISMATCH:
                self.phase = FlowPhase.WHITE_RESULT_MISMATCH
                self._note_action = None
                self._show_mismatch_controls()
                self._refresh_panel()
                self._update_status()
            else:
                self._retry_white_move()
            return
        if self.phase is FlowPhase.ERROR and self.workspace.attempt is not None:
            self.phase = FlowPhase.RULE_NOTE
            self._refresh_panel()
            self._update_status()
            return
        self.controller.clear_selection()
        self.move_input.value = ""
        self._sync_board()

    def action_restart_line(self) -> None:
        if self.input.handles_global_shortcuts:
            self._restart()

    def action_reload_flow(self) -> None:
        if not self.input.handles_global_shortcuts:
            return
        try:
            turn = self.workspace.reload()
        except FlowError as error:
            self.failure = error
            self._reload_error = f"FLOW RELOAD FAILED\n\n{error}"
            self._refresh_panel()
            self._update_status()
            return
        self._clear_failure()
        self._reload_error = None
        if turn is not None:
            self._enter_white_turn(turn)
        else:
            self._enter_black_turn()

    def _restart(self) -> None:
        self._suggestion_request_id += 1
        self._leave_text_mode()
        self.workspace.restart_position()
        self.move_input.value = ""
        self.note_input.value = ""
        self._reload_error = None
        self._move_error = None
        self._quit_confirmation = False
        self._note_action = None
        if self.workspace.outcome is not None:
            self._enter_game_over()
        else:
            self._enter_white_turn(self.workspace.begin_white_turn())

    def _enter_white_turn(self, turn: WhiteTurn | None = None) -> None:
        if self.workspace.outcome is not None:
            self._enter_game_over()
            return
        turn = turn or self.workspace.begin_white_turn()
        self.phase = (
            FlowPhase.FRONTIER_MOVE
            if turn.recommendation is None or turn.unavailable_reason is not None
            else FlowPhase.WHITE_TEST
        )
        self._hide_move_suggestions()
        self._hide_interaction_controls()
        self.move_input.display = True
        self.move_input.disabled = False
        self._refresh_panel()
        self._sync_board()

    def _enter_black_turn(self) -> None:
        if self.workspace.outcome is not None:
            self._enter_game_over()
            return
        self.phase = FlowPhase.BLACK_LOADING
        self._hide_interaction_controls()
        self._hide_move_suggestions()
        self._suggestion_request_id += 1
        request_id = self._suggestion_request_id
        self._refresh_panel()
        self._sync_board()
        board = self.controller.board.copy(stack=False)
        self.run_worker(
            self._load_black_moves(request_id, board),
            name="load-opponent-suggestions",
            group="opponent-suggestions",
            exclusive=True,
        )

    async def _load_black_moves(self, request_id: int, board: chess.Board) -> None:
        try:
            suggestions = await self.opponent_planner.suggestions_for(board)
        except EngineError as error:
            if not self._black_move_request_is_current(request_id, board):
                return
            self._show_engine_error(error)
            return
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
        if not suggestions:
            self._enter_manual_black_turn()
            return
        self._clear_failure()
        self.phase = FlowPhase.BLACK_SELECT
        explored = frozenset(
            reply.move_san
            for reply in self.author.flow.opponent_replies
            if reply.after_san == tuple(self.history)
        )
        self.move_suggestions.set_suggestions(
            suggestions,
            context=f"After {_format_history(tuple(self.history))}:",
            explored_sans=explored,
        )
        self.move_suggestions.display = True
        self.panel.update("")
        self.move_suggestions.focus()
        self._update_status()

    def _show_engine_error(self, error: EngineError) -> None:
        self._suggestion_request_id += 1
        self.failure = error
        self.phase = FlowPhase.BLACK_ENGINE_ERROR
        self._hide_move_suggestions()
        self._hide_interaction_controls()
        self.panel.update(
            f"ENGINE SUGGESTION FAILED\n\n{error}\n\n"
            "[M] Enter Black move manually\n"
            "[I] Type Black SAN\n"
            "[R] Retry engine"
        )
        self._sync_board()

    def _retry_engine(self) -> None:
        if self.phase is FlowPhase.BLACK_ENGINE_ERROR:
            self._enter_black_turn()

    def _enter_game_over(self) -> None:
        outcome = self.workspace.outcome
        if outcome is None:
            return
        self._suggestion_request_id += 1
        self.phase = FlowPhase.GAME_OVER
        self._hide_move_suggestions()
        self._hide_interaction_controls()
        self._clear_failure()
        self.panel.update(_format_game_over(outcome))
        self._sync_board()

    def _black_move_request_is_current(
        self, request_id: int, board: chess.Board
    ) -> bool:
        return (
            request_id == self._suggestion_request_id
            and self.phase is FlowPhase.BLACK_LOADING
            and self.controller.board.fen(en_passant="fen")
            == board.fen(en_passant="fen")
        )

    def _enter_manual_black_turn(self, *, text_entry: bool = False) -> None:
        self._suggestion_request_id += 1
        self.phase = FlowPhase.BLACK_MANUAL
        self._hide_move_suggestions()
        self._hide_interaction_controls()
        self.move_input.display = True
        self.move_input.disabled = False
        self._refresh_panel()
        self._sync_board()
        if text_entry:
            self._enter_text_mode(self.move_input)

    def _show_mismatch_controls(self) -> None:
        attempt = self.workspace.attempt
        assert attempt is not None
        self._hide_move_suggestions()
        self._hide_interaction_controls()
        self.actions.display = True
        self._set_button_available("retry", True)
        self._set_button_available("keep-rule", True)
        self._set_button_available("replace-default", True)
        self._set_button_available("edit-note", True)
        is_exception = attempt.result is AttemptResult.MISMATCH_EXCEPTION
        self._set_button_available("add-exception", not is_exception)
        self._set_button_available("replace-exception", is_exception)
        self._set_button_available("delete-exception", is_exception)

    def _start_engine_review(self, attempt: WhiteMoveAttempt) -> None:
        self._assessment_request_id += 1
        self._assessment = None
        self._assessment_error = None
        engine = self.analysis_engine
        if engine is None:
            self._assessment_loading = False
            return
        self._assessment_loading = True
        request_id = self._assessment_request_id
        self.run_worker(
            self._review_white_attempt(request_id, attempt),
            name="review-white-move",
            group="engine-analysis",
            exclusive=True,
        )

    async def _review_white_attempt(
        self,
        request_id: int,
        attempt: WhiteMoveAttempt,
    ) -> None:
        engine = self.analysis_engine
        assert engine is not None
        move = chess.Move.from_uci(attempt.selected_move.move.uci)
        try:
            assessment = await assess_white_move(
                engine,
                attempt.board_before,
                move,
                thresholds=self.quality_thresholds,
            )
        except EngineError as error:
            if not self._assessment_request_is_current(request_id, attempt):
                return
            self._assessment_error = error
            self._assessment_loading = False
        else:
            if not self._assessment_request_is_current(request_id, attempt):
                return
            self._assessment = assessment
            self._assessment_loading = False
        if self.phase is FlowPhase.WHITE_RESULT_MISMATCH:
            self._refresh_panel()
            self._update_status()

    def _assessment_request_is_current(
        self,
        request_id: int,
        attempt: WhiteMoveAttempt,
    ) -> bool:
        return (
            request_id == self._assessment_request_id
            and self.workspace.attempt is attempt
        )

    def _hide_interaction_controls(self) -> None:
        self._leave_text_mode()
        self.move_input.display = False
        self.move_input.disabled = True
        self.note_input.display = False
        self.note_input.disabled = True
        self.actions.display = False
        for button in self.actions.query(Button):
            button.display = False
            button.disabled = True

    def _hide_move_suggestions(self) -> None:
        if self.move_suggestions.has_focus:
            self.set_focus(None)
        self.move_suggestions.display = False
        self.move_suggestions.clear()

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

    def _clear_failure(self) -> None:
        if self._geometry_error is None:
            self.failure = None

    def _show_save_error(self, error: FlowError) -> None:
        self.failure = error
        self.phase = FlowPhase.ERROR
        self._leave_text_mode()
        self.panel.update(f"SAVE FAILED\n\n{error}\n\n[Esc] Return")
        self._update_status()

    def _show_black_save_error(self, error: FlowError) -> None:
        self.failure = error
        self._enter_manual_black_turn()
        self.panel.update(
            f"BRANCH SAVE FAILED\n\n{error}\n\n"
            "The move was not applied; retry after fixing the flow file."
        )

    def _refresh_panel(self) -> None:
        if self._reload_error is not None:
            self.panel.update(
                f"{self._reload_error}\n\nThe current in-memory flow remains active."
            )
            return
        if self.phase is FlowPhase.WHITE_TEST:
            turn = self.workspace.white_turn
            assert turn is not None
            self.panel.update(
                f"WHITE STEP {turn.white_step}\n\n"
                f"Position:\n{_format_history(tuple(self.history)) or 'Starting position'}"
                "\n\nPLAY YOUR MOVE"
            )
        elif self.phase is FlowPhase.FRONTIER_MOVE:
            turn = self.workspace.white_turn
            assert turn is not None
            if turn.unavailable_reason is not None:
                recommendation = turn.recommendation
                assert recommendation is not None
                self.panel.update(
                    "DEFAULT MOVE UNAVAILABLE\n\n"
                    f"Default step {turn.white_step}: {recommendation.move_san}\n\n"
                    f"{turn.unavailable_reason}\n\n"
                    "Play a legal move to define an exception."
                )
            else:
                self.panel.update(
                    f"FLOW FRONTIER\n\nNo rule exists for White step "
                    f"{turn.white_step}.\n\nPlay the move you want to add."
                )
        elif self.phase is FlowPhase.WHITE_RESULT_CORRECT:
            attempt = self.workspace.attempt
            assert attempt is not None and attempt.recommendation is not None
            note = (
                f"\n\n{attempt.recommendation.note}"
                if attempt.recommendation.note
                else ""
            )
            self.panel.update(f"CORRECT\n\n{attempt.selected_move.san}{note}")
        elif self.phase is FlowPhase.WHITE_RESULT_MISMATCH:
            self.panel.update(self._mismatch_text())
        elif self.phase is FlowPhase.RULE_NOTE:
            self.panel.update(self._rule_note_text())
        elif self.phase is FlowPhase.BLACK_LOADING:
            self.panel.update("BLACK RESPONSE\n\nPlanning opponent moves...")
        elif self.phase is FlowPhase.BLACK_SELECT:
            self.panel.update("")
        elif self.phase is FlowPhase.BLACK_ENGINE_ERROR:
            return
        elif self.phase is FlowPhase.BLACK_MANUAL:
            self.panel.update(
                "BLACK RESPONSE\n\nPlay any legal Black move on the board or type SAN."
            )
        elif self.phase is FlowPhase.GAME_OVER:
            outcome = self.workspace.outcome
            assert outcome is not None
            self.panel.update(_format_game_over(outcome))

    def _mismatch_text(self) -> str:
        attempt = self.workspace.attempt
        assert attempt is not None and attempt.recommendation is not None
        recommendation = attempt.recommendation
        source = (
            f"Exception {recommendation.exception_id}"
            if recommendation.source == "exception"
            else f"Default step {attempt.white_step}"
        )
        controls = (
            "[R] Retry\n[Enter] Keep saved rule and continue\n"
            "[X] Replace exception\n[D] Replace numbered default\n"
            "[Delete] Remove exception and use default\n[N] Edit saved note"
            if recommendation.source == "exception"
            else "[R] Retry\n[Enter] Keep saved rule and continue\n"
            "[E] Make selected move an exception\n[D] Make selected move the default\n"
            "[N] Edit saved note"
        )
        engine_review = self._engine_review_text(attempt)
        return (
            "RULE MISMATCH\n\n"
            f"You played:\n{attempt.selected_move.san}\n\n"
            f"Saved rule:\n{recommendation.move_san}\n\n"
            f"Source:\n{source}\n\n{engine_review}{controls}"
        )

    def _engine_review_text(self, attempt: WhiteMoveAttempt) -> str:
        if self.analysis_engine is None:
            return ""
        if self._assessment_loading:
            return "Engine review:\nAnalysing...\n\n"
        if self._assessment_error is not None:
            return "Engine review:\nUnavailable\n" f"{self._assessment_error}\n\n"
        assessment = self._assessment
        if assessment is None:
            return ""
        best_move = chess.Move.from_uci(assessment.best_uci)
        best_san = attempt.board_before.san(best_move)
        if assessment.loss_cp is not None:
            detail = (
                f"Approximately {assessment.loss_cp / 100:.1f} pawns worse "
                "than the best move."
            )
        elif assessment.mate_after is not None and assessment.mate_after < 0:
            detail = "Allows a forced mate for Black."
        elif assessment.mate_before is not None and assessment.mate_before > 0:
            detail = "Misses a forced mate for White."
        else:
            detail = "Mate score detected; centipawn loss is not used."
        return (
            "Engine review:\n"
            f"{assessment.quality.value.upper()}\n"
            f"{detail}\n\n"
            f"Best move:\n{best_san}\n\n"
        )

    def _rule_note_text(self) -> str:
        attempt = self.workspace.attempt
        assert attempt is not None
        if self._note_action is RuleNoteAction.SAVE_DEFAULT:
            heading = f"DEFINE DEFAULT STEP {attempt.white_step}"
            move = attempt.selected_move.san
        elif self._note_action is RuleNoteAction.SAVE_EXCEPTION:
            heading = "DEFINE POSITION EXCEPTION"
            move = attempt.selected_move.san
        else:
            heading = "EDIT SAVED NOTE"
            recommendation = attempt.recommendation
            assert recommendation is not None
            move = recommendation.move_san
        return f"{heading}\n\nMove:\n{move}\n\nWhy do you play this move?"

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
            self.status.update("[NAV] Q QUIT · ESC RETURN")
            return
        if self._move_error is not None:
            self.status.update(
                f"[TEXT: MOVE] INVALID MOVE: {self._move_error} · ESC CANCEL"
            )
            return
        if self.input.mode is InputMode.TEXT:
            if self.input.active_field is self.note_input:
                self.status.update("[TEXT: NOTE] ENTER DONE · ESC CANCEL")
            else:
                self.status.update("[TEXT: MOVE] TYPE SAN · ENTER SUBMIT · ESC CANCEL")
            return
        instructions = {
            FlowPhase.WHITE_TEST: "PLAY WHITE · I TYPE SAN · ENTER CONFIRM",
            FlowPhase.FRONTIER_MOVE: "PLAY RULE · I TYPE SAN · ENTER CONFIRM",
            FlowPhase.WHITE_RESULT_CORRECT: "CORRECT · ENTER CONTINUE",
            FlowPhase.WHITE_RESULT_MISMATCH: "R RETRY · ENTER KEEP · E/D/X EDIT",
            FlowPhase.RULE_NOTE: "I EDIT NOTE · S SAVE · ESC CANCEL",
            FlowPhase.BLACK_LOADING: "LOADING BLACK RESPONSES",
            FlowPhase.BLACK_SELECT: (
                "UP/DOWN OR A/S/D/F SELECT · ENTER PLAY · M MANUAL · I TYPE"
            ),
            FlowPhase.BLACK_ENGINE_ERROR: "M MANUAL · I TYPE SAN · R RETRY ENGINE",
            FlowPhase.BLACK_MANUAL: "PLAY BLACK · I TYPE SAN · ENTER CONFIRM",
            FlowPhase.GAME_OVER: "R RESTART · Q QUIT",
            FlowPhase.SAVING: "SAVING",
            FlowPhase.ERROR: "ESC RETURN",
            FlowPhase.LOADING: "LOADING",
        }[self.phase]
        if self.phase is FlowPhase.BLACK_ENGINE_ERROR:
            self.status.update(f"[NAV] {instructions} · CTRL+N RESTART · Q QUIT")
        elif self.phase is FlowPhase.GAME_OVER:
            self.status.update(f"[NAV] {instructions}")
        else:
            self.status.update(f"[NAV] {instructions} · R RESTART · Q QUIT")

    def _update_debug_status(self) -> None:
        turn = "white" if self.controller.board.turn is chess.WHITE else "black"
        white_step = (len(self.history) // 2) + 1
        if self.phase is FlowPhase.WHITE_TEST:
            rule = "hidden"
        elif self.workspace.attempt is not None:
            recommendation = self.workspace.attempt.recommendation
            rule = (
                f"{recommendation.source}:{recommendation.move_san}"
                if recommendation is not None
                else "none"
            )
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


FlowScreen = AuthorScreen


def _format_history(history: tuple[str, ...]) -> str:
    parts: list[str] = []
    for index, san in enumerate(history):
        if index % 2 == 0:
            parts.append(f"{(index // 2) + 1}. {san}")
        else:
            parts.append(san)
    return " ".join(parts)


def _format_game_over(outcome: chess.Outcome) -> str:
    labels = {
        chess.Termination.CHECKMATE: "Checkmate",
        chess.Termination.STALEMATE: "Stalemate",
        chess.Termination.INSUFFICIENT_MATERIAL: "Insufficient material",
        chess.Termination.SEVENTYFIVE_MOVES: "Seventy-five-move draw",
        chess.Termination.FIVEFOLD_REPETITION: "Fivefold repetition",
    }
    termination = labels.get(
        outcome.termination,
        outcome.termination.name.replace("_", " ").title(),
    )
    if outcome.winner is chess.WHITE:
        result = "White wins"
    elif outcome.winner is chess.BLACK:
        result = "Black wins"
    else:
        result = "Draw"
    return f"GAME OVER\n\n{termination}\n{result}\n\n[R] Restart flow\n[Q] Quit"
