from __future__ import annotations

import pytest

from chess_tui import DEFAULT_STARTING_FEN, format_fen, parse_fen
from chess_tui.game import GameController, square_from_name, square_name


def test_format_fen_round_trip() -> None:
    position = parse_fen(DEFAULT_STARTING_FEN)

    assert format_fen(position) == DEFAULT_STARTING_FEN


@pytest.mark.parametrize("name", ["a1", "e4", "h8"])
def test_square_name_round_trip(name: str) -> None:
    assert square_name(square_from_name(name)) == name


def test_controller_selects_and_confirms_double_pawn_move() -> None:
    controller = GameController(parse_fen(DEFAULT_STARTING_FEN))
    e2 = square_from_name("e2")
    e4 = square_from_name("e4")

    assert controller.select_square(e2)
    assert {move.uci for move in controller.interaction.legal_moves} == {
        "e2e3",
        "e2e4",
    }
    assert controller.interaction.quiet_targets == frozenset(
        {square_from_name("e3"), e4}
    )
    assert controller.choose_destination(e4)
    assert controller.interaction.pending_move is not None
    assert controller.interaction.pending_move.uci == "e2e4"

    move = controller.confirm_move()

    assert move is not None
    assert move.uci == "e2e4"
    assert controller.piece_at(e2) == "."
    assert controller.piece_at(e4) == "P"
    assert controller.position.active_color == "b"
    assert controller.interaction.last_move == move


def test_controller_marks_legal_capture() -> None:
    controller = GameController(parse_fen("4k3/8/8/3p4/4P3/8/8/4K3 w - - 0 1"))

    assert controller.select_square(square_from_name("e4"))
    assert controller.interaction.capture_targets == frozenset({square_from_name("d5")})


def test_controller_prefers_queen_for_pending_promotion() -> None:
    controller = GameController(parse_fen("4k3/1P6/8/8/8/8/8/4K3 w - - 0 1"))

    assert controller.select_square(square_from_name("b7"))
    assert controller.choose_destination(square_from_name("b8"))
    assert controller.interaction.pending_move is not None
    assert controller.interaction.pending_move.uci == "b7b8q"


def test_controller_identifies_checked_king() -> None:
    controller = GameController(parse_fen("4k3/8/8/8/8/8/4R3/4K3 b - - 0 1"))

    assert controller.interaction.checked_king == square_from_name("e8")


def test_controller_cancel_preserves_position() -> None:
    controller = GameController(parse_fen(DEFAULT_STARTING_FEN))
    original = controller.position
    controller.handle_square(square_from_name("e2"))
    controller.handle_square(square_from_name("e4"))

    controller.clear_selection()

    assert controller.position == original
    assert controller.interaction.selected_square is None
    assert controller.interaction.pending_move is None
