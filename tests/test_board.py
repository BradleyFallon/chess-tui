from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from textual.events import Resize
from textual.geometry import Size

from chess_tui import DEFAULT_STARTING_FEN, FenError, parse_fen
from chess_tui.board import PIECE_GLYPHS
from chess_tui.runtime import TerminalCapabilityError
from chess_tui.tui import (
    BOARD_LEFT_MARGIN,
    BoardGeometry,
    ChessBoard,
    ChessTui,
    calculate_geometry,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "fens.json"
GLYPHS = frozenset(PIECE_GLYPHS.values())


def load_fen_samples() -> list[dict[str, str]]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    "sample", load_fen_samples(), ids=lambda sample: sample["name"]
)
def test_textual_board_renders_fen_samples(sample: dict[str, str]) -> None:
    position = parse_fen(sample["fen"])
    geometry = BoardGeometry(square_width=5)
    board = ChessBoard(position)
    board.configure(geometry)

    lines = [board.render_line(y) for y in range(geometry.height)]
    visible_lines = [line.text for line in lines]

    assert len(lines) == geometry.height
    assert all(line.cell_length == geometry.width for line in lines)
    assert visible_lines[0].startswith("     a    b    c    d    e    f    g    h")
    assert visible_lines[-1] == visible_lines[0]

    expected_pieces = sum(
        1 for char in sample["fen"].split()[0] if char in PIECE_GLYPHS
    )
    rendered_pieces = sum(char in GLYPHS for line in visible_lines for char in line)
    assert rendered_pieces == expected_pieces

    for rank_index in range(8):
        center_row = 1 + (rank_index * geometry.square_height)
        center_row += geometry.square_height // 2
        line = visible_lines[center_row]
        assert line.startswith(str(8 - rank_index))
        for column, character in enumerate(line):
            if character in GLYPHS:
                square_column = column - BOARD_LEFT_MARGIN
                assert (
                    square_column % geometry.square_width == geometry.square_width // 2
                )


def test_calculate_geometry_uses_reported_pixel_ratio() -> None:
    geometry = calculate_geometry(Size(100, 40), Size(800, 640))

    assert geometry.square_width == 5
    assert geometry.square_height == 3
    assert geometry.width == 43
    assert geometry.height == 26


def test_calculate_geometry_uses_cell_geometry_without_pixel_metrics() -> None:
    geometry = calculate_geometry(Size(100, 40))

    assert geometry == BoardGeometry(square_width=5)


def test_calculate_geometry_rejects_terminal_that_is_too_small() -> None:
    with pytest.raises(TerminalCapabilityError, match="requires at least"):
        calculate_geometry(Size(40, 24), Size(320, 384))


def test_textual_app_accepts_verified_pixel_metrics() -> None:
    async def run_test() -> None:
        app = ChessTui(parse_fen(DEFAULT_STARTING_FEN))
        terminal_size = Size(100, 40)
        pixel_size = Size(800, 640)

        async with app.run_test(size=(100, 40)) as pilot:
            app.post_message(
                Resize(terminal_size, terminal_size, terminal_size, pixel_size)
            )
            await pilot.pause()

            assert app.failure is None
            assert app.board.geometry == BoardGeometry(square_width=5)

    asyncio.run(run_test())


def test_textual_app_accepts_resize_without_pixel_metrics() -> None:
    async def run_test() -> None:
        app = ChessTui(parse_fen(DEFAULT_STARTING_FEN))

        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()

            assert app.failure is None
            assert app.board.geometry == BoardGeometry(square_width=5)

    asyncio.run(run_test())


def test_parse_fen_normalizes_board() -> None:
    position = parse_fen(DEFAULT_STARTING_FEN)

    assert position.active_color == "w"
    assert position.castling == "KQkq"
    assert position.en_passant == "-"
    assert position.halfmove_clock == 0
    assert position.fullmove_number == 1
    assert position.board[0] == tuple("rnbqkbnr")
    assert position.board[7] == tuple("RNBQKBNR")


def test_parse_fen_rejects_bad_input() -> None:
    with pytest.raises(FenError):
        parse_fen("8/8/8/8/8/8/8/7X w - - 0 1")
