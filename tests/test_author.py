from __future__ import annotations

import asyncio
from pathlib import Path
import shutil

from chess_tui import AppMode, DEFAULT_STARTING_FEN, parse_fen
from chess_tui.flow import FlowStore, WhiteFlow
from chess_tui.game import square_from_name
from chess_tui.layout import QuizLayoutMode
from chess_tui.renderers.factory import create_piece_renderer
from chess_tui.renderers.mode import RendererMode
from chess_tui.screens.author import AuthorPhase, AuthorScreen, RuleDecision
from chess_tui.runtime import TerminalCapabilityError
from chess_tui.tui import ChessTui

PROJECT_ROOT = Path(__file__).parents[1]
LONDON_FLOW = PROJECT_ROOT / "flows" / "london.toml"


def _play(screen: AuthorScreen, uci: str) -> None:
    screen.controller.handle_square(square_from_name(uci[:2]))
    screen.controller.handle_square(square_from_name(uci[2:4]))
    screen.action_confirm_move()


def test_author_defines_consecutive_defaults_in_empty_flow(tmp_path: Path) -> None:
    async def run_test() -> None:
        path = tmp_path / "empty.toml"
        FlowStore().save(
            path,
            WhiteFlow(1, "Empty London", DEFAULT_STARTING_FEN, (), ()),
        )
        app = ChessTui(
            parse_fen(DEFAULT_STARTING_FEN),
            mode=AppMode.AUTHOR,
            renderer=create_piece_renderer(RendererMode.UNICODE),
            flow_path=path,
        )
        screen = app.initial_screen
        assert isinstance(screen, AuthorScreen)

        async with app.run_test(size=(120, 42)) as pilot:
            await pilot.pause()
            assert screen.phase is AuthorPhase.WHITE_MOVE
            assert screen.recommendation is None
            assert "phase=white-move" in screen.debug_status.render_line(0).text
            assert "white_step=1" in screen.debug_status.render_line(0).text

            _play(screen, "d2d4")
            await pilot.pause()
            assert screen.phase is AuthorPhase.CHOOSE_RULE_CHANGE
            assert screen.pending_change is not None
            assert screen.pending_change.decision is RuleDecision.DEFINE_DEFAULT
            assert screen.board.geometry is not None
            screen.note_input.value = "Control the center."
            assert await pilot.click("#save-default")
            await pilot.pause()

            assert screen.phase is AuthorPhase.BLACK_MOVE
            assert "phase=black-move" in screen.debug_status.render_line(0).text
            assert "turn=black" in screen.debug_status.render_line(0).text
            assert FlowStore().load(path).defaults[0].move_san == "d4"

            _play(screen, "d7d5")
            await pilot.pause()
            assert screen.phase is AuthorPhase.WHITE_MOVE
            assert screen.recommendation is None

            _play(screen, "c1f4")
            await pilot.pause()
            screen.note_input.value = "Develop outside the pawn chain."
            assert await pilot.click("#save-default")
            await pilot.pause()

            defaults = FlowStore().load(path).defaults
            assert [(rule.step, rule.move_san) for rule in defaults] == [
                (1, "d4"),
                (2, "Bf4"),
            ]

    asyncio.run(run_test())


def test_author_q_quits_when_note_editor_is_hidden(tmp_path: Path) -> None:
    async def run_test() -> None:
        path = tmp_path / "london.toml"
        shutil.copy2(LONDON_FLOW, path)
        app = ChessTui(
            parse_fen(DEFAULT_STARTING_FEN),
            mode=AppMode.AUTHOR,
            renderer=create_piece_renderer(RendererMode.UNICODE),
            flow_path=path,
        )
        screen = app.initial_screen
        assert isinstance(screen, AuthorScreen)

        async with app.run_test(size=(120, 42)) as pilot:
            await pilot.pause()
            assert screen.note_input.disabled

            await pilot.press("q")
            await pilot.pause()

            assert not app.is_running

    asyncio.run(run_test())


def test_author_persists_exact_exception_and_reloads_note(tmp_path: Path) -> None:
    async def run_test() -> None:
        path = tmp_path / "london.toml"
        shutil.copy2(LONDON_FLOW, path)
        app = ChessTui(
            parse_fen(DEFAULT_STARTING_FEN),
            mode=AppMode.AUTHOR,
            renderer=create_piece_renderer(RendererMode.UNICODE),
            flow_path=path,
        )
        screen = app.initial_screen
        assert isinstance(screen, AuthorScreen)

        async with app.run_test(size=(120, 42)) as pilot:
            await pilot.pause()
            assert screen.recommendation is not None
            assert screen.recommendation.move_san == "d4"

            _play(screen, "d2d4")
            _play(screen, "e7e5")
            await pilot.pause()
            assert screen.recommendation is not None
            assert screen.recommendation.move_san == "Bf4"
            assert screen.recommendation.source == "default"
            assert "rule=default:Bf4" in screen.debug_status.render_line(0).text

            _play(screen, "d4e5")
            await pilot.pause()
            assert screen.phase is AuthorPhase.CHOOSE_RULE_CHANGE
            assert screen.pending_change is not None
            assert screen.pending_change.decision is RuleDecision.DIFFERENT_FROM_DEFAULT
            assert screen.board.geometry is not None
            screen.note_input.value = "Capture the offered pawn."
            assert await pilot.click("#add-exception")
            await pilot.pause()

            saved = FlowStore().load(path)
            assert len(saved.exceptions) == 1
            exception = saved.exceptions[0]
            assert exception.id == "after-d4-e5"
            assert exception.after_san == ("d4", "e5")
            assert exception.move_san == "dxe5"

            screen.action_restart_line()
            _play(screen, "d2d4")
            _play(screen, "d7d5")
            await pilot.pause()
            assert screen.recommendation is not None
            assert screen.recommendation.move_san == "Bf4"
            assert screen.recommendation.source == "default"

            screen.action_restart_line()
            _play(screen, "d2d4")
            _play(screen, "e7e5")
            await pilot.pause()
            assert screen.recommendation is not None
            assert screen.recommendation.move_san == "dxe5"
            assert screen.recommendation.source == "exception"

            text = path.read_text(encoding="utf-8").replace(
                "Capture the offered pawn.",
                "Reloaded note from disk.",
            )
            path.write_text(text, encoding="utf-8")
            screen.action_reload_flow()
            await pilot.pause()

            assert screen.failure is None
            assert screen.recommendation is not None
            assert screen.recommendation.note == "Reloaded note from disk."

            active_flow = screen.author.flow
            path.write_text("version = 99\n", encoding="utf-8")
            screen.action_reload_flow()
            await pilot.pause()

            assert screen.failure is not None
            assert screen.author.flow is active_flow
            assert screen.controller.board.fen() != chess_start_fen()

    asyncio.run(run_test())


def test_author_resize_preserves_line_and_renderer(tmp_path: Path) -> None:
    async def run_test() -> None:
        path = tmp_path / "london.toml"
        shutil.copy2(LONDON_FLOW, path)
        renderer = create_piece_renderer(RendererMode.PIXEL_MASK)
        app = ChessTui(
            parse_fen(DEFAULT_STARTING_FEN),
            mode=AppMode.AUTHOR,
            renderer=renderer,
            flow_path=path,
        )
        screen = app.initial_screen
        assert isinstance(screen, AuthorScreen)

        async with app.run_test(size=(120, 42)) as pilot:
            await pilot.pause()
            _play(screen, "d2d4")
            assert screen.history == ["d4"]
            assert screen.layout_mode is QuizLayoutMode.LANDSCAPE

            await pilot.resize_terminal(80, 52)
            await pilot.pause()
            assert screen.layout_mode is QuizLayoutMode.PORTRAIT
            assert screen.history == ["d4"]

            await pilot.resize_terminal(70, 40)
            await pilot.pause()
            assert screen.layout_mode is QuizLayoutMode.COMPACT
            assert screen.board.geometry is not None
            assert screen.renderer is renderer

            await pilot.resize_terminal(60, 30)
            await pilot.pause()
            assert isinstance(screen.failure, TerminalCapabilityError)
            assert screen.board.geometry is None
            assert screen.history == ["d4"]

            await pilot.resize_terminal(120, 42)
            await pilot.pause()
            assert screen.failure is None
            assert screen.board.geometry is not None
            assert screen.renderer is renderer
            assert screen.history == ["d4"]

    asyncio.run(run_test())


def chess_start_fen() -> str:
    return "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
