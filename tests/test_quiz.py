from __future__ import annotations

import asyncio

from textual.app import App, ComposeResult
from textual.widgets import Input

from chess_tui import AppMode
from chess_tui.renderers.factory import create_piece_renderer
from chess_tui.renderers.mode import RendererMode
from chess_tui.screens.quiz import QuizScreen, QuizUiPhase
from chess_tui.screens.modals import ContinuationModal
from chess_tui.sessions.models import MoveChoice
from chess_tui.tui import ChessTui
from chess_tui.view import BoardInputMode
from chess_tui.widgets.choice_panel import ChoicePanel


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
            for choice_key in ("s", "a", "a"):
                await pilot.press(choice_key, "enter")
                await pilot.pause()
                assert screen.phase is QuizUiPhase.CORRECT_FEEDBACK
                await pilot.press("enter")
                await pilot.pause()

            assert screen.phase is QuizUiPhase.FRONTIER
            assert screen.state is not None and screen.state.frontier is not None

            await pilot.press("a")
            await pilot.pause()
            modal = app.screen
            assert isinstance(modal, ContinuationModal)
            modal.query_one("#opponent", Input).value = "e6"
            modal.query_one("#response", Input).value = "e3"
            modal.query_one("#note", Input).value = "Sample branch"
            assert await pilot.click("#submit")
            await pilot.pause()

            assert screen._demo_result is not None
            assert "e6 → e3" in screen._demo_result
            assert "Sample branch" in screen._demo_result

            await pilot.press("s")
            await pilot.pause()
            assert screen.phase is QuizUiPhase.ASKING
            assert screen.score == 0
            assert screen.streak == 0
            assert screen.state is not None and screen.state.line_san == ()

    asyncio.run(run_test())
