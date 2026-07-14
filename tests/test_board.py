from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from rich.cells import cell_len
from textual.events import Resize
from textual.geometry import Size

from chess_tui import DEFAULT_STARTING_FEN, FenError, RendererMode, parse_fen
from chess_tui.board import (
    FILES,
    PIECE_GLYPHS,
    PIECE_SPRITES,
    PIXEL_SPRITE_HEIGHT,
    PIXEL_SPRITE_WIDTH,
)
from chess_tui.renderers.base import center_cells
from chess_tui.renderers.factory import create_piece_renderer
from chess_tui.renderers.pixel_mask import (
    PIECE_NAMES,
    PIXEL_MASK_SQUARE_HEIGHT,
    PIXEL_MASK_SQUARE_WIDTH,
    PixelMaskError,
    load_retro_8_piece_set,
    render_piece_square,
)
from chess_tui.runtime import TerminalCapabilityError
from chess_tui.tui import (
    BOARD_LEFT_MARGIN,
    BoardGeometry,
    ChessBoard,
    ChessTui,
    calculate_geometry,
    cell_offset_to_square,
    display_coordinates_to_square,
    square_to_display_coordinates,
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
    geometry = BoardGeometry(
        square_width=PIXEL_MASK_SQUARE_WIDTH,
        square_height=PIXEL_MASK_SQUARE_HEIGHT,
    )
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
    assert any("▀" in line for line in visible_lines[1:-1])


@pytest.mark.parametrize("piece", PIECE_GLYPHS)
def test_pixel_mask_renderer_distinguishes_piece_and_empty_squares(
    piece: str,
) -> None:
    renderer = create_piece_renderer(RendererMode.PIXEL_MASK)
    geometry = BoardGeometry(
        PIXEL_MASK_SQUARE_WIDTH,
        PIXEL_MASK_SQUARE_HEIGHT,
    )

    piece_rows = renderer.render_square_rows(
        piece=piece,
        square_width=geometry.square_width,
        square_height=geometry.square_height,
        background="#405e42",
        visual_state="normal",
        quiet_target=False,
        capture_target=False,
    )
    empty_rows = renderer.render_square_rows(
        piece=".",
        square_width=geometry.square_width,
        square_height=geometry.square_height,
        background="#405e42",
        visual_state="normal",
        quiet_target=False,
        capture_target=False,
    )

    assert len(piece_rows) == geometry.square_height
    assert all(
        sum(segment.cell_length for segment in row) == geometry.square_width
        for row in piece_rows
    )
    assert piece_rows != empty_rows


def test_retro_8_piece_set_loads() -> None:
    piece_set = load_retro_8_piece_set()

    assert piece_set.width == 8
    assert piece_set.height == 8
    assert piece_set.baseline == 6
    assert set(piece_set.pieces) == PIECE_NAMES
    assert set(piece_set.white_palette) == {"A", "B"}
    assert set(piece_set.black_palette) == {"A", "B"}


def test_every_piece_is_exactly_eight_by_eight() -> None:
    piece_set = load_retro_8_piece_set()

    for rows in piece_set.pieces.values():
        assert len(rows) == 8
        assert all(len(row) == 8 for row in rows)
        assert set("".join(rows)) <= {"_", "A", "B"}


def test_pixel_mask_square_renders_as_eight_by_four() -> None:
    rendered = render_piece_square(
        piece="N",
        background="#405e42",
        piece_set=load_retro_8_piece_set(),
    )

    assert len(rendered) == 4
    assert all(sum(segment.cell_length for segment in row) == 8 for row in rendered)


def test_white_and_black_piece_colors_differ() -> None:
    piece_set = load_retro_8_piece_set()
    white = render_piece_square(piece="P", background="#405e42", piece_set=piece_set)
    black = render_piece_square(piece="p", background="#405e42", piece_set=piece_set)

    assert white != black


def test_pixel_mask_renderer_rejects_non_native_geometry() -> None:
    renderer = create_piece_renderer(RendererMode.PIXEL_MASK)

    with pytest.raises(PixelMaskError, match="requires exactly 8x4"):
        renderer.render_square_rows(
            piece="P",
            square_width=7,
            square_height=3,
            background="#405e42",
            visual_state="normal",
            quiet_target=False,
            capture_target=False,
        )


@pytest.mark.parametrize("piece", PIECE_GLYPHS)
def test_unicode_renderer_centers_glyph(piece: str) -> None:
    renderer = create_piece_renderer(RendererMode.UNICODE)
    geometry = BoardGeometry(5, 2)

    rendered = renderer.render_square_rows(
        piece=piece,
        square_width=geometry.square_width,
        square_height=geometry.square_height,
        background="#405e42",
        visual_state="normal",
        quiet_target=False,
        capture_target=False,
    )

    assert rendered[0][0].text == " " * geometry.square_width
    assert PIECE_GLYPHS[piece] in rendered[1][0].text


@pytest.mark.parametrize("piece", PIECE_GLYPHS)
def test_legacy_renderer_centers_sprite(piece: str) -> None:
    renderer = create_piece_renderer(RendererMode.LEGACY_SPRITE)
    geometry = BoardGeometry(7, 3)

    rendered = renderer.render_square_rows(
        piece=piece,
        square_width=geometry.square_width,
        square_height=geometry.square_height,
        background="#405e42",
        visual_state="normal",
        quiet_target=False,
        capture_target=False,
    )
    expected = tuple(
        center_cells(row, geometry.square_width) for row in PIECE_SPRITES[piece.upper()]
    )

    assert tuple(row[0].text for row in rendered) == expected
    assert all(cell_len(row[0].text) == geometry.square_width for row in rendered)


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
    geometry = calculate_geometry(
        Size(100, 40),
        Size(800, 640),
        renderer_mode=RendererMode.UNICODE,
    )

    assert geometry == BoardGeometry(square_width=7, square_height=3)
    assert geometry.width == 59
    assert geometry.height == 26


def test_calculate_geometry_uses_cell_geometry_without_pixel_metrics() -> None:
    geometry = calculate_geometry(Size(100, 40), renderer_mode=RendererMode.UNICODE)

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
    assert (
        calculate_geometry(terminal_size, renderer_mode=RendererMode.UNICODE)
        == expected
    )


def test_calculate_geometry_reserves_space_for_app_chrome() -> None:
    assert calculate_geometry(
        Size(59, 26),
        reserved_rows=1,
        renderer_mode=RendererMode.UNICODE,
    ) == BoardGeometry(5, 2)


def test_calculate_geometry_rejects_terminal_that_is_too_small() -> None:
    with pytest.raises(TerminalCapabilityError, match="at least 27x10"):
        calculate_geometry(Size(26, 9), renderer_mode=RendererMode.UNICODE)


def test_pixel_mask_geometry_is_fixed_at_eight_by_four() -> None:
    assert calculate_geometry(Size(100, 40), reserved_rows=1) == BoardGeometry(8, 4)


def test_pixel_mask_geometry_requires_sixty_seven_by_thirty_five() -> None:
    with pytest.raises(
        TerminalCapabilityError,
        match="67 columns × 35 rows",
    ):
        calculate_geometry(Size(66, 34), reserved_rows=1)


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
            assert app.board.geometry == BoardGeometry(8, 4)
            assert app.renderer.mode is RendererMode.PIXEL_MASK

    asyncio.run(run_test())


def test_textual_app_accepts_resize_without_pixel_metrics() -> None:
    async def run_test() -> None:
        app = ChessTui(parse_fen(DEFAULT_STARTING_FEN))

        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()

            assert app.failure is None
            assert app.board.geometry == BoardGeometry(8, 4)

    asyncio.run(run_test())


def test_textual_app_recovers_after_terminal_grows() -> None:
    async def run_test() -> None:
        app = ChessTui(parse_fen(DEFAULT_STARTING_FEN))

        async with app.run_test(size=(18, 9)) as pilot:
            await pilot.pause()
            assert app.board.geometry is None

            size = Size(80, 40)
            app.post_message(Resize(size, size, size))
            await pilot.pause()

            assert app.is_running
            assert app.board.geometry == BoardGeometry(8, 4)

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


def test_textual_app_renders_pixel_mask_mode() -> None:
    async def run_test() -> None:
        app = ChessTui(parse_fen(DEFAULT_STARTING_FEN))

        async with app.run_test(size=(100, 40)):
            geometry = app.board.geometry
            assert geometry is not None
            assert geometry == BoardGeometry(8, 4)
            assert app.renderer.mode is RendererMode.PIXEL_MASK
            rendered_lines = [
                app.board.render_line(row).text for row in range(geometry.height)
            ]
            assert any("▀" in line for line in rendered_lines)

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
