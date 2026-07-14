from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from rich.cells import cell_len
from textual.events import Resize
from textual.geometry import Size

from chess_tui import DEFAULT_STARTING_FEN, FenError, parse_fen
from chess_tui.board import (
    FILES,
    PIECE_GLYPHS,
    PIECE_SPRITES,
    PIXEL_SPRITE_HEIGHT,
    PIXEL_SPRITE_WIDTH,
)
from chess_tui.runtime import TerminalCapabilityError
from chess_tui.tui import (
    BOARD_LEFT_MARGIN,
    BoardGeometry,
    ChessBoard,
    ChessTui,
    calculate_geometry,
    cell_offset_to_square,
    center_cells,
    display_coordinates_to_square,
    render_piece_row,
    square_to_display_coordinates,
    use_pixel_pieces,
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
    geometry = BoardGeometry(square_width=5, square_height=2)
    board = ChessBoard(position)
    board.configure(geometry)

    lines = [board.render_line(y) for y in range(geometry.height)]
    visible_lines = [line.text for line in lines]

    assert len(lines) == geometry.height
    assert all(line.cell_length == geometry.width for line in lines)
    expected_labels = " " * BOARD_LEFT_MARGIN + "".join(
        center_cells(file_, geometry.square_width) for file_ in FILES
    )
    assert visible_lines[0] == expected_labels
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
                    square_column % geometry.square_width
                    == (geometry.square_width - 1) // 2
                )


@pytest.mark.parametrize("piece", PIECE_GLYPHS)
def test_render_piece_row_centers_three_row_sprite(
    piece: str,
) -> None:
    geometry = BoardGeometry(7, 3)

    rendered = tuple(
        render_piece_row(piece, square_row, geometry)
        for square_row in range(geometry.square_height)
    )
    expected = tuple(
        center_cells(row, geometry.square_width) for row in PIECE_SPRITES[piece.upper()]
    )

    assert use_pixel_pieces(geometry)
    assert rendered == expected
    assert all(cell_len(row) == geometry.square_width for row in rendered)


def test_render_piece_row_centers_sprite_in_larger_square() -> None:
    geometry = BoardGeometry(7, 4)

    rendered = tuple(
        render_piece_row("K", square_row, geometry)
        for square_row in range(geometry.square_height)
    )

    assert rendered[:3] == tuple(
        center_cells(row, geometry.square_width) for row in PIECE_SPRITES["K"]
    )
    assert rendered[3] == " " * geometry.square_width


def test_render_piece_row_uses_figurine_for_compact_square() -> None:
    geometry = BoardGeometry(5, 2)

    rendered = tuple(
        render_piece_row("n", square_row, geometry)
        for square_row in range(geometry.square_height)
    )

    assert not use_pixel_pieces(geometry)
    assert rendered == (" " * 5, center_cells(PIECE_GLYPHS["n"], 5))


def test_render_piece_row_can_force_figurine_in_large_square() -> None:
    geometry = BoardGeometry(7, 3)

    rendered = tuple(
        render_piece_row("N", row, geometry, "figurine")
        for row in range(geometry.square_height)
    )

    assert rendered == (
        " " * 7,
        center_cells(PIECE_GLYPHS["N"], 7),
        " " * 7,
    )


def test_textual_board_renders_pixel_sprite_across_square_rows() -> None:
    position = parse_fen("8/8/8/8/4P3/8/8/8 w - - 0 1")
    geometry = BoardGeometry(7, 3)
    board = ChessBoard(position)
    board.configure(geometry)
    square_start = BOARD_LEFT_MARGIN + (4 * geometry.square_width)
    rank_start = 1 + (4 * geometry.square_height)

    rendered = tuple(
        board.render_line(rank_start + row).text[
            square_start : square_start + geometry.square_width
        ]
        for row in range(geometry.square_height)
    )

    assert rendered == tuple(center_cells(row, 7) for row in PIECE_SPRITES["P"])


def test_all_pixel_sprite_rows_are_five_cells_wide() -> None:
    for piece, sprite in PIECE_SPRITES.items():
        assert len(sprite) == PIXEL_SPRITE_HEIGHT
        for row in sprite:
            assert cell_len(row) == PIXEL_SPRITE_WIDTH, (
                f"{piece} sprite row {row!r} is not " f"{PIXEL_SPRITE_WIDTH} cells wide"
            )


def test_five_cell_sprite_centers_in_seven_cell_square() -> None:
    for sprite in PIECE_SPRITES.values():
        for row in sprite:
            rendered = center_cells(row, 7)

            assert cell_len(rendered) == 7
            assert rendered[0] == " "
            assert rendered[-1] == " "


def test_center_cells_rejects_content_wider_than_square() -> None:
    with pytest.raises(ValueError, match="only 4 are available"):
        center_cells("12345", 4)


def test_calculate_geometry_uses_reported_pixel_ratio() -> None:
    geometry = calculate_geometry(Size(100, 40), Size(800, 640))

    assert geometry == BoardGeometry(square_width=7, square_height=3)
    assert geometry.width == 59
    assert geometry.height == 26


def test_calculate_geometry_uses_cell_geometry_without_pixel_metrics() -> None:
    geometry = calculate_geometry(Size(100, 40))

    assert geometry == BoardGeometry(square_width=7, square_height=3)


@pytest.mark.parametrize(
    ("terminal_size", "expected"),
    [
        (Size(59, 26), BoardGeometry(7, 3)),
        (Size(43, 18), BoardGeometry(5, 2)),
        (Size(27, 10), BoardGeometry(3, 1)),
    ],
)
def test_calculate_geometry_uses_largest_fitting_preset(
    terminal_size: Size, expected: BoardGeometry
) -> None:
    assert calculate_geometry(terminal_size) == expected


def test_calculate_geometry_reserves_space_for_app_chrome() -> None:
    assert calculate_geometry(Size(59, 26), reserved_rows=1) == BoardGeometry(5, 2)


def test_calculate_geometry_rejects_terminal_that_is_too_small() -> None:
    with pytest.raises(TerminalCapabilityError, match="at least 27x10"):
        calculate_geometry(Size(26, 9))


@pytest.mark.parametrize(
    ("display_file", "display_rank", "flipped", "expected"),
    [
        (0, 0, False, 56),
        (7, 7, False, 7),
        (0, 0, True, 7),
        (7, 7, True, 56),
    ],
)
def test_display_coordinates_to_square(
    display_file: int, display_rank: int, flipped: bool, expected: int
) -> None:
    square = display_coordinates_to_square(display_file, display_rank, flipped)

    assert square == expected
    assert square_to_display_coordinates(square, flipped) == (
        display_file,
        display_rank,
    )


def test_square_display_coordinate_round_trip() -> None:
    for flipped in (False, True):
        for square in range(64):
            display_file, display_rank = square_to_display_coordinates(square, flipped)
            assert (
                display_coordinates_to_square(display_file, display_rank, flipped)
                == square
            )


def test_cell_offset_to_square_excludes_labels_and_maps_orientation() -> None:
    geometry = BoardGeometry(7, 3)

    assert cell_offset_to_square(3, 1, geometry, False) == 56
    assert cell_offset_to_square(58, 24, geometry, False) == 7
    assert cell_offset_to_square(3, 1, geometry, True) == 7
    assert cell_offset_to_square(58, 24, geometry, True) == 56
    assert cell_offset_to_square(2, 1, geometry, False) is None
    assert cell_offset_to_square(3, 0, geometry, False) is None
    assert cell_offset_to_square(3, 25, geometry, False) is None


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
            assert app.board.geometry == BoardGeometry(7, 3)

    asyncio.run(run_test())


def test_textual_app_accepts_resize_without_pixel_metrics() -> None:
    async def run_test() -> None:
        app = ChessTui(parse_fen(DEFAULT_STARTING_FEN))

        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()

            assert app.failure is None
            assert app.board.geometry == BoardGeometry(7, 3)

    asyncio.run(run_test())


def test_textual_app_recovers_after_terminal_grows() -> None:
    async def run_test() -> None:
        app = ChessTui(parse_fen(DEFAULT_STARTING_FEN))

        async with app.run_test(size=(18, 9)) as pilot:
            await pilot.pause()
            assert app.board.geometry is None

            size = Size(80, 24)
            app.post_message(Resize(size, size, size))
            await pilot.pause()

            assert app.is_running
            assert app.board.geometry == BoardGeometry(5, 2)

    asyncio.run(run_test())


def test_textual_app_selects_confirms_and_flips() -> None:
    async def run_test() -> None:
        app = ChessTui(parse_fen(DEFAULT_STARTING_FEN))

        async with app.run_test(size=(100, 40)) as pilot:
            app.board.post_message(ChessBoard.SquareClicked(12))
            await pilot.pause()
            assert app.controller.interaction.selected_square == 12
            assert app.controller.interaction.quiet_targets == frozenset({20, 28})

            app.board.post_message(ChessBoard.SquareClicked(28))
            await pilot.pause()
            assert app.controller.interaction.pending_move is not None
            assert app.controller.interaction.pending_move.uci == "e2e4"

            await pilot.press("enter")
            assert app.controller.position.active_color == "b"
            assert app.controller.piece_at(28) == "P"

            await pilot.press("f")
            assert app.flipped

    asyncio.run(run_test())


def test_textual_app_toggles_piece_view_mode() -> None:
    async def run_test() -> None:
        app = ChessTui(parse_fen(DEFAULT_STARTING_FEN))

        async with app.run_test(size=(100, 40)) as pilot:
            geometry = app.board.geometry
            assert geometry is not None
            assert geometry == BoardGeometry(7, 3)
            assert app.piece_mode == "pixel"
            pixel_lines = [
                app.board.render_line(row).text for row in range(geometry.height)
            ]
            assert not any(glyph in line for glyph in GLYPHS for line in pixel_lines)

            await pilot.press("v")

            assert app.piece_mode == "figurine"
            figurine_lines = [
                app.board.render_line(row).text for row in range(geometry.height)
            ]
            assert any(glyph in line for glyph in GLYPHS for line in figurine_lines)

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
