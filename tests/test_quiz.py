from __future__ import annotations

import asyncio

from textual.app import App, ComposeResult

from chess_tui import AppMode, DEFAULT_STARTING_FEN
from chess_tui.layout import QuizLayoutMode
from chess_tui.renderers.factory import create_piece_renderer
from chess_tui.renderers.mode import RendererMode
from chess_tui.screens.quiz import QuizScreen, QuizUiPhase
from chess_tui.sessions.errors import SessionUnavailableError
from chess_tui.sessions.models import (
    ContinuationDraft,
    FlowSummary,
    FrontierKind,
    FrontierState,
    MoveChoice,
    QuizFeedback,
    QuizPhase,
    QuizQuestion,
    QuizSessionState,
    RuleType,
)
from chess_tui.runtime import TerminalCapabilityError
from chess_tui.tui import ChessTui
from chess_tui.view import BoardInputMode
from chess_tui.widgets.choice_panel import ChoicePanel
from chess_tui.widgets.continuation import ContinuationEditor


class ChoicePanelTestApp(App[None]):
    def __init__(self) -> None:
        super().__init__()
        self.panel = ChoicePanel()
        self.submitted: list[str] = []

    def compose(self) -> ComposeResult:
        yield self.panel

    def on_mount(self) -> None:
        self.panel.set_choices(
            (
                MoveChoice("a", "Bf4", "c1f4"),
                MoveChoice("s", "Nf3", "g1f3"),
                MoveChoice("d", "c4", "c2c4"),
                MoveChoice("f", "e3", "e2e3"),
            )
        )
        self.panel.focus()

    def on_choice_panel_choice_submitted(
        self, message: ChoicePanel.ChoiceSubmitted
    ) -> None:
        self.submitted.append(message.choice.id)


def _question_state(prompt: str = "Choose") -> QuizSessionState:
    return QuizSessionState(
        phase=QuizPhase.QUESTION,
        fen=DEFAULT_STARTING_FEN,
        line_san=(),
        question=QuizQuestion(
            "root",
            prompt,
            (
                MoveChoice("a", "e4", "e2e4"),
                MoveChoice("s", "d4", "d2d4"),
            ),
        ),
    )


class FakeQuizSession:
    def __init__(self, prompt: str) -> None:
        self.prompt = prompt
        self.closed = False
        self.start_calls = 0

    async def start(self) -> QuizSessionState:
        self.start_calls += 1
        return _question_state(self.prompt)

    async def answer(self, question_id: str, choice_id: str) -> QuizSessionState:
        state = _question_state(self.prompt)
        assert state.question is not None
        choice = next(
            choice for choice in state.question.choices if choice.id == choice_id
        )
        return QuizSessionState(
            phase=QuizPhase.CORRECT_FEEDBACK,
            fen=state.fen,
            line_san=state.line_san,
            question=state.question,
            feedback=QuizFeedback(True, choice.san, choice.san, None),
        )

    async def continue_session(self) -> QuizSessionState:
        return _question_state(self.prompt)

    async def restart(self) -> QuizSessionState:
        return await self.start()

    async def close(self) -> None:
        self.closed = True


class FakeQuizProvider:
    def __init__(self, *, fail_listing: bool = False) -> None:
        self.flows = (
            FlowSummary("alpha", "Alpha", "white"),
            FlowSummary("beta", "Beta", "black"),
        )
        self.fail_listing = fail_listing
        self.select_calls: list[str] = []
        self.create_calls: list[str] = []
        self.sessions: list[FakeQuizSession] = []
        self.closed = False

    async def list_flows(self) -> tuple[FlowSummary, ...]:
        if self.fail_listing:
            raise SessionUnavailableError("flow list unavailable")
        return self.flows

    async def active_flow(self) -> FlowSummary:
        return self.flows[0]

    async def select_flow(self, flow_id: str) -> FlowSummary:
        self.select_calls.append(flow_id)
        return next(flow for flow in self.flows if flow.id == flow_id)

    async def create_session(self, flow_id: str) -> FakeQuizSession:
        self.create_calls.append(flow_id)
        session = FakeQuizSession(f"Question from {flow_id}")
        self.sessions.append(session)
        return session

    async def close(self) -> None:
        self.closed = True


class QuizScreenTestApp(App[None]):
    def __init__(self, screen: QuizScreen) -> None:
        super().__init__()
        self.quiz_screen = screen

    def on_mount(self) -> None:
        self.push_screen(self.quiz_screen)


class ContinuationEditorTestApp(App[None]):
    def __init__(self, frontier: FrontierState) -> None:
        super().__init__()
        self.frontier = frontier
        self.editor = ContinuationEditor()
        self.result: ContinuationDraft | None = None

    def compose(self) -> ComposeResult:
        yield self.editor

    def on_mount(self) -> None:
        self.editor.show_editor(self.frontier)

    def on_continuation_editor_submitted(
        self, message: ContinuationEditor.Submitted
    ) -> None:
        self.result = message.draft


def test_choice_panel_keyboard_hover_click_and_double_submit_guard() -> None:
    async def run_test() -> None:
        app = ChoicePanelTestApp()
        async with app.run_test(size=(40, 20)) as pilot:
            await pilot.press("s")
            assert app.panel.highlighted_index == 1
            assert app.submitted == []

            await pilot.press("enter")
            await pilot.pause()
            assert app.submitted == ["s"]

            await pilot.press("enter")
            await pilot.pause()
            assert app.submitted == ["s"]

            app.panel.set_submission_enabled(True)
            assert await pilot.hover("#choice-d")
            await pilot.pause()
            assert app.panel.highlighted_index == 2

            assert await pilot.click("#choice-d")
            await pilot.pause()
            assert app.submitted == ["s", "d"]

    asyncio.run(run_test())


def test_continuation_editor_fields_follow_frontier_kind() -> None:
    async def run_test() -> None:
        first_rule = FrontierState(
            FrontierKind.NEEDS_FIRST_RULE,
            DEFAULT_STARTING_FEN,
            (),
        )
        first_app = ContinuationEditorTestApp(first_rule)
        async with first_app.run_test(size=(80, 30)) as pilot:
            await pilot.pause()
            assert not first_app.editor.opponent.display
            first_app.editor.response.value = "d4"
            assert await pilot.click("#submit")
            await pilot.pause()

        assert first_app.result == ContinuationDraft("d4", RuleType.DEFAULT)

        user_response = FrontierState(
            FrontierKind.NEEDS_USER_RESPONSE,
            DEFAULT_STARTING_FEN,
            ("e4", "e5"),
            opponent_move_san="e5",
        )
        response_app = ContinuationEditorTestApp(user_response)
        async with response_app.run_test(size=(80, 30)) as pilot:
            await pilot.pause()
            assert not response_app.editor.opponent.display
            response_app.editor.response.value = "Nf3"
            assert await pilot.click("#submit")
            await pilot.pause()

        assert response_app.result == ContinuationDraft(
            "Nf3", RuleType.EXACT, opponent_move_san="e5"
        )

    asyncio.run(run_test())


def test_quiz_screen_correct_mismatch_and_canonical_progression() -> None:
    async def run_test() -> None:
        renderer = create_piece_renderer(RendererMode.UNICODE)
        app = ChessTui(mode=AppMode.QUIZ_DEMO, renderer=renderer)
        screen = app.initial_screen
        assert isinstance(screen, QuizScreen)

        async with app.run_test(size=(120, 42)) as pilot:
            await pilot.pause()
            assert screen.phase is QuizUiPhase.ASKING
            assert screen.board.input_mode is BoardInputMode.READ_ONLY
            assert screen.state is not None and screen.state.line_san == ()

            await pilot.press("s", "enter")
            await pilot.pause()
            assert screen.phase is QuizUiPhase.CORRECT_FEEDBACK
            assert screen.streak == 1

            await pilot.press("enter")
            await pilot.pause()
            assert screen.phase is QuizUiPhase.ASKING
            assert screen.state is not None
            assert screen.state.line_san == ("d4", "d5")

            await pilot.press("s", "enter")
            await pilot.pause()
            assert screen.phase is QuizUiPhase.MISMATCH_FEEDBACK
            assert screen.streak == 0
            await pilot.pause(0.7)
            assert screen.phase is QuizUiPhase.MISMATCH_FEEDBACK

            await pilot.press("enter")
            await pilot.pause()
            assert screen.phase is QuizUiPhase.ASKING
            assert screen.state is not None
            assert screen.state.line_san == ("d4", "d5", "Bf4", "Nf6")

    asyncio.run(run_test())


def test_quiz_mismatch_can_make_selected_move_correct() -> None:
    async def run_test() -> None:
        renderer = create_piece_renderer(RendererMode.UNICODE)
        app = ChessTui(mode=AppMode.QUIZ_DEMO, renderer=renderer)
        screen = app.initial_screen
        assert isinstance(screen, QuizScreen)

        async with app.run_test(size=(120, 42)) as pilot:
            await pilot.pause()
            await pilot.press("a", "enter")
            await pilot.pause()
            assert screen.phase is QuizUiPhase.MISMATCH_FEEDBACK
            assert screen.state is not None
            assert screen.state.feedback is not None
            assert screen.state.feedback.selected_san == "e4"

            await pilot.press("e")
            await pilot.pause()
            assert screen.phase is QuizUiPhase.CORRECT_FEEDBACK
            assert screen.score == 1
            assert screen.streak == 1
            assert screen.state is not None
            assert screen.state.feedback is not None
            assert screen.state.feedback.expected_san == "e4"
            assert "this quiz session" in (screen.state.feedback.explanation or "")

            await pilot.press("enter")
            await pilot.pause()
            assert screen.phase is QuizUiPhase.FRONTIER
            assert screen.state is not None
            assert screen.state.line_san == ("e4",)

    asyncio.run(run_test())


def test_quiz_correct_feedback_auto_advances_and_flow_picker_switches() -> None:
    async def run_test() -> None:
        renderer = create_piece_renderer(RendererMode.UNICODE)
        app = ChessTui(mode=AppMode.QUIZ_DEMO, renderer=renderer)
        screen = app.initial_screen
        assert isinstance(screen, QuizScreen)

        async with app.run_test(size=(120, 42)) as pilot:
            await pilot.pause()
            await pilot.press("s", "enter")
            await pilot.pause(0.7)
            assert screen.phase is QuizUiPhase.ASKING
            assert screen.state is not None
            assert screen.state.line_san == ("d4", "d5")

            await pilot.press("l")
            await pilot.pause()
            await pilot.press("down", "enter")
            await pilot.pause()
            assert screen.flow.id == "caro-kann-demo"
            assert screen.state is not None
            assert screen.state.line_san == ("e4",)

    asyncio.run(run_test())


def test_quiz_reaches_frontier_previews_mock_continuation_and_restarts() -> None:
    async def run_test() -> None:
        renderer = create_piece_renderer(RendererMode.UNICODE)
        app = ChessTui(mode=AppMode.QUIZ_DEMO, renderer=renderer)
        screen = app.initial_screen
        assert isinstance(screen, QuizScreen)

        async with app.run_test(size=(120, 42)) as pilot:
            await pilot.pause()
            for choice_key in ("s", "a", "s"):
                await pilot.press(choice_key, "enter")
                await pilot.pause()
                assert screen.phase is QuizUiPhase.CORRECT_FEEDBACK
                await pilot.press("enter")
                await pilot.pause()

            assert screen.phase is QuizUiPhase.FRONTIER
            assert screen.state is not None and screen.state.frontier is not None

            await pilot.press("a")
            await pilot.pause()
            assert app.screen is screen
            assert screen.board.geometry is not None
            editor = screen.continuation_editor
            assert editor.display
            assert not editor.opponent.display
            editor.response.value = "e3"
            editor.note.value = "Main plan"
            assert await pilot.click("#submit")
            await pilot.pause()

            assert screen._continuation_rules == [
                ContinuationDraft("e3", RuleType.DEFAULT, note="Main plan")
            ]

            await pilot.press("a")
            await pilot.pause()
            assert app.screen is screen
            assert screen.board.geometry is not None
            assert editor.display
            assert editor.opponent.display
            editor.opponent.value = "e6"
            editor.response.value = "c4"
            editor.note.value = "Branch plan"
            assert await pilot.click("#submit")
            await pilot.pause()

            assert screen._continuation_rules == [
                ContinuationDraft("e3", RuleType.DEFAULT, note="Main plan"),
                ContinuationDraft(
                    "c4",
                    RuleType.EXACT,
                    opponent_move_san="e6",
                    note="Branch plan",
                ),
            ]

            await pilot.press("a")
            await pilot.pause()
            assert app.screen is screen
            assert screen.board.geometry is not None
            editor.opponent.value = "e6"
            editor.response.value = "c3"
            assert await pilot.click("#submit")
            await pilot.pause()

            assert len(screen._continuation_rules) == 2
            assert screen._continuation_rules[1] == ContinuationDraft(
                "c3", RuleType.EXACT, opponent_move_san="e6"
            )

            await pilot.press("d")
            await pilot.pause()
            assert app.screen is screen
            assert screen.board.geometry is not None
            assert editor.response.value == "e3"
            editor.response.value = "Nf3"
            assert await pilot.click("#submit")
            await pilot.pause()

            assert screen._continuation_rules[0].response_move_san == "Nf3"
            assert len(screen._continuation_rules) == 2

            await pilot.press("s")
            await pilot.pause()
            assert screen.phase is QuizUiPhase.ASKING
            assert screen.score == 0
            assert screen.streak == 0
            assert screen._continuation_rules == []
            assert screen.state is not None and screen.state.line_san == ()

    asyncio.run(run_test())


def test_compact_continuation_editor_keeps_board_visible() -> None:
    async def run_test() -> None:
        renderer = create_piece_renderer(RendererMode.PIXEL_MASK)
        app = ChessTui(mode=AppMode.QUIZ_DEMO, renderer=renderer)
        screen = app.initial_screen
        assert isinstance(screen, QuizScreen)

        async with app.run_test(size=(120, 42)) as pilot:
            await pilot.pause()
            for choice_key in ("s", "a", "s"):
                await pilot.press(choice_key, "enter")
                await pilot.pause()
                await pilot.press("enter")
                await pilot.pause()

            assert screen.phase is QuizUiPhase.FRONTIER
            await pilot.resize_terminal(70, 40)
            await pilot.pause()
            assert screen.layout_mode is QuizLayoutMode.COMPACT

            await pilot.press("a")
            await pilot.pause()

            assert app.screen is screen
            assert screen.board.geometry is not None
            assert screen.board.region.height > 0
            assert screen.continuation_editor.display
            assert screen.continuation_editor.region.height == 4

    asyncio.run(run_test())


def test_quiz_resize_preserves_renderer_state_choice_flow_and_timer() -> None:
    async def run_test() -> None:
        renderer = create_piece_renderer(RendererMode.PIXEL_MASK)
        app = ChessTui(mode=AppMode.QUIZ_DEMO, renderer=renderer)
        screen = app.initial_screen
        assert isinstance(screen, QuizScreen)

        async with app.run_test(size=(120, 42)) as pilot:
            await pilot.pause()
            original_state = screen.state
            original_panel = screen.choice_panel
            original_flow = screen.flow
            assert screen.layout_mode is QuizLayoutMode.LANDSCAPE

            await pilot.press("s")
            assert screen.choice_panel.highlighted_index == 1

            await pilot.resize_terminal(80, 52)
            await pilot.pause()
            assert screen.layout_mode is QuizLayoutMode.PORTRAIT
            assert screen.state is original_state
            assert screen.choice_panel is original_panel
            assert screen.choice_panel.highlighted_index == 1

            await pilot.resize_terminal(70, 40)
            await pilot.pause()
            assert screen.layout_mode is QuizLayoutMode.COMPACT
            assert screen.renderer is renderer
            assert screen.flow is original_flow
            assert screen.score == 0

            await pilot.resize_terminal(60, 30)
            await pilot.pause()
            assert isinstance(screen.failure, TerminalCapabilityError)
            assert screen.board.geometry is None
            assert screen.state is original_state
            assert screen.choice_panel.highlighted_index == 1

            await pilot.resize_terminal(120, 42)
            await pilot.pause()
            assert screen.failure is None
            assert screen.layout_mode is QuizLayoutMode.LANDSCAPE
            assert screen.renderer is renderer
            assert screen.state is original_state
            assert screen.choice_panel.highlighted_index == 1

            await pilot.press("enter")
            await pilot.pause()
            assert screen.phase is QuizUiPhase.CORRECT_FEEDBACK
            assert screen.score == 1

            await pilot.resize_terminal(80, 52)
            await pilot.pause(0.7)
            assert screen.layout_mode is QuizLayoutMode.PORTRAIT
            assert screen.phase is QuizUiPhase.ASKING
            assert screen.state is not None
            assert screen.state.line_san == ("d4", "d5")
            assert screen.flow is original_flow
            assert screen.score == 1

    asyncio.run(run_test())


def test_quiz_screen_uses_provider_for_flow_selection_and_closes_resources() -> None:
    async def run_test() -> None:
        provider = FakeQuizProvider()
        flow = await provider.active_flow()
        initial_session = await provider.create_session(flow.id)
        screen = QuizScreen(
            provider,
            flow,
            initial_session,
            create_piece_renderer(RendererMode.UNICODE),
        )
        app = QuizScreenTestApp(screen)

        async with app.run_test(size=(120, 42)) as pilot:
            await pilot.pause()
            assert screen.phase is QuizUiPhase.ASKING
            assert screen.flow is flow
            assert initial_session.start_calls == 1

            await pilot.press("l")
            await pilot.pause()
            await pilot.press("down", "enter")
            await pilot.pause()

            assert provider.select_calls == ["beta"]
            assert provider.create_calls == ["alpha", "beta"]
            assert initial_session.closed
            assert screen.flow is provider.flows[1]
            assert screen.session is provider.sessions[1]
            assert screen.state is not None
            assert screen.state.question is not None
            assert screen.state.question.prompt == "Question from beta"

        assert provider.sessions[1].closed
        assert provider.closed

    asyncio.run(run_test())


def test_quiz_screen_enters_error_phase_when_provider_flow_list_fails() -> None:
    async def run_test() -> None:
        provider = FakeQuizProvider(fail_listing=True)
        flow = await provider.active_flow()
        session = await provider.create_session(flow.id)
        screen = QuizScreen(
            provider,
            flow,
            session,
            create_piece_renderer(RendererMode.UNICODE),
        )
        app = QuizScreenTestApp(screen)

        async with app.run_test(size=(120, 42)) as pilot:
            await pilot.pause()
            await pilot.press("l")
            await pilot.pause()

            assert screen.phase is QuizUiPhase.ERROR
            assert isinstance(screen.failure, SessionUnavailableError)
            assert str(screen.failure) == "flow list unavailable"

    asyncio.run(run_test())
