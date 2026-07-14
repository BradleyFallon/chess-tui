"""ChessFlow-shaped local fixture quiz screen."""

from __future__ import annotations

from collections.abc import Callable
from enum import Enum

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.events import Key, Resize
from textual.screen import Screen
from textual.timer import Timer
from textual.widgets import Static

from ..board import DEFAULT_STARTING_FEN, parse_fen
from ..renderers.base import PieceRenderer
from ..renderers.colors import LABEL_COLOR, SCREEN_BACKGROUND, STATUS_BACKGROUND
from ..runtime import TerminalCapabilityError
from ..sessions.base import QuizSession
from ..sessions.demo import DemoFlowSummary, DemoQuizSession, list_demo_flows
from ..sessions.errors import SessionError
from ..sessions.models import QuizPhase, QuizSessionState
from ..tui import ChessBoard
from ..view import BoardInputMode, board_view_from_quiz_state
from ..widgets.choice_panel import ChoicePanel
from ..widgets.feedback import FeedbackPanel
from ..widgets.frontier import FrontierPanel
from .base import RendererController
from .modals import ContinuationModal, FlowPickerModal


class QuizUiPhase(str, Enum):
    LOADING = "loading"
    ASKING = "asking"
    SUBMITTING = "submitting"
    CORRECT_FEEDBACK = "correct-feedback"
    MISMATCH_FEEDBACK = "mismatch-feedback"
    FRONTIER = "frontier"
    ERROR = "error"


SessionFactory = Callable[[str], QuizSession]


class QuizScreen(Screen[None]):
    AUTO_ADVANCE_SECONDS = 0.6
    CSS = f"""
    QuizScreen {{ background: {SCREEN_BACKGROUND}; }}
    QuizScreen > #quiz-header {{
        dock: top; height: 1; color: {LABEL_COLOR}; background: {STATUS_BACKGROUND};
        text-style: bold; padding: 0 1;
    }}
    QuizScreen > #quiz-layout {{ height: 1fr; align: center middle; }}
    QuizScreen ChessBoard {{ margin: 0 1; }}
    QuizScreen #quiz-side {{ width: 1fr; min-width: 28; padding: 1 2; }}
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
    QuizScreen > #quiz-status {{
        dock: bottom; height: 1; color: {LABEL_COLOR}; background: {STATUS_BACKGROUND};
        text-align: center;
    }}
    """
    BINDINGS = [("q", "app.quit", "Quit")]

    def __init__(
        self,
        session: QuizSession,
        flow: DemoFlowSummary,
        renderer: PieceRenderer,
        *,
        session_factory: SessionFactory = DemoQuizSession,
    ) -> None:
        super().__init__()
        self.session = session
        self.flow = flow
        self.session_factory = session_factory
        self.renderer_controller = RendererController(renderer)
        self.board = ChessBoard(
            parse_fen(DEFAULT_STARTING_FEN),
            renderer=renderer,
            input_mode=BoardInputMode.READ_ONLY,
        )
        self.header = Static("", id="quiz-header")
        self.line = Static("")
        self.prompt = Static("")
        self.choice_panel = ChoicePanel()
        self.feedback_panel = FeedbackPanel("")
        self.frontier_panel = FrontierPanel("")
        self.status = Static("", id="quiz-status")
        self.phase = QuizUiPhase.LOADING
        self.state: QuizSessionState | None = None
        self.score = 0
        self.streak = 0
        self.failure: Exception | None = None
        self._feedback_timer: Timer | None = None
        self._generation = 0
        self._demo_result: str | None = None

    @property
    def renderer(self) -> PieceRenderer:
        return self.renderer_controller.active

    def compose(self) -> ComposeResult:
        yield self.header
        with Horizontal(id="quiz-layout"):
            yield self.board
            with Vertical(id="quiz-side"):
                yield Static("POSITION", classes="section-label")
                yield self.line
                yield Static("SELECT YOUR MOVE", classes="section-label")
                yield self.prompt
                yield self.choice_panel
                yield self.feedback_panel
                yield self.frontier_panel
        yield self.status

    async def on_mount(self) -> None:
        self.feedback_panel.clear_feedback()
        self.frontier_panel.clear_frontier()
        await self._start_session()

    async def on_unmount(self) -> None:
        self._cancel_feedback_timer()
        await self.session.close()

    def on_resize(self, event: Resize) -> None:
        try:
            renderer, geometry = self.renderer_controller.choose(
                event.size, event.pixel_size, reserved_rows=2
            )
        except TerminalCapabilityError as exc:
            self.failure = exc
            self.board.unconfigure()
            self.status.update(str(exc).replace("\n", " "))
            return
        self.board.renderer = renderer
        self.board.configure(geometry)
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
        if key == "enter" and self.phase in {
            QuizUiPhase.CORRECT_FEEDBACK,
            QuizUiPhase.MISMATCH_FEEDBACK,
        }:
            event.stop()
            await self._continue_after_feedback()
            return
        if self.phase is QuizUiPhase.FRONTIER:
            if key == "a":
                event.stop()
                self.action_add_continuation()
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
        self.phase = QuizUiPhase.SUBMITTING
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
        self.feedback_panel.show_feedback(feedback)
        if feedback.correct:
            self.score += 1
            self.streak += 1
            self.phase = QuizUiPhase.CORRECT_FEEDBACK
            self._schedule_auto_continue()
        else:
            self.streak = 0
            self.phase = QuizUiPhase.MISMATCH_FEEDBACK
        self._refresh_header()
        self._update_status()

    def action_select_flow(self) -> None:
        self.app.push_screen(
            FlowPickerModal(list_demo_flows(), self.flow.id),
            self._flow_selected,
        )

    def action_add_continuation(self) -> None:
        if self.phase is QuizUiPhase.FRONTIER:
            self.app.push_screen(ContinuationModal(), self._continuation_collected)

    async def _start_session(self) -> None:
        self._cancel_feedback_timer()
        self.phase = QuizUiPhase.LOADING
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
        self.phase = QuizUiPhase.LOADING
        self.score = 0
        self.streak = 0
        self._demo_result = None
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
        self.phase = QuizUiPhase.SUBMITTING
        self._update_status()
        try:
            state = await self.session.continue_session()
        except SessionError as exc:
            self._show_error(exc)
            return
        self._apply_state(state)

    def _apply_state(self, state: QuizSessionState) -> None:
        self._generation += 1
        self.state = state
        self.board.update_view(board_view_from_quiz_state(state), flipped=False)
        self.line.update(_format_line(state.line_san))
        self.feedback_panel.clear_feedback()
        self.frontier_panel.clear_frontier()
        if state.phase is QuizPhase.QUESTION and state.question is not None:
            self.phase = QuizUiPhase.ASKING
            self.prompt.update(state.question.prompt)
            self.choice_panel.set_choices(state.question.choices)
            self.choice_panel.focus()
        elif state.phase is QuizPhase.FRONTIER and state.frontier is not None:
            self.phase = QuizUiPhase.FRONTIER
            self.prompt.update("")
            self.choice_panel.clear()
            self.frontier_panel.show_frontier(
                state.frontier, demo_result=self._demo_result
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
        self.phase = QuizUiPhase.ERROR
        self.choice_panel.clear()
        self.prompt.update(f"SESSION ERROR\n\n{error}\n\n[R] Retry  [Q] Quit")
        self._update_status()

    def _refresh_header(self) -> None:
        self.header.update(
            f"{self.flow.name.upper()} · {self.flow.side.upper()}"
            f"    SCORE {self.score}    STREAK {self.streak}"
        )

    def _update_status(self) -> None:
        renderer = self.renderer.mode.value
        if self.renderer_controller.fallback_active:
            renderer += " fallback"
        instructions = {
            QuizUiPhase.LOADING: "LOADING",
            QuizUiPhase.ASKING: "A/S/D/F HIGHLIGHT · ENTER CONFIRM · L FLOWS",
            QuizUiPhase.SUBMITTING: "SUBMITTING",
            QuizUiPhase.CORRECT_FEEDBACK: "ENTER CONTINUE NOW",
            QuizUiPhase.MISMATCH_FEEDBACK: "ENTER CONTINUE",
            QuizUiPhase.FRONTIER: "A ADD · S RESTART · F EXIT · L FLOWS",
            QuizUiPhase.ERROR: "R RETRY · Q QUIT",
        }[self.phase]
        self.status.update(f"Renderer: {renderer} · {instructions} · Q QUIT")

    def _flow_selected(self, flow_id: str | None) -> None:
        if flow_id is not None and flow_id != self.flow.id:
            self.run_worker(self._switch_flow(flow_id), exclusive=True)

    async def _switch_flow(self, flow_id: str) -> None:
        await self.session.close()
        self.session = self.session_factory(flow_id)
        self.flow = next(flow for flow in list_demo_flows() if flow.id == flow_id)
        self.score = 0
        self.streak = 0
        self._demo_result = None
        await self._start_session()

    def _continuation_collected(self, result: dict[str, str] | None) -> None:
        if result is None or self.state is None or self.state.frontier is None:
            return
        self._demo_result = (
            f"{result['opponent']} → {result['response']} " f"({result['selection']})"
        )
        if result["note"]:
            self._demo_result += f" · {result['note']}"
        self.frontier_panel.show_frontier(
            self.state.frontier, demo_result=self._demo_result
        )


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
