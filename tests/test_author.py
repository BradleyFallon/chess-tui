from __future__ import annotations

from pathlib import Path
import shutil

import chess

from chess_tui import AppMode, DEFAULT_STARTING_FEN, parse_fen
from chess_tui.flow import AuthorBoardController
from chess_tui.renderers.factory import create_piece_renderer
from chess_tui.renderers.mode import RendererMode
from chess_tui.screens.author import AuthorScreen, FlowPhase
from chess_tui.tui import ChessTui

FIXTURE = Path(__file__).parents[1] / "flows" / "london.toml"


def test_author_board_controller_commits_legal_san() -> None:
    controller = AuthorBoardController(chess.Board(DEFAULT_STARTING_FEN))
    confirmed = controller.confirm_san("d4")
    assert confirmed.san == "d4"
    assert confirmed.move.uci == "d2d4"


def test_textual_flow_screen_starts_with_v4_rulebook(tmp_path: Path) -> None:
    async def run() -> None:
        path = tmp_path / "flow.toml"
        shutil.copy2(FIXTURE, path)
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
            assert screen.phase is FlowPhase.POLICY_TEST
            assert screen.workspace.policy_turn
            assert screen.workspace.policy_turn.decision.source_id == "d-pawn.develop"

    import asyncio

    asyncio.run(run())
