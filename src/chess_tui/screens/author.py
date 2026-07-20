"""Textual diagnostics and play surface for deterministic v3 flows."""

from __future__ import annotations

from enum import Enum
from pathlib import Path

import chess
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Vertical
from textual.events import Key, Resize
from textual.screen import Screen
from textual.widgets import Input, Static

from ..engine import ChessEngineService, EngineError, EngineResultError
from ..flow import AttemptResult, FlowError, FlowWorkspace, PolicyMoveAttempt
from ..input_mode import InputMode, InputModeController
from ..layout import QuizLayoutMode, choose_quiz_layout
from ..opening import MoveSuggestion, OpeningSourceError, OpponentMovePlanner
from ..renderers.base import PieceRenderer
from ..renderers.colors import LABEL_COLOR, SCREEN_BACKGROUND, STATUS_BACKGROUND
from ..runtime import TerminalCapabilityError
from ..tui import ChessBoard
from ..view import BoardInputMode, BoardViewState, MoveView
from ..widgets import AdvantageBar, MoveSuggestionPanel
from .base import RendererController


class FlowPhase(str, Enum):
    LOADING = "loading"
    POLICY_TEST = "policy-test"
    POLICY_RESULT = "policy-result"
    OPPONENT_LOADING = "opponent-loading"
    OPPONENT_SELECT = "opponent-select"
    OPPONENT_MANUAL = "opponent-manual"
    GAME_OVER = "game-over"
    ERROR = "error"


class AuthorScreen(Screen[None]):
    """Play a flow and inspect v3 decisions; editing lives in web/TOML."""

    AUTO_FOCUS = ""
    CSS = f"""
    AuthorScreen {{ background: {SCREEN_BACKGROUND}; }}
    AuthorScreen > #author-header {{ dock: top; height: 1; color: {LABEL_COLOR}; background: {STATUS_BACKGROUND}; text-style: bold; padding: 0 1; }}
    AuthorScreen > #author-layout {{ width: 100%; height: 1fr; }}
    AuthorScreen #board-stage {{ align: center middle; }}
    AuthorScreen #author-side {{ padding: 1 2; }}
    AuthorScreen #advantage-bar {{ height: 1; margin-bottom: 1; }}
    AuthorScreen #move-suggestions {{ display: none; height: auto; margin-top: 1; }}
    AuthorScreen #move-entry {{ height: 3; margin-top: 1; }}
    AuthorScreen > #author-status {{ dock: bottom; height: 1; color: {LABEL_COLOR}; background: {STATUS_BACKGROUND}; text-align: center; }}
    AuthorScreen.layout-landscape > #author-layout {{ layout: horizontal; }}
    AuthorScreen.layout-landscape #board-stage {{ width: auto; height: 100%; }}
    AuthorScreen.layout-landscape #author-side {{ width: 1fr; min-width: 34; height: 100%; }}
    AuthorScreen.layout-portrait > #author-layout, AuthorScreen.layout-compact > #author-layout {{ layout: vertical; }}
    AuthorScreen.layout-portrait #board-stage, AuthorScreen.layout-compact #board-stage {{ width: 100%; height: auto; }}
    AuthorScreen.layout-portrait #author-side {{ width: 100%; height: 1fr; padding: 0 2; }}
    AuthorScreen.layout-compact #author-side {{ width: 100%; height: 4; padding: 0; }}
    AuthorScreen.layout-compact #author-panel, AuthorScreen.layout-compact #advantage-bar, AuthorScreen.layout-compact #move-entry {{ height: 1; margin: 0; border: none; }}
    AuthorScreen.layout-too-small > #author-layout {{ display: none; }}
    """
    BINDINGS = [
        Binding("q", "request_quit", "Quit"),
        Binding("i", "focus_move", "Type"),
        Binding("ctrl+r", "reload_flow", "Reload"),
        Binding("ctrl+n", "restart_line", "Restart"),
        Binding("enter", "confirm_move", "Confirm"),
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
        quality_thresholds=None,
        auto_play_black: bool = False,
        focus_san_on_white_turn: bool = False,
    ) -> None:
        del quality_thresholds
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
        self.auto_play_black = auto_play_black
        self.focus_san_on_white_turn = focus_san_on_white_turn
        self.board = ChessBoard(
            self.controller.position,
            renderer=renderer,
            input_mode=BoardInputMode.MOVE_ENTRY,
        )
        self.header = Static("", id="author-header")
        self.panel = Static("", id="author-panel", markup=False)
        self.advantage_bar = AdvantageBar()
        self.advantage_bar.display = analysis_engine is not None
        self.move_suggestions = MoveSuggestionPanel()
        self.move_input = Input(placeholder="Type SAN and press Enter", id="move-entry")
        self.status = Static("", id="author-status", markup=False)
        self.input = InputModeController()
        self.phase = FlowPhase.LOADING
        self.layout_mode: QuizLayoutMode | None = None
        self.failure: Exception | None = None
        self._request_id = 0
        self._advantage_key: str | None = None

    @property
    def renderer(self) -> PieceRenderer:
        return self.renderer_controller.active

    def compose(self) -> ComposeResult:
        yield self.header
        with Container(id="author-layout"):
            with Container(id="board-stage"):
                yield self.board
            with Vertical(id="author-side"):
                yield self.advantage_bar
                yield self.panel
                yield self.move_suggestions
                yield self.move_input
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
            self.board.unconfigure()
            self.add_class("layout-too-small")
            self.status.update(str(error).replace("\n", " "))
            return
        self.remove_class("layout-too-small")
        if layout.mode is not self.layout_mode:
            self._apply_layout_mode(layout.mode)
        self.board.renderer = self.renderer
        self.board.configure(layout.board_geometry)

    def on_chess_board_square_hovered(self, message: ChessBoard.SquareHovered) -> None:
        self.controller.set_hover(message.square)
        self._sync_board()

    def on_chess_board_square_clicked(self, message: ChessBoard.SquareClicked) -> None:
        if self.phase not in {FlowPhase.POLICY_TEST, FlowPhase.OPPONENT_MANUAL}:
            return
        if self.input.mode is InputMode.TEXT:
            self.input.leave_text()
        self.controller.handle_square(message.square)
        self.move_input.value = self.controller.pending_san or ""
        self._sync_board()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input is not self.move_input:
            return
        event.stop()
        value = event.value.strip()
        if not value:
            self.action_confirm_move()
            return
        try:
            if self.phase is FlowPhase.POLICY_TEST:
                self._handle_attempt(self.workspace.submit_policy_san(value))
            elif self.phase is FlowPhase.OPPONENT_MANUAL:
                self.workspace.submit_opponent_san(value)
                self._after_opponent()
        except (ValueError, FlowError) as error:
            self.failure = error
            self.status.update(f"INVALID MOVE · {error}")

    def on_key(self, event: Key) -> None:
        if not self.input.handles_global_shortcuts:
            return
        if self.phase is FlowPhase.POLICY_RESULT and event.key.lower() == "r":
            event.stop()
            self.workspace.retry_policy_move()
            self._enter_policy_turn()
        elif self.phase is FlowPhase.OPPONENT_SELECT and event.key.lower() == "m":
            event.stop()
            self._enter_opponent_manual()

    def on_move_suggestion_panel_suggestion_submitted(
        self, message: MoveSuggestionPanel.SuggestionSubmitted
    ) -> None:
        if self.phase is FlowPhase.OPPONENT_SELECT:
            self._play_suggestion(message.suggestion)

    def on_move_suggestion_panel_manual_requested(
        self, message: MoveSuggestionPanel.ManualRequested
    ) -> None:
        del message
        self._enter_opponent_manual()

    def on_move_suggestion_panel_text_requested(
        self, message: MoveSuggestionPanel.TextRequested
    ) -> None:
        del message
        self._enter_opponent_manual(focus=True)

    def action_focus_move(self) -> None:
        if self.phase in {FlowPhase.POLICY_TEST, FlowPhase.OPPONENT_MANUAL}:
            self.input.enter_text(self.move_input)
        elif self.phase is FlowPhase.OPPONENT_SELECT:
            self._enter_opponent_manual(focus=True)

    def action_confirm_move(self) -> None:
        if self.phase is FlowPhase.POLICY_RESULT:
            attempt = self.workspace.attempt
            if attempt is not None and attempt.result is AttemptResult.MISMATCH:
                self.workspace.continue_with_policy_move()
                self._enter_opponent_turn()
            return
        if self.phase is FlowPhase.OPPONENT_SELECT:
            self.move_suggestions.submit_highlighted()
            return
        try:
            if self.phase is FlowPhase.POLICY_TEST:
                attempt = self.workspace.submit_pending_policy_move()
                if attempt is not None:
                    self._handle_attempt(attempt)
            elif self.phase is FlowPhase.OPPONENT_MANUAL:
                confirmed = self.workspace.submit_pending_opponent_move()
                if confirmed is not None:
                    self._after_opponent()
        except FlowError as error:
            self.failure = error
            self.status.update(f"FLOW ERROR · {error}")

    def action_cancel(self) -> None:
        if self.input.mode is InputMode.TEXT:
            self.input.leave_text()
            self.set_focus(None)
        elif self.phase is FlowPhase.POLICY_RESULT:
            self.workspace.retry_policy_move()
            self._enter_policy_turn()

    def action_request_quit(self) -> None:
        if self.input.handles_global_shortcuts:
            self.app.exit()

    def action_restart_line(self) -> None:
        self._restart()

    def action_reload_flow(self) -> None:
        try:
            turn = self.workspace.reload()
        except FlowError as error:
            self.failure = error
            self.panel.update(
                f"RELOAD FAILED\n\n{error}\n\nThe current in-memory policy remains active."
            )
            return
        self.failure = None
        if self.workspace.outcome is not None:
            self._enter_game_over()
        elif turn is not None:
            self._enter_policy_turn()
        else:
            self._enter_opponent_turn()

    def _restart(self) -> None:
        self.workspace.restart()
        self._enter_policy_turn()

    def _enter_policy_turn(self) -> None:
        turn = self.workspace.policy_turn or self.workspace.begin_policy_turn()
        self.phase = FlowPhase.POLICY_TEST
        self.move_suggestions.display = False
        self.move_input.disabled = False
        decision = turn.decision
        selected = decision.source_id or (
            decision.frontier_reason.value
            if decision.frontier_reason is not None
            else "frontier"
        )
        trace = "\n".join(f"• {line}" for line in decision.trace)
        self.panel.update(
            f"POLICY DECISION\n\nSelected: {selected}\nMove: {decision.move_san or 'Frontier'}"
            f"\nReason: {decision.note or 'No note.'}\n\n{trace}"
        )
        self._sync_board()
        if self.focus_san_on_white_turn:
            self.input.enter_text(self.move_input)

    def _handle_attempt(self, attempt: PolicyMoveAttempt) -> None:
        self.move_input.value = ""
        if attempt.result is AttemptResult.CORRECT:
            self.workspace.complete_correct_move()
            if self.workspace.outcome is not None:
                self._enter_game_over()
            else:
                self._enter_opponent_turn(correct_san=attempt.selected_move.san)
            return
        self.phase = FlowPhase.POLICY_RESULT
        expected = attempt.decision.move_san or "Frontier"
        self.panel.update(
            f"{'RULE MISMATCH' if attempt.result is AttemptResult.MISMATCH else 'FLOW FRONTIER'}\n\n"
            f"You played: {attempt.selected_move.san}\nExpected: {expected}\n"
            f"Rule: {attempt.decision.source_id or 'none'}\n"
            f"Reason: {attempt.decision.note or 'No note.'}\n\n"
            "[R/Esc] Retry    [Enter] Use selected policy move\n"
            "Edit rules in the local web UI or TOML source."
        )
        self._sync_board()

    def _enter_opponent_turn(self, *, correct_san: str | None = None) -> None:
        if self.workspace.outcome is not None:
            self._enter_game_over()
            return
        self.phase = FlowPhase.OPPONENT_LOADING
        prefix = f"CORRECT · {correct_san}\n\n" if correct_san else ""
        self.panel.update(prefix + "Loading opponent replies…")
        self.move_input.disabled = True
        self._request_id += 1
        request_id = self._request_id
        board = self.controller.board.copy(stack=False)
        self.run_worker(
            self._load_suggestions(request_id, board),
            name="opponent-suggestions",
            exclusive=True,
        )

    async def _load_suggestions(self, request_id: int, board: chess.Board) -> None:
        try:
            suggestions = await self.opponent_planner.suggestions_for(board)
        except OpeningSourceError as error:
            if request_id != self._request_id:
                return
            self.failure = error
            self._enter_opponent_manual()
            self.panel.update(
                f"OPPONENT ENGINE ERROR\n\n{error}\n\nEnter a legal reply manually."
            )
            return
        if (
            request_id != self._request_id
            or self.phase is not FlowPhase.OPPONENT_LOADING
        ):
            return
        if self.auto_play_black and suggestions:
            self._play_suggestion(suggestions[0])
            return
        self.phase = FlowPhase.OPPONENT_SELECT
        self.move_suggestions.display = True
        self.move_suggestions.set_suggestions(
            suggestions, context="Choose a reply or press M for manual entry."
        )
        self.move_suggestions.focus()
        self.panel.update("")
        self._update_status()

    def _play_suggestion(self, suggestion: MoveSuggestion) -> None:
        try:
            self.workspace.submit_opponent_uci(suggestion.uci)
        except FlowError as error:
            self.failure = error
            self._enter_opponent_manual()
            self.panel.update(f"BRANCH SAVE FAILED\n\n{error}")
            return
        self._after_opponent()

    def _enter_opponent_manual(self, *, focus: bool = False) -> None:
        self._request_id += 1
        self.phase = FlowPhase.OPPONENT_MANUAL
        self.move_suggestions.display = False
        self.move_input.disabled = False
        self.panel.update(
            "OPPONENT RESPONSE\n\nPlay a legal move on the board or type SAN."
        )
        self._sync_board()
        if focus:
            self.input.enter_text(self.move_input)

    def _after_opponent(self) -> None:
        if self.workspace.outcome is not None:
            self._enter_game_over()
        else:
            self.workspace.begin_policy_turn()
            self._enter_policy_turn()

    def _enter_game_over(self) -> None:
        self.phase = FlowPhase.GAME_OVER
        self.move_suggestions.display = False
        self.move_input.disabled = True
        outcome = self.workspace.outcome
        assert outcome is not None
        winner = (
            "Draw"
            if outcome.winner is None
            else ("White wins" if outcome.winner else "Black wins")
        )
        self.panel.update(
            f"GAME OVER\n\n{outcome.termination.name.replace('_', ' ').title()}\n{winner}\n\nCtrl+N restarts."
        )
        self._sync_board()

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
                    if interaction.pending_move
                    else None
                ),
                hover_square=interaction.hover_square,
                last_move=(
                    MoveView(
                        interaction.last_move.from_square,
                        interaction.last_move.to_square,
                    )
                    if interaction.last_move
                    else None
                ),
                checked_king=interaction.checked_king,
            ),
            flipped=self.workspace.author.rulebook.side == "black",
        )
        line = " ".join(self.history) if self.history else "Starting position"
        self.header.update(f"{self.author.rulebook.name.upper()}    {line}")
        self._update_status()
        self._track_advantage()

    def _track_advantage(self) -> None:
        if self.analysis_engine is None:
            return
        board = self.controller.board.copy(stack=False)
        key = board.fen(en_passant="fen")
        if key == self._advantage_key:
            return
        self._advantage_key = key
        outcome = board.outcome(claim_draw=False)
        if outcome is not None:
            self.advantage_bar.set_outcome(outcome)
            return
        self.advantage_bar.mark_loading()
        self.run_worker(
            self._load_advantage(key, board), name="flow-advantage", exclusive=True
        )

    async def _load_advantage(self, key: str, board: chess.Board) -> None:
        assert self.analysis_engine is not None
        try:
            lines = await self.analysis_engine.analyse(board, count=1)
            if not lines:
                raise EngineResultError("Engine returned no analysis.")
        except EngineError as error:
            if self._advantage_key == key:
                self.advantage_bar.set_error(str(error))
            return
        if self._advantage_key == key:
            self.advantage_bar.set_evaluation(
                evaluation_cp=lines[0].evaluation_cp, mate_in=lines[0].mate_in
            )

    def _update_status(self) -> None:
        if self.input.mode is InputMode.TEXT:
            self.status.update("[TEXT] TYPE SAN · ENTER SUBMIT · ESC EXIT")
            return
        labels = {
            FlowPhase.LOADING: "LOADING",
            FlowPhase.POLICY_TEST: "PLAY POLICY MOVE · I TYPE SAN · ENTER CONFIRM",
            FlowPhase.POLICY_RESULT: "R RETRY · ENTER USE SELECTED MOVE",
            FlowPhase.OPPONENT_LOADING: "LOADING OPPONENT RESPONSES",
            FlowPhase.OPPONENT_SELECT: "SELECT RESPONSE · ENTER PLAY · M MANUAL",
            FlowPhase.OPPONENT_MANUAL: "PLAY OPPONENT · I TYPE SAN",
            FlowPhase.GAME_OVER: "CTRL+N RESTART · Q QUIT",
            FlowPhase.ERROR: "CTRL+R RELOAD · Q QUIT",
        }
        self.status.update(f"[NAV] {labels[self.phase]} · CTRL+R RELOAD · Q QUIT")

    def _apply_layout_mode(self, mode: QuizLayoutMode) -> None:
        for name in ("layout-landscape", "layout-portrait", "layout-compact"):
            self.remove_class(name)
        self.add_class(f"layout-{mode.value}")
        self.layout_mode = mode


FlowScreen = AuthorScreen
