"""Persistent local White-flow authoring screen."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import chess
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.events import Key, Resize
from textual.screen import Screen
from textual.widgets import Button, Input, Static

from ..flow import (
    AuthorBoardController,
    FlowError,
    Recommendation,
    RuleUnavailableError,
    WhiteFlowAuthor,
)
from ..layout import QuizLayoutMode, choose_quiz_layout
from ..renderers.base import PieceRenderer
from ..renderers.colors import LABEL_COLOR, SCREEN_BACKGROUND, STATUS_BACKGROUND
from ..runtime import TerminalCapabilityError
from ..tui import ChessBoard
from ..view import BoardInputMode, BoardViewState, MoveView
from .base import RendererController


class AuthorPhase(str, Enum):
    LOADING = "loading"
    WHITE_MOVE = "white-move"
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
    AuthorScreen.layout-compact #note {{ height: 1; margin: 0; border: none; }}
    AuthorScreen.layout-compact #decision-actions {{ height: 1; margin: 0; }}
    AuthorScreen.layout-compact #decision-actions Button {{ height: 1; min-width: 8; }}
    AuthorScreen.layout-too-small > #author-layout {{ display: none; }}
    """
    BINDINGS = [
        ("q", "app.quit", "Quit"),
        ("ctrl+r", "reload_flow", "Reload"),
        ("ctrl+n", "restart_line", "Restart"),
        ("enter", "confirm_move", "Confirm"),
        ("escape", "cancel", "Cancel"),
    ]

    def __init__(self, flow_path: Path, renderer: PieceRenderer) -> None:
        super().__init__()
        self.flow_path = flow_path
        self.author = WhiteFlowAuthor(flow_path)
        start = chess.Board(self.author.flow.start_fen)
        self.controller = AuthorBoardController(start)
        self.renderer_controller = RendererController(renderer)
        self.board = ChessBoard(
            self.controller.position,
            renderer=renderer,
            input_mode=BoardInputMode.MOVE_ENTRY,
        )
        self.header = Static("", id="author-header")
        self.panel = Static("", id="author-panel", markup=False)
        self.note_input = Input(placeholder="Why?", id="note")
        self.note_input.disabled = True
        self.actions = Horizontal(id="decision-actions")
        self.debug_status = Static("", id="debug-status", markup=False)
        self.status = Static("", id="author-status", markup=False)
        self.phase = AuthorPhase.LOADING
        self.layout_mode: QuizLayoutMode | None = None
        self.history: list[str] = []
        self.recommendation: Recommendation | None = None
        self.pending_change: PendingRuleChange | None = None
        self.failure: Exception | None = None
        self._geometry_error: str | None = None
        self._reload_error: str | None = None

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
            self.controller.handle_square(message.square)
            self._sync_board()

    def on_key(self, event: Key) -> None:
        if self.phase not in {
            AuthorPhase.CHOOSE_RULE_CHANGE,
            AuthorPhase.ERROR,
        }:
            return
        actions = {
            "s": "save-default",
            "e": "add-exception",
            "r": "replace-exception",
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

    def action_confirm_move(self) -> None:
        if self.phase not in {AuthorPhase.WHITE_MOVE, AuthorPhase.BLACK_MOVE}:
            return
        self._reload_error = None
        board_before = self.controller.board.copy(stack=False)
        history_before = tuple(self.history)
        confirmed = self.controller.confirm_move()
        if confirmed is None:
            return
        self.history.append(confirmed.san)
        self._sync_board()
        if confirmed.color is chess.BLACK:
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
            self._sync_board()

    def action_restart_line(self) -> None:
        self._restart()

    def action_reload_flow(self) -> None:
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
        self.controller.reset(chess.Board(self.author.flow.start_fen))
        self.history.clear()
        self.pending_change = None
        self.note_input.value = ""
        self._reload_error = None
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
        self._hide_decision()
        self._refresh_panel()
        self._sync_board()

    def _enter_black_turn(self) -> None:
        self.phase = AuthorPhase.BLACK_MOVE
        self.recommendation = None
        self._hide_decision()
        self._refresh_panel()
        self._sync_board()

    def _show_rule_decision(self) -> None:
        self.phase = AuthorPhase.CHOOSE_RULE_CHANGE
        self.note_input.disabled = False
        self.note_input.display = True
        self.actions.display = True
        pending = self.pending_change
        assert pending is not None
        self.query_one("#save-default", Button).display = (
            pending.decision is RuleDecision.DEFINE_DEFAULT
        )
        self.query_one("#add-exception", Button).display = (
            pending.decision is RuleDecision.DIFFERENT_FROM_DEFAULT
        )
        self.query_one("#replace-exception", Button).display = (
            pending.decision is RuleDecision.DIFFERENT_FROM_EXCEPTION
        )
        self.query_one("#replace-default", Button).display = (
            pending.decision is not RuleDecision.DEFINE_DEFAULT
        )
        self._refresh_panel()
        self._update_status()

    def _hide_decision(self) -> None:
        self.note_input.display = False
        self.note_input.disabled = True
        self.actions.display = False

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
        instructions = {
            AuthorPhase.WHITE_MOVE: "PLAY WHITE · ENTER CONFIRM",
            AuthorPhase.BLACK_MOVE: "PLAY BLACK · ENTER CONFIRM",
            AuthorPhase.CHOOSE_RULE_CHANGE: "CHOOSE RULE CHANGE",
            AuthorPhase.SAVING: "SAVING",
            AuthorPhase.ERROR: "C CANCEL",
            AuthorPhase.LOADING: "LOADING",
            AuthorPhase.NOTE: "ENTER NOTE",
        }[self.phase]
        self.status.update(
            f"Renderer: {self.renderer.mode.value} · {instructions} · "
            "CTRL+N RESTART · CTRL+R RELOAD · Q QUIT"
        )

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
            f"phase={self.phase.value} | turn={turn} | white_step={white_step} | "
            f"ply={len(self.history)} | rule={rule} | error={error}"
        )

    def _apply_layout_mode(self, mode: QuizLayoutMode) -> None:
        for class_name in ("layout-landscape", "layout-portrait", "layout-compact"):
            self.remove_class(class_name)
        self.add_class(f"layout-{mode.value}")
        self.layout_mode = mode
