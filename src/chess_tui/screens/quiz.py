"""ChessFlow-shaped local fixture quiz screen."""

from __future__ import annotations

from enum import Enum

from textual.app import ComposeResult
from textual.containers import Container, Vertical
from textual.events import Key, Resize
from textual.screen import Screen
from textual.timer import Timer
from textual.widgets import Static

from ..board import DEFAULT_STARTING_FEN, parse_fen
from ..layout import QuizLayoutMode, choose_quiz_layout
from ..renderers.base import PieceRenderer
from ..renderers.colors import LABEL_COLOR, SCREEN_BACKGROUND, STATUS_BACKGROUND
from ..runtime import TerminalCapabilityError
from ..sessions.base import EditableQuizSession, QuizSession
from ..sessions.errors import SessionError
from ..sessions.models import (
    ContinuationDraft,
    FlowSummary,
    FrontierKind,
    FrontierState,
    QuizPhase,
    QuizSessionState,
    RuleType,
)
from ..sessions.provider import QuizProvider
from ..tui import ChessBoard
from ..view import BoardInputMode, board_view_from_quiz_state
from ..widgets.choice_panel import ChoicePanel
from ..widgets.continuation import ContinuationEditor
from ..widgets.feedback import FeedbackPanel
from ..widgets.frontier import FrontierPanel
from .base import RendererController
from .modals import FlowPickerModal


class QuizUiPhase(str, Enum):
    LOADING = "loading"
    ASKING = "asking"
    SUBMITTING = "submitting"
    CORRECT_FEEDBACK = "correct-feedback"
    MISMATCH_FEEDBACK = "mismatch-feedback"
    FRONTIER = "frontier"
    ERROR = "error"


class QuizScreen(Screen[None]):
    AUTO_ADVANCE_SECONDS = 0.6
    CSS = f"""
    QuizScreen {{ background: {SCREEN_BACKGROUND}; }}
    QuizScreen > #quiz-header {{
        dock: top; height: 1; color: {LABEL_COLOR}; background: {STATUS_BACKGROUND};
        text-style: bold; padding: 0 1;
    }}
    QuizScreen > #quiz-layout {{ width: 100%; height: 1fr; }}
    QuizScreen #board-stage {{ align: center middle; }}
    QuizScreen #quiz-side {{ padding: 1 2; }}
    QuizScreen .section-label {{ color: #9eaf74; text-style: bold; margin-top: 1; }}
    QuizScreen ChoicePanel {{ height: auto; margin-top: 1; }}
    QuizScreen MoveChoiceButton {{ height: 3; padding: 1 2; color: #d7ddcf; }}
    QuizScreen MoveChoiceButton:hover, QuizScreen MoveChoiceButton.selected {{
        color: #fffdf5; background: #405e42; text-style: bold;
    }}
    QuizScreen FeedbackPanel {{ height: auto; margin-top: 1; padding: 1 2; }}
    QuizScreen FeedbackPanel.correct {{ color: #d8f3c7; background: #29472e; }}
    QuizScreen FeedbackPanel.mismatch {{ color: #ffe0d5; background: #5a2929; }}
    QuizScreen FrontierPanel {{ height: auto; margin-top: 1; padding: 1 2; border: solid #9eaf74; }}
    QuizScreen ContinuationEditor {{
        display: none; height: auto; margin-top: 1; padding: 1 2; border: solid #9eaf74;
    }}
    QuizScreen ContinuationEditor Input {{ height: 1; border: none; margin-bottom: 1; }}
    QuizScreen ContinuationEditor #editor-help {{ color: #9eaf74; margin-bottom: 1; }}
    QuizScreen ContinuationEditor #editor-actions {{ height: 3; }}
    QuizScreen ContinuationEditor Button {{ width: 1fr; height: 3; }}
    QuizScreen > #quiz-status {{
        dock: bottom; height: 1; color: {LABEL_COLOR}; background: {STATUS_BACKGROUND};
        text-align: center;
    }}
    QuizScreen.layout-landscape > #quiz-layout {{ layout: horizontal; }}
    QuizScreen.layout-landscape #board-stage {{ width: auto; height: 100%; }}
    QuizScreen.layout-landscape #quiz-side {{
        display: block; width: 1fr; min-width: 34; height: 100%;
    }}
    QuizScreen.layout-landscape ChoicePanel {{
        layout: vertical; width: 100%; height: auto;
    }}
    QuizScreen.layout-landscape MoveChoiceButton {{ width: 100%; height: 3; }}
    QuizScreen.layout-portrait > #quiz-layout {{ layout: vertical; }}
    QuizScreen.layout-portrait #board-stage {{ width: 100%; height: auto; }}
    QuizScreen.layout-portrait #quiz-side {{
        display: block; width: 100%; height: 1fr; padding: 0 2;
    }}
    QuizScreen.layout-portrait ChoicePanel {{
        layout: horizontal; width: 100%; height: 3;
    }}
    QuizScreen.layout-portrait MoveChoiceButton {{ width: 1fr; height: 3; padding: 1; }}
    QuizScreen.layout-compact > #quiz-layout {{ layout: vertical; }}
    QuizScreen.layout-compact #board-stage {{ width: 100%; height: auto; }}
    QuizScreen.layout-compact #quiz-side {{
        display: block; width: 100%; height: 4; padding: 0;
    }}
    QuizScreen.layout-compact #position-label,
    QuizScreen.layout-compact #move-line,
    QuizScreen.layout-compact #move-label,
    QuizScreen.layout-compact #quiz-prompt {{ display: none; }}
    QuizScreen.layout-compact ChoicePanel {{
        display: block; layout: horizontal; width: 100%; height: 3;
    }}
    QuizScreen.layout-compact MoveChoiceButton {{ width: 1fr; height: 3; padding: 1; }}
    QuizScreen.layout-compact.phase-asking FeedbackPanel,
    QuizScreen.layout-compact.phase-asking FrontierPanel {{ display: none; }}
    QuizScreen.layout-compact.phase-feedback ChoicePanel,
    QuizScreen.layout-compact.phase-feedback FrontierPanel {{ display: none; }}
    QuizScreen.layout-compact.phase-feedback FeedbackPanel {{
        display: block; height: 3; padding: 0 1;
    }}
    QuizScreen.layout-compact.phase-frontier ChoicePanel,
    QuizScreen.layout-compact.phase-frontier FeedbackPanel {{ display: none; }}
    QuizScreen.layout-compact.phase-frontier FrontierPanel {{
        display: block; height: 4; padding: 0 1;
    }}
    QuizScreen.layout-compact ContinuationEditor {{
        height: 4; margin: 0; padding: 0; border: none;
    }}
    QuizScreen.layout-compact ContinuationEditor #editor-help,
    QuizScreen.layout-compact ContinuationEditor #note {{ display: none; }}
    QuizScreen.layout-compact ContinuationEditor Input {{
        height: 1; margin: 0; border: none;
    }}
    QuizScreen.layout-compact ContinuationEditor #editor-actions {{ height: 1; }}
    QuizScreen.layout-compact ContinuationEditor Button {{ height: 1; min-width: 10; }}
    QuizScreen.layout-too-small > #quiz-layout {{ display: none; }}
    """
    BINDINGS = [("q", "app.quit", "Quit")]

    def __init__(
        self,
        provider: QuizProvider,
        flow: FlowSummary,
        session: QuizSession,
        renderer: PieceRenderer,
    ) -> None:
        super().__init__()
        self.provider = provider
        self.session = session
        self.flow = flow
        self.renderer_controller = RendererController(renderer)
        self.board = ChessBoard(
            parse_fen(DEFAULT_STARTING_FEN),
            renderer=renderer,
            input_mode=BoardInputMode.READ_ONLY,
        )
        self.header = Static("", id="quiz-header")
        self.line = Static("", id="move-line")
        self.prompt = Static("", id="quiz-prompt")
        self.choice_panel = ChoicePanel()
        self.feedback_panel = FeedbackPanel("")
        self.frontier_panel = FrontierPanel("")
        self.continuation_editor = ContinuationEditor()
        self.status = Static("", id="quiz-status")
        self.phase = QuizUiPhase.LOADING
        self.layout_mode: QuizLayoutMode | None = None
        self.state: QuizSessionState | None = None
        self.score = 0
        self.streak = 0
        self.failure: Exception | None = None
        self._feedback_timer: Timer | None = None
        self._generation = 0
        self._continuation_rules: list[ContinuationDraft] = []
        self._last_choice_id: str | None = None
        self._streak_before_answer = 0

    @property
    def renderer(self) -> PieceRenderer:
        return self.renderer_controller.active

    def compose(self) -> ComposeResult:
        yield self.header
        with Container(id="quiz-layout"):
            with Container(id="board-stage"):
                yield self.board
            with Vertical(id="quiz-side"):
                yield Static("POSITION", id="position-label", classes="section-label")
                yield self.line
                yield Static(
                    "SELECT YOUR MOVE", id="move-label", classes="section-label"
                )
                yield self.prompt
                yield self.choice_panel
                yield self.feedback_panel
                yield self.frontier_panel
                yield self.continuation_editor
        yield self.status

    async def on_mount(self) -> None:
        self.feedback_panel.clear_feedback()
        self.frontier_panel.clear_frontier()
        self.continuation_editor.display = False
        await self._start_session()

    async def on_unmount(self) -> None:
        self._cancel_feedback_timer()
        try:
            await self.session.close()
        finally:
            await self.provider.close()

    def on_resize(self, event: Resize) -> None:
        try:
            layout = choose_quiz_layout(
                event.size, event.pixel_size, self.renderer.mode
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
        if isinstance(self.failure, TerminalCapabilityError):
            self.failure = None
        self._update_status()

    async def on_key(self, event: Key) -> None:
        key = event.key.lower()
        if key == "l":
            event.stop()
            self.action_select_flow()
            return
        if self.phase is QuizUiPhase.ASKING:
            if key in {"a", "s", "d", "f"}:
                event.stop()
                self.choice_panel.highlight_key(key)
            elif key == "up":
                event.stop()
                self.choice_panel.move_highlight(-1)
            elif key == "down":
                event.stop()
                self.choice_panel.move_highlight(1)
            elif key == "enter":
                event.stop()
                self.choice_panel.submit_highlighted()
            return
        if key == "e" and self.phase is QuizUiPhase.MISMATCH_FEEDBACK:
            event.stop()
            await self._update_correct_answer()
            return
        if key == "enter" and self.phase in {
            QuizUiPhase.CORRECT_FEEDBACK,
            QuizUiPhase.MISMATCH_FEEDBACK,
        }:
            event.stop()
            await self._continue_after_feedback()
            return
        if self.phase is QuizUiPhase.FRONTIER:
            if self.continuation_editor.display:
                if key == "escape":
                    event.stop()
                    self.continuation_editor.cancel()
                return
            if key == "a":
                event.stop()
                self.action_add_continuation()
            elif key == "d" and self._default_continuation is not None:
                event.stop()
                self.action_edit_default_continuation()
            elif key == "s":
                event.stop()
                await self._restart()
            elif key == "f":
                event.stop()
                self.app.exit()
            return
        if self.phase is QuizUiPhase.ERROR and key == "r":
            event.stop()
            await self._start_session()

    async def on_choice_panel_choice_submitted(
        self, message: ChoicePanel.ChoiceSubmitted
    ) -> None:
        if self.phase is not QuizUiPhase.ASKING:
            return
        state = self.state
        if state is None or state.question is None:
            return
        self._set_phase(QuizUiPhase.SUBMITTING)
        self._last_choice_id = message.choice.id
        self._streak_before_answer = self.streak
        self.choice_panel.set_submission_enabled(False)
        self._update_status()
        try:
            feedback_state = await self.session.answer(
                state.question.id, message.choice.id
            )
        except SessionError as exc:
            self._show_error(exc)
            return
        feedback = feedback_state.feedback
        if feedback is None:
            self._show_error(
                SessionError("Provider returned feedback without details.")
            )
            return
        self.state = feedback_state
        self.feedback_panel.show_feedback(
            feedback, editable=isinstance(self.session, EditableQuizSession)
        )
        if feedback.correct:
            self.score += 1
            self.streak += 1
            self._set_phase(QuizUiPhase.CORRECT_FEEDBACK)
            self._schedule_auto_continue()
        else:
            self.streak = 0
            self._set_phase(QuizUiPhase.MISMATCH_FEEDBACK)
        self._refresh_header()
        self._update_status()

    def action_select_flow(self) -> None:
        self.run_worker(self._open_flow_picker(), exclusive=True)

    def action_add_continuation(self) -> None:
        if (
            self.phase is QuizUiPhase.FRONTIER
            and self.state is not None
            and self.state.frontier is not None
        ):
            frontier = self.state.frontier
            if self._default_continuation is not None:
                frontier = FrontierState(
                    kind=FrontierKind.NEEDS_OPPONENT_CONTINUATION,
                    fen=frontier.fen,
                    line_san=frontier.line_san,
                    message="Add an exception for a specific opponent move.",
                )
            self._show_continuation_editor(frontier)

    def action_edit_default_continuation(self) -> None:
        state = self.state
        default = self._default_continuation
        if state is None or state.frontier is None or default is None:
            return
        frontier = FrontierState(
            kind=FrontierKind.NEEDS_FIRST_RULE,
            fen=state.frontier.fen,
            line_san=state.frontier.line_san,
            message="Edit the response used after any opponent move.",
        )
        self._show_continuation_editor(frontier, initial=default)

    async def _start_session(self) -> None:
        self._cancel_feedback_timer()
        self._set_phase(QuizUiPhase.LOADING)
        self.failure = None
        self.choice_panel.clear()
        self._update_status()
        try:
            state = await self.session.start()
        except SessionError as exc:
            self._show_error(exc)
            return
        self._apply_state(state)

    async def _restart(self) -> None:
        self._cancel_feedback_timer()
        self._set_phase(QuizUiPhase.LOADING)
        self.score = 0
        self.streak = 0
        self._continuation_rules.clear()
        try:
            state = await self.session.restart()
        except SessionError as exc:
            self._show_error(exc)
            return
        self._apply_state(state)

    async def _continue_after_feedback(self) -> None:
        if self.phase not in {
            QuizUiPhase.CORRECT_FEEDBACK,
            QuizUiPhase.MISMATCH_FEEDBACK,
        }:
            return
        self._cancel_feedback_timer()
        self._set_phase(QuizUiPhase.SUBMITTING)
        self._update_status()
        try:
            state = await self.session.continue_session()
        except SessionError as exc:
            self._show_error(exc)
            return
        self._apply_state(state)

    async def _update_correct_answer(self) -> None:
        state = self.state
        choice_id = self._last_choice_id
        session = self.session
        if (
            state is None
            or state.question is None
            or choice_id is None
            or not isinstance(session, EditableQuizSession)
        ):
            return
        self._set_phase(QuizUiPhase.SUBMITTING)
        self._update_status()
        try:
            edited_state = await session.update_correct_answer(
                state.question.id, choice_id
            )
        except SessionError as exc:
            self._show_error(exc)
            return
        feedback = edited_state.feedback
        if feedback is None:
            self._show_error(SessionError("Provider returned no edited feedback."))
            return
        self.state = edited_state
        self.score += 1
        self.streak = self._streak_before_answer + 1
        self.feedback_panel.show_feedback(feedback)
        self._set_phase(QuizUiPhase.CORRECT_FEEDBACK)
        self._refresh_header()
        self._update_status()

    def _apply_state(self, state: QuizSessionState) -> None:
        self._generation += 1
        self.state = state
        self.board.update_view(board_view_from_quiz_state(state), flipped=False)
        self.line.update(_format_line(state.line_san))
        self.feedback_panel.clear_feedback()
        self.frontier_panel.clear_frontier()
        self.continuation_editor.display = False
        if state.phase is QuizPhase.QUESTION and state.question is not None:
            self._last_choice_id = None
            self._set_phase(QuizUiPhase.ASKING)
            self.prompt.update(state.question.prompt)
            self.choice_panel.set_choices(state.question.choices)
            self.choice_panel.focus()
        elif state.phase is QuizPhase.FRONTIER and state.frontier is not None:
            self._set_phase(QuizUiPhase.FRONTIER)
            self.prompt.update("")
            self.choice_panel.clear()
            self.frontier_panel.show_frontier(
                state.frontier, rules=tuple(self._continuation_rules)
            )
        else:
            self._show_error(
                SessionError(f"Unexpected provider phase: {state.phase.value}.")
            )
            return
        self._refresh_header()
        self._update_status()

    def _schedule_auto_continue(self) -> None:
        self._cancel_feedback_timer()
        generation = self._generation

        async def continue_current() -> None:
            if (
                generation == self._generation
                and self.phase is QuizUiPhase.CORRECT_FEEDBACK
            ):
                await self._continue_after_feedback()

        self._feedback_timer = self.set_timer(
            self.AUTO_ADVANCE_SECONDS, continue_current
        )

    def _cancel_feedback_timer(self) -> None:
        if self._feedback_timer is not None:
            self._feedback_timer.stop()
            self._feedback_timer = None

    def _show_error(self, error: Exception) -> None:
        self._cancel_feedback_timer()
        self.failure = error
        self._set_phase(QuizUiPhase.ERROR)
        self.choice_panel.clear()
        self.prompt.update(f"SESSION ERROR\n\n{error}\n\n[R] Retry  [Q] Quit")
        self._update_status()

    def _refresh_header(self) -> None:
        line = (
            _format_line(self.state.line_san)
            if self.state is not None
            else "Starting position"
        )
        self.header.update(
            f"{self.flow.name.upper()} · {self.flow.side.upper()}"
            f"    {_truncate(line, 36)}"
            f"    SCORE {self.score}    STREAK {self.streak}"
        )

    def _update_status(self) -> None:
        renderer = self.renderer.mode.value
        mismatch_instructions = (
            "E MAKE SELECTED CORRECT · ENTER CONTINUE"
            if isinstance(self.session, EditableQuizSession)
            else "ENTER CONTINUE"
        )
        instructions = {
            QuizUiPhase.LOADING: "LOADING",
            QuizUiPhase.ASKING: "A/S/D/F HIGHLIGHT · ENTER CONFIRM · L FLOWS",
            QuizUiPhase.SUBMITTING: "SUBMITTING",
            QuizUiPhase.CORRECT_FEEDBACK: "ENTER CONTINUE NOW",
            QuizUiPhase.MISMATCH_FEEDBACK: mismatch_instructions,
            QuizUiPhase.FRONTIER: self._frontier_instructions,
            QuizUiPhase.ERROR: "R RETRY · Q QUIT",
        }[self.phase]
        self.status.update(f"Renderer: {renderer} · {instructions} · Q QUIT")

    def _flow_selected(self, flow_id: str | None) -> None:
        if flow_id is not None and flow_id != self.flow.id:
            self.run_worker(self._switch_flow(flow_id), exclusive=True)

    async def _open_flow_picker(self) -> None:
        try:
            flows = await self.provider.list_flows()
        except SessionError as error:
            self._show_error(error)
            return
        self.app.push_screen(FlowPickerModal(flows, self.flow.id), self._flow_selected)

    async def _switch_flow(self, flow_id: str) -> None:
        self._cancel_feedback_timer()
        try:
            flow = await self.provider.select_flow(flow_id)
            session = await self.provider.create_session(flow_id)
        except SessionError as error:
            self._show_error(error)
            return
        try:
            await self.session.close()
        except SessionError as error:
            await session.close()
            self._show_error(error)
            return
        self.flow = flow
        self.session = session
        self.score = 0
        self.streak = 0
        self._continuation_rules.clear()
        await self._start_session()

    def _continuation_collected(self, result: ContinuationDraft | None) -> None:
        if result is None:
            return
        if result.rule_type is RuleType.DEFAULT:
            self._continuation_rules = [
                rule
                for rule in self._continuation_rules
                if rule.rule_type is not RuleType.DEFAULT
            ]
            self._continuation_rules.insert(0, result)
        else:
            self._continuation_rules = [
                rule
                for rule in self._continuation_rules
                if not (
                    rule.rule_type is RuleType.EXACT
                    and rule.opponent_move_san == result.opponent_move_san
                )
            ]
            self._continuation_rules.append(result)
        if self.state is None or self.state.frontier is None:
            return
        self.frontier_panel.show_frontier(
            self.state.frontier, rules=tuple(self._continuation_rules)
        )

    def on_continuation_editor_submitted(
        self, message: ContinuationEditor.Submitted
    ) -> None:
        self._continuation_collected(message.draft)
        self.frontier_panel.display = True
        self._update_status()

    def on_continuation_editor_cancelled(
        self, message: ContinuationEditor.Cancelled
    ) -> None:
        self.frontier_panel.display = True
        self._update_status()

    def _show_continuation_editor(
        self,
        frontier: FrontierState,
        *,
        initial: ContinuationDraft | None = None,
    ) -> None:
        self.frontier_panel.display = False
        self.continuation_editor.show_editor(frontier, initial=initial)
        self._update_status()

    @property
    def _default_continuation(self) -> ContinuationDraft | None:
        return next(
            (
                rule
                for rule in self._continuation_rules
                if rule.rule_type is RuleType.DEFAULT
            ),
            None,
        )

    @property
    def _frontier_instructions(self) -> str:
        if self.continuation_editor.display:
            return "EDIT RULE INLINE · ESC CANCEL"
        if self._default_continuation is not None:
            return "A ADD EXCEPTION · D EDIT DEFAULT · S RESTART · F EXIT · L FLOWS"
        if (
            self.state is not None
            and self.state.frontier is not None
            and self.state.frontier.kind is not FrontierKind.NEEDS_FIRST_RULE
        ):
            return "A ADD EXCEPTION · S RESTART · F EXIT · L FLOWS"
        else:
            return "A SET DEFAULT · S RESTART · F EXIT · L FLOWS"

    def _apply_layout_mode(self, mode: QuizLayoutMode) -> None:
        for class_name in (
            "layout-landscape",
            "layout-portrait",
            "layout-compact",
        ):
            self.remove_class(class_name)
        self.add_class(f"layout-{mode.value}")
        self.layout_mode = mode

    def _set_phase(self, phase: QuizUiPhase) -> None:
        for class_name in (
            "phase-asking",
            "phase-feedback",
            "phase-frontier",
            "phase-error",
        ):
            self.remove_class(class_name)
        self.phase = phase
        if phase is QuizUiPhase.ASKING:
            self.add_class("phase-asking")
        elif phase in {
            QuizUiPhase.CORRECT_FEEDBACK,
            QuizUiPhase.MISMATCH_FEEDBACK,
        }:
            self.add_class("phase-feedback")
        elif phase is QuizUiPhase.FRONTIER:
            self.add_class("phase-frontier")
        elif phase is QuizUiPhase.ERROR:
            self.add_class("phase-error")


def _format_line(line_san: tuple[str, ...]) -> str:
    if not line_san:
        return "Starting position"
    output: list[str] = []
    for index, san in enumerate(line_san):
        if index % 2 == 0:
            output.append(f"{(index // 2) + 1}. {san}")
        else:
            output.append(san)
    return " ".join(output)


def _truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return f"…{value[-(limit - 1):]}"
