from __future__ import annotations

import asyncio
from pathlib import Path
import shutil

import chess

from chess_tui import AppMode, DEFAULT_STARTING_FEN, parse_fen
from chess_tui.flow import DefaultRule, FlowStore, WhiteFlow
from chess_tui.engine import (
    ENGINE_PROTOTYPE_PROFILE,
    AnalysedMove,
    EngineProcessError,
    EngineProfile,
)
from chess_tui.game import square_from_name
from chess_tui.input_mode import InputMode
from chess_tui.layout import QuizLayoutMode
from chess_tui.opening import (
    FixtureOpeningMoveSource,
    OpponentMovePlanner,
    StockfishBotMoveSource,
)
from chess_tui.renderers.factory import create_piece_renderer
from chess_tui.renderers.mode import RendererMode
from chess_tui.runtime import TerminalCapabilityError
from chess_tui.screens.author import AuthorScreen, FlowPhase
from chess_tui.tui import ChessBoard, ChessTui

PROJECT_ROOT = Path(__file__).parents[1]
LONDON_FLOW = PROJECT_ROOT / "tests" / "fixtures" / "london-flow.toml"


def _write_flow(
    path: Path,
    start_fen: str,
    defaults: tuple[DefaultRule, ...] = (),
) -> None:
    FlowStore().save(path, WhiteFlow(1, "Endgame test", start_fen, defaults, ()))


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
            assert screen.move_suggestions.highlighted_suggestion is not None
            assert screen.move_suggestions.highlighted_suggestion.san == "d5"

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
            assert screen.phase is FlowPhase.BLACK_SELECT
            suggestion = screen.move_suggestions.highlighted_suggestion
            assert suggestion is not None
            assert suggestion.kind.value == "bot"

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
            suggestion = screen.move_suggestions.highlighted_suggestion
            assert screen.phase is FlowPhase.BLACK_SELECT
            assert suggestion is not None
            assert suggestion.kind.value == "bot"

            screen.action_restart_line()
            await pilot.pause()
            await advance_to_step_five(screen, pilot)
            assert screen.phase is FlowPhase.WHITE_TEST
            assert "Bd3" not in _panel_text(screen)
            assert "rule=hidden" in screen.debug_status.render_line(0).text

    asyncio.run(run_test())


def test_flow_suggestions_keep_manual_and_typed_black_entry(tmp_path: Path) -> None:
    async def enter_black_selector(screen: AuthorScreen, pilot) -> None:
        await _submit_board_move(screen, pilot, "d2d4")
        if screen.phase is FlowPhase.WHITE_RESULT_CORRECT:
            await pilot.press("enter")
            await pilot.pause()
        assert screen.phase is FlowPhase.BLACK_SELECT

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
            await enter_black_selector(screen, pilot)
            await pilot.press("m")
            await pilot.pause()
            assert screen.phase is FlowPhase.BLACK_MANUAL
            assert screen.input.mode is InputMode.NAVIGATION

            screen.action_restart_line()
            await pilot.pause()
            await enter_black_selector(screen, pilot)
            await pilot.press("i")
            await pilot.pause()
            assert screen.phase is FlowPhase.BLACK_MANUAL
            assert screen.input.mode is InputMode.TEXT
            assert screen.input.active_field is screen.move_input

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


def test_flow_enters_game_over_for_checkmate_after_white_move(
    tmp_path: Path,
) -> None:
    async def run_test() -> None:
        path = tmp_path / "mate-white.toml"
        _write_flow(path, "7k/8/5KQ1/8/8/8/8/8 w - - 0 1")
        app = ChessTui(
            mode=AppMode.FLOW,
            renderer=create_piece_renderer(RendererMode.UNICODE),
            flow_path=path,
        )
        screen = app.initial_screen
        assert isinstance(screen, AuthorScreen)

        async with app.run_test(size=(120, 42)) as pilot:
            await pilot.pause()
            await _submit_board_move(screen, pilot, "g6g7")

            assert screen.phase is FlowPhase.GAME_OVER
            assert "Checkmate\nWhite wins" in _panel_text(screen)
            assert not screen.move_suggestions.display

    asyncio.run(run_test())


def test_flow_enters_game_over_for_checkmate_after_black_move(
    tmp_path: Path,
) -> None:
    async def run_test() -> None:
        path = tmp_path / "mate-black.toml"
        _write_flow(
            path,
            "rnbqkbnr/pppp1ppp/8/4p3/8/5P2/PPPPP1PP/RNBQKBNR " "w KQkq - 0 2",
            (DefaultRule(1, "g4"),),
        )
        app = ChessTui(
            mode=AppMode.FLOW,
            renderer=create_piece_renderer(RendererMode.UNICODE),
            flow_path=path,
        )
        screen = app.initial_screen
        assert isinstance(screen, AuthorScreen)

        async with app.run_test(size=(120, 42)) as pilot:
            await pilot.pause()
            await _submit_board_move(screen, pilot, "g2g4")
            if screen.phase is FlowPhase.WHITE_RESULT_CORRECT:
                await pilot.press("enter")
                await pilot.pause()
            assert screen.phase is FlowPhase.BLACK_SELECT

            await pilot.press("m")
            await pilot.pause()
            await _submit_board_move(screen, pilot, "d8h4")

            assert screen.phase is FlowPhase.GAME_OVER
            assert "Checkmate\nBlack wins" in _panel_text(screen)

    asyncio.run(run_test())


def test_flow_enters_game_over_for_stalemate_and_can_restart(
    tmp_path: Path,
) -> None:
    async def run_test() -> None:
        path = tmp_path / "stalemate.toml"
        _write_flow(path, "k7/2Q5/2K5/8/8/8/8/8 w - - 0 1")
        app = ChessTui(
            mode=AppMode.FLOW,
            renderer=create_piece_renderer(RendererMode.UNICODE),
            flow_path=path,
        )
        screen = app.initial_screen
        assert isinstance(screen, AuthorScreen)

        async with app.run_test(size=(120, 42)) as pilot:
            await pilot.pause()
            await _submit_board_move(screen, pilot, "c7b6")
            assert screen.phase is FlowPhase.GAME_OVER
            assert "Stalemate\nDraw" in _panel_text(screen)

            await pilot.press("r")
            await pilot.pause()
            assert screen.phase is FlowPhase.FRONTIER_MOVE
            assert screen.history == []
            assert screen.workspace.outcome is None

    asyncio.run(run_test())


def test_configured_engine_failure_is_explicit_and_retryable(
    tmp_path: Path,
) -> None:
    async def run_test() -> None:
        class FlakyEngine:
            def __init__(self) -> None:
                self.requests = 0
                self.closed = False

            async def choose_move(
                self, board: chess.Board, profile: EngineProfile
            ) -> chess.Move:
                assert profile == ENGINE_PROTOTYPE_PROFILE
                self.requests += 1
                if self.requests == 1:
                    raise EngineProcessError("simulated engine exit")
                return chess.Move.from_uci("e7e5")

            async def analyse(
                self, board: chess.Board, *, count: int = 4
            ) -> tuple[AnalysedMove, ...]:
                move = next(iter(board.legal_moves))
                return (
                    AnalysedMove(
                        move.uci(),
                        board.san(move),
                        0,
                        (move.uci(),),
                    ),
                )

            async def close(self) -> None:
                self.closed = True

        path = tmp_path / "engine-retry.toml"
        _write_flow(path, DEFAULT_STARTING_FEN, (DefaultRule(1, "e4"),))
        engine = FlakyEngine()
        planner = OpponentMovePlanner(
            FixtureOpeningMoveSource(),
            StockfishBotMoveSource(engine),
        )
        app = ChessTui(
            mode=AppMode.FLOW,
            renderer=create_piece_renderer(RendererMode.UNICODE),
            flow_path=path,
            opponent_planner=planner,
        )
        screen = app.initial_screen
        assert isinstance(screen, AuthorScreen)

        async with app.run_test(size=(120, 42)) as pilot:
            await pilot.pause()
            await _submit_board_move(screen, pilot, "e2e4")
            if screen.phase is FlowPhase.WHITE_RESULT_CORRECT:
                await pilot.press("enter")
                await pilot.pause()

            assert screen.phase is FlowPhase.BLACK_ENGINE_ERROR
            panel = _panel_text(screen)
            assert "ENGINE SUGGESTION FAILED" in panel
            assert "simulated engine exit" in panel
            assert "[M] Enter Black move manually" in panel
            assert screen.move_suggestions.suggestions == ()

            await pilot.press("r")
            await pilot.pause()
            assert screen.phase is FlowPhase.BLACK_SELECT
            suggestion = screen.move_suggestions.highlighted_suggestion
            assert suggestion is not None
            assert suggestion.san == "e5"
            assert suggestion.label == "ENGINE PROTOTYPE"
            assert engine.requests == 2

        assert engine.closed

    asyncio.run(run_test())


def test_mismatching_white_move_shows_structured_engine_review(
    tmp_path: Path,
) -> None:
    async def run_test() -> None:
        class ReviewEngine:
            def __init__(self) -> None:
                self.closed = False

            async def choose_move(
                self, board: chess.Board, profile: EngineProfile
            ) -> chess.Move:
                return next(iter(board.legal_moves))

            async def analyse(
                self, board: chess.Board, *, count: int = 4
            ) -> tuple[AnalysedMove, ...]:
                if board.turn is chess.WHITE:
                    return (AnalysedMove("d2d4", "d4", 50, ("d2d4", "d7d5")),)
                return (AnalysedMove("e7e5", "e5", -210, ("e7e5", "g1f3")),)

            async def close(self) -> None:
                self.closed = True

        path = tmp_path / "review.toml"
        _write_flow(path, DEFAULT_STARTING_FEN, (DefaultRule(1, "d4"),))
        engine = ReviewEngine()
        app = ChessTui(
            mode=AppMode.FLOW,
            renderer=create_piece_renderer(RendererMode.UNICODE),
            flow_path=path,
            analysis_engine=engine,
        )
        screen = app.initial_screen
        assert isinstance(screen, AuthorScreen)

        async with app.run_test(size=(120, 42)) as pilot:
            await pilot.pause()
            await _submit_board_move(screen, pilot, "e2e4")
            await pilot.pause()

            assert screen.phase is FlowPhase.WHITE_RESULT_MISMATCH
            panel = _panel_text(screen)
            assert "Engine review:\nBLUNDER" in panel
            assert "Approximately 2.6 pawns worse than the best move." in panel
            assert "Best move:\nd4" in panel
            assert "[R] Retry" in panel
            assert "[Enter] Keep saved rule" in panel
            assert FlowStore().load(path).defaults[0].move_san == "d4"

        assert engine.closed

    asyncio.run(run_test())


def test_advantage_bar_tracks_only_committed_flow_positions(tmp_path: Path) -> None:
    async def run_test() -> None:
        class TrackingEngine:
            def __init__(self) -> None:
                self.positions: list[str] = []
                self.closed = False

            async def choose_move(
                self, board: chess.Board, profile: EngineProfile
            ) -> chess.Move:
                return next(iter(board.legal_moves))

            async def analyse(
                self, board: chess.Board, *, count: int = 4
            ) -> tuple[AnalysedMove, ...]:
                self.positions.append(board.fen(en_passant="fen"))
                move = next(iter(board.legal_moves))
                evaluation = 35 if board.turn is chess.WHITE else -80
                return (
                    AnalysedMove(
                        move.uci(),
                        board.san(move),
                        evaluation,
                        (move.uci(),),
                    ),
                )

            async def close(self) -> None:
                self.closed = True

        path = tmp_path / "advantage.toml"
        _write_flow(path, DEFAULT_STARTING_FEN)
        engine = TrackingEngine()
        app = ChessTui(
            mode=AppMode.FLOW,
            renderer=create_piece_renderer(RendererMode.UNICODE),
            flow_path=path,
            analysis_engine=engine,
        )
        screen = app.initial_screen
        assert isinstance(screen, AuthorScreen)

        async with app.run_test(size=(120, 42)) as pilot:
            await pilot.pause()
            assert screen.advantage_bar.display
            assert "WHITE +0.35" in screen.advantage_bar.render().plain
            assert len(engine.positions) == 1

            _click_move(screen, "e2e4")
            await pilot.pause()
            assert len(engine.positions) == 1

            await pilot.press("enter")
            await pilot.pause()
            assert len(engine.positions) == 2
            assert "BLACK +0.80" in screen.advantage_bar.render().plain

        assert engine.closed

    asyncio.run(run_test())


def test_advantage_analysis_failure_does_not_interrupt_flow(tmp_path: Path) -> None:
    async def run_test() -> None:
        class FailingAnalysisEngine:
            async def choose_move(
                self, board: chess.Board, profile: EngineProfile
            ) -> chess.Move:
                return next(iter(board.legal_moves))

            async def analyse(
                self, board: chess.Board, *, count: int = 4
            ) -> tuple[AnalysedMove, ...]:
                raise EngineProcessError("analysis unavailable")

            async def close(self) -> None:
                return None

        path = tmp_path / "advantage-error.toml"
        _write_flow(path, DEFAULT_STARTING_FEN)
        app = ChessTui(
            mode=AppMode.FLOW,
            renderer=create_piece_renderer(RendererMode.UNICODE),
            flow_path=path,
            analysis_engine=FailingAnalysisEngine(),
        )
        screen = app.initial_screen
        assert isinstance(screen, AuthorScreen)

        async with app.run_test(size=(120, 42)) as pilot:
            await pilot.pause()
            assert screen.phase is FlowPhase.FRONTIER_MOVE
            assert "ENGINE —" in screen.advantage_bar.render().plain
            assert screen.advantage_bar.error == "analysis unavailable"

    asyncio.run(run_test())


def test_auto_play_black_commits_first_ranked_suggestion(tmp_path: Path) -> None:
    async def run_test() -> None:
        path = tmp_path / "auto-black.toml"
        _write_flow(
            path,
            DEFAULT_STARTING_FEN,
            (DefaultRule(1, "d4"),),
        )
        app = ChessTui(
            mode=AppMode.FLOW,
            renderer=create_piece_renderer(RendererMode.UNICODE),
            flow_path=path,
            auto_play_black=True,
        )
        screen = app.initial_screen
        assert isinstance(screen, AuthorScreen)

        async with app.run_test(size=(120, 42)) as pilot:
            await pilot.pause()
            await _submit_board_move(screen, pilot, "d2d4")
            if screen.phase is FlowPhase.WHITE_RESULT_CORRECT:
                await pilot.press("enter")
                await pilot.pause()

            assert screen.history == ["d4", "d5"]
            assert screen.phase is FlowPhase.FRONTIER_MOVE
            assert not screen.move_suggestions.display
            saved = FlowStore().load(path)
            assert saved.opponent_replies[-1].move_san == "d5"

    asyncio.run(run_test())


def test_default_flow_focuses_san_and_restores_focus_each_white_turn(
    tmp_path: Path,
) -> None:
    async def run_test() -> None:
        path = tmp_path / "focused-san.toml"
        _write_flow(
            path,
            DEFAULT_STARTING_FEN,
            (DefaultRule(1, "d4"),),
        )
        app = ChessTui(
            mode=AppMode.FLOW,
            renderer=create_piece_renderer(RendererMode.UNICODE),
            flow_path=path,
            auto_play_black=True,
            focus_san_on_white_turn=True,
        )
        screen = app.initial_screen
        assert isinstance(screen, AuthorScreen)

        async with app.run_test(size=(120, 42)) as pilot:
            await pilot.pause()
            assert screen.input.mode is InputMode.TEXT
            assert screen.input.active_field is screen.move_input
            assert screen.move_input.has_focus

            await pilot.press("escape")
            await pilot.pause()
            assert screen.input.mode is InputMode.NAVIGATION
            assert screen.input.active_field is None

            await pilot.press("i")
            await pilot.pause()
            assert screen.input.mode is InputMode.TEXT
            assert screen.input.active_field is screen.move_input
            assert screen.move_input.has_focus

            await pilot.press("d", "4", "enter")
            await pilot.pause()
            if screen.phase is FlowPhase.WHITE_RESULT_CORRECT:
                await pilot.press("enter")
                await pilot.pause()

            assert screen.history == ["d4", "d5"]
            assert screen.phase is FlowPhase.FRONTIER_MOVE
            assert screen.input.mode is InputMode.TEXT
            assert screen.input.active_field is screen.move_input
            assert screen.move_input.has_focus

    asyncio.run(run_test())
