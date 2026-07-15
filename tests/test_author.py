from __future__ import annotations

import asyncio
from pathlib import Path
import shutil

from chess_tui import AppMode, DEFAULT_STARTING_FEN, parse_fen
from chess_tui.flow import FlowStore
from chess_tui.game import square_from_name
from chess_tui.input_mode import InputMode
from chess_tui.layout import QuizLayoutMode
from chess_tui.renderers.factory import create_piece_renderer
from chess_tui.renderers.mode import RendererMode
from chess_tui.runtime import TerminalCapabilityError
from chess_tui.screens.author import AuthorScreen, FlowPhase
from chess_tui.tui import ChessBoard, ChessTui

PROJECT_ROOT = Path(__file__).parents[1]
LONDON_FLOW = PROJECT_ROOT / "flows" / "london.toml"


def _click_move(screen: AuthorScreen, uci: str) -> None:
    screen.on_chess_board_square_clicked(
        ChessBoard.SquareClicked(square_from_name(uci[:2]))
    )
    screen.on_chess_board_square_clicked(
        ChessBoard.SquareClicked(square_from_name(uci[2:4]))
    )


def _panel_text(screen: AuthorScreen) -> str:
    return "\n".join(screen.panel.render_line(row).text for row in range(30))


async def _submit_board_move(
    screen: AuthorScreen,
    pilot,
    uci: str,
) -> None:
    _click_move(screen, uci)
    await pilot.press("enter")
    await pilot.pause()


async def _play_correct_and_choose_black(
    screen: AuthorScreen,
    pilot,
    white_uci: str,
    black_key: str | None = None,
) -> None:
    await _submit_board_move(screen, pilot, white_uci)
    if screen.phase is FlowPhase.WHITE_RESULT_CORRECT:
        await pilot.press("enter")
        await pilot.pause()
    assert screen.phase is FlowPhase.BLACK_SELECT
    if black_key is not None:
        await pilot.press(black_key)
    await pilot.press("enter")
    await pilot.pause()


def test_flow_hides_known_answer_until_white_submits(tmp_path: Path) -> None:
    async def run_test() -> None:
        path = tmp_path / "london.toml"
        shutil.copy2(LONDON_FLOW, path)
        app = ChessTui(
            parse_fen(DEFAULT_STARTING_FEN),
            mode=AppMode.FLOW,
            renderer=create_piece_renderer(RendererMode.UNICODE),
            flow_path=path,
        )
        screen = app.initial_screen
        assert isinstance(screen, AuthorScreen)

        async with app.run_test(size=(120, 42)) as pilot:
            await pilot.pause()
            assert screen.phase is FlowPhase.WHITE_TEST
            assert "PLAY YOUR MOVE" in _panel_text(screen)
            assert "Recommended" not in _panel_text(screen)
            assert "d4" not in _panel_text(screen)
            assert "rule=hidden" in screen.debug_status.render_line(0).text

            await _submit_board_move(screen, pilot, "d2d4")
            assert screen.phase is FlowPhase.WHITE_RESULT_CORRECT
            assert "CORRECT" in _panel_text(screen)
            assert "d4" in _panel_text(screen)
            assert "Control the center." in _panel_text(screen)
            assert screen.move_input.value == ""

            await pilot.press("enter")
            await pilot.pause()
            assert screen.phase is FlowPhase.BLACK_SELECT
            assert screen.opening_moves.highlighted_move is not None
            assert screen.opening_moves.highlighted_move.san == "d5"

    asyncio.run(run_test())


def test_flow_mismatch_retry_restores_position_and_tests_again(tmp_path: Path) -> None:
    async def run_test() -> None:
        path = tmp_path / "london.toml"
        shutil.copy2(LONDON_FLOW, path)
        app = ChessTui(
            mode=AppMode.FLOW,
            renderer=create_piece_renderer(RendererMode.UNICODE),
            flow_path=path,
        )
        screen = app.initial_screen
        assert isinstance(screen, AuthorScreen)

        async with app.run_test(size=(120, 42)) as pilot:
            await pilot.pause()
            await _submit_board_move(screen, pilot, "e2e4")
            assert screen.phase is FlowPhase.WHITE_RESULT_MISMATCH
            assert screen.history == ["e4"]
            assert "Saved rule:\nd4" in _panel_text(screen)

            await pilot.press("r")
            await pilot.pause()
            assert screen.phase is FlowPhase.WHITE_TEST
            assert screen.history == []
            assert screen.controller.board.piece_at(square_from_name("e2")) is not None
            assert "d4" not in _panel_text(screen)

            await _submit_board_move(screen, pilot, "d2d4")
            assert screen.phase is FlowPhase.WHITE_RESULT_CORRECT

    asyncio.run(run_test())


def test_flow_keep_saved_rule_rolls_back_wrong_move(tmp_path: Path) -> None:
    async def run_test() -> None:
        path = tmp_path / "london.toml"
        shutil.copy2(LONDON_FLOW, path)
        app = ChessTui(
            mode=AppMode.FLOW,
            renderer=create_piece_renderer(RendererMode.UNICODE),
            flow_path=path,
        )
        screen = app.initial_screen
        assert isinstance(screen, AuthorScreen)

        async with app.run_test(size=(120, 42)) as pilot:
            await pilot.pause()
            await _play_correct_and_choose_black(screen, pilot, "d2d4")
            assert screen.phase is FlowPhase.WHITE_TEST

            await _submit_board_move(screen, pilot, "e2e3")
            assert screen.phase is FlowPhase.WHITE_RESULT_MISMATCH
            assert screen.history == ["d4", "d5", "e3"]

            await pilot.press("enter")
            await pilot.pause()
            assert screen.history == ["d4", "d5", "Bf4"]
            assert screen.controller.board.piece_at(square_from_name("f4")) is not None
            assert screen.controller.board.piece_at(square_from_name("e2")) is not None
            assert screen.phase is FlowPhase.BLACK_SELECT

    asyncio.run(run_test())


def test_flow_can_retry_then_edit_selected_move_as_default(tmp_path: Path) -> None:
    async def run_test() -> None:
        path = tmp_path / "london.toml"
        shutil.copy2(LONDON_FLOW, path)
        app = ChessTui(
            mode=AppMode.FLOW,
            renderer=create_piece_renderer(RendererMode.UNICODE),
            flow_path=path,
        )
        screen = app.initial_screen
        assert isinstance(screen, AuthorScreen)

        async with app.run_test(size=(120, 42)) as pilot:
            await pilot.pause()
            await _play_correct_and_choose_black(screen, pilot, "d2d4")
            await _submit_board_move(screen, pilot, "c2c3")
            assert screen.phase is FlowPhase.WHITE_RESULT_MISMATCH

            await pilot.press("d")
            await pilot.pause()
            assert screen.phase is FlowPhase.RULE_NOTE
            assert screen.input.mode is InputMode.TEXT
            screen.note_input.value = "Build the pawn chain first."
            await pilot.press("enter")
            await pilot.pause()
            assert screen.phase is FlowPhase.RULE_NOTE
            assert screen.input.mode is InputMode.NAVIGATION
            await pilot.press("s")
            await pilot.pause()

            assert screen.history == ["d4", "d5", "c3"]
            saved = FlowStore().load(path)
            assert saved.defaults[1].move_san == "c3"
            assert saved.defaults[1].note == "Build the pawn chain first."

    asyncio.run(run_test())


def test_flow_exception_is_hidden_then_keep_applies_it(tmp_path: Path) -> None:
    async def run_test() -> None:
        path = tmp_path / "london.toml"
        shutil.copy2(LONDON_FLOW, path)
        app = ChessTui(
            mode=AppMode.FLOW,
            renderer=create_piece_renderer(RendererMode.UNICODE),
            flow_path=path,
        )
        screen = app.initial_screen
        assert isinstance(screen, AuthorScreen)

        async with app.run_test(size=(120, 42)) as pilot:
            await pilot.pause()
            await _play_correct_and_choose_black(screen, pilot, "d2d4", "d")
            assert screen.history == ["d4", "e5"]
            assert screen.phase is FlowPhase.WHITE_TEST
            assert "dxe5" not in _panel_text(screen)

            await _submit_board_move(screen, pilot, "c1f4")
            assert screen.phase is FlowPhase.WHITE_RESULT_MISMATCH
            assert "Saved rule:\ndxe5" in _panel_text(screen)

            await pilot.press("enter")
            await pilot.pause()
            assert screen.history == ["d4", "e5", "dxe5"]
            assert screen.controller.board.piece_at(square_from_name("e5")) is not None
            assert screen.phase is FlowPhase.BLACK_MANUAL

    asyncio.run(run_test())


def test_flow_frontier_saves_rule_then_tests_it_after_restart(tmp_path: Path) -> None:
    async def advance_to_step_five(screen: AuthorScreen, pilot) -> None:
        await _play_correct_and_choose_black(screen, pilot, "d2d4")
        await _play_correct_and_choose_black(screen, pilot, "c1f4")
        await _play_correct_and_choose_black(screen, pilot, "e2e3")
        await _play_correct_and_choose_black(screen, pilot, "g1f3")

    async def run_test() -> None:
        path = tmp_path / "london.toml"
        shutil.copy2(LONDON_FLOW, path)
        app = ChessTui(
            mode=AppMode.FLOW,
            renderer=create_piece_renderer(RendererMode.UNICODE),
            flow_path=path,
        )
        screen = app.initial_screen
        assert isinstance(screen, AuthorScreen)

        async with app.run_test(size=(120, 42)) as pilot:
            await pilot.pause()
            await advance_to_step_five(screen, pilot)
            assert screen.phase is FlowPhase.FRONTIER_MOVE
            assert "No rule exists for White step 5" in _panel_text(screen)

            await _submit_board_move(screen, pilot, "f1d3")
            assert screen.phase is FlowPhase.RULE_NOTE
            assert screen.input.mode is InputMode.TEXT
            screen.note_input.value = "Prepare to castle."
            await pilot.press("enter")
            await pilot.pause()
            assert screen.phase is FlowPhase.RULE_NOTE
            await pilot.press("s")
            await pilot.pause()
            assert FlowStore().load(path).defaults[4].move_san == "Bd3"

            screen.action_restart_line()
            await pilot.pause()
            await advance_to_step_five(screen, pilot)
            assert screen.phase is FlowPhase.WHITE_TEST
            assert "Bd3" not in _panel_text(screen)
            assert "rule=hidden" in screen.debug_status.render_line(0).text

    asyncio.run(run_test())


def test_flow_text_mode_keeps_shortcut_characters_literal(tmp_path: Path) -> None:
    async def run_test() -> None:
        path = tmp_path / "london.toml"
        shutil.copy2(LONDON_FLOW, path)
        app = ChessTui(
            mode=AppMode.FLOW,
            renderer=create_piece_renderer(RendererMode.UNICODE),
            flow_path=path,
        )
        screen = app.initial_screen
        assert isinstance(screen, AuthorScreen)

        async with app.run_test(size=(120, 42)) as pilot:
            await pilot.pause()
            await pilot.press("i")
            await pilot.press("q", "e", "d", "r")
            await pilot.pause()
            assert app.is_running
            assert screen.input.mode is InputMode.TEXT
            assert screen.move_input.value == "qedr"

            await pilot.press("escape")
            await pilot.pause()
            assert screen.input.mode is InputMode.NAVIGATION
            assert screen.move_input.value == ""

    asyncio.run(run_test())


def test_flow_resize_preserves_run_and_renderer(tmp_path: Path) -> None:
    async def run_test() -> None:
        path = tmp_path / "london.toml"
        shutil.copy2(LONDON_FLOW, path)
        renderer = create_piece_renderer(RendererMode.PIXEL_MASK)
        app = ChessTui(
            mode=AppMode.FLOW,
            renderer=renderer,
            flow_path=path,
        )
        screen = app.initial_screen
        assert isinstance(screen, AuthorScreen)

        async with app.run_test(size=(120, 42)) as pilot:
            await pilot.pause()
            await _submit_board_move(screen, pilot, "d2d4")
            assert screen.history == ["d4"]
            assert screen.layout_mode is QuizLayoutMode.LANDSCAPE

            await pilot.resize_terminal(80, 52)
            await pilot.pause()
            assert screen.layout_mode is QuizLayoutMode.PORTRAIT
            assert screen.history == ["d4"]

            await pilot.resize_terminal(70, 40)
            await pilot.pause()
            assert screen.layout_mode is QuizLayoutMode.COMPACT
            assert screen.renderer is renderer

            await pilot.resize_terminal(60, 30)
            await pilot.pause()
            assert isinstance(screen.failure, TerminalCapabilityError)
            assert screen.history == ["d4"]

    asyncio.run(run_test())
