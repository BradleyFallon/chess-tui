from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import chess
import pytest

from chess_tui.flow import (
    DevelopmentAssignment,
    Flow,
    FlowAuthor,
    FlowStore,
    FlowValidationError,
    FlowWorkspace,
)
from chess_tui.policy import StartingPieceRef, parse_condition
from chess_tui.policy.runtime import PolicyRuntime


def assignment(
    item_id: str,
    piece: str,
    target: str,
    *,
    structures: tuple[str, ...] = (),
) -> DevelopmentAssignment:
    return DevelopmentAssignment(
        id=item_id,
        piece=StartingPieceRef.parse(piece),
        target=target,
        structures=structures,
    )


def test_development_assignments_round_trip_without_priority_or_enabled() -> None:
    flow = FlowStore().decode("""
version=3
name="Development"
start_fen="startpos"
side="white"
[[development]]
id="d-pawn"
piece="piece:white:pawn:d"
target="d4"
ready_when={unmoved="piece:white:pawn:d"}
note="Center."
""")
    item = flow.development[0]
    assert item.piece == StartingPieceRef.parse("piece:white:pawn:d")
    encoded = FlowStore().encode(flow)
    assert "priority" not in encoded
    assert "enabled" not in encoded
    assert FlowStore().decode(encoded) == flow


def test_development_allows_global_and_structure_specific_alternatives() -> None:
    flow = FlowStore().decode("""
version=3
name="Alternatives"
start_fen="startpos"
side="white"
[[structures]]
id="a"
name="A"
available_when={moved="piece:white:pawn:d"}
selected_when={at={piece="piece:white:pawn:c",square="c3"}}
[[structures]]
id="b"
name="B"
available_when={moved="piece:white:pawn:d"}
selected_when={at={piece="piece:white:pawn:c",square="c4"}}
[[development]]
id="global-c"
piece="piece:white:pawn:c"
target="c3"
[[development]]
id="a-c"
piece="piece:white:pawn:c"
target="c3"
structures=["a"]
[[development]]
id="b-c"
piece="piece:white:pawn:c"
target="c4"
structures=["b"]
""")
    assert len(flow.development) == 3


def test_more_than_one_global_assignment_for_a_piece_is_invalid() -> None:
    flow = Flow(
        version=3,
        name="Invalid",
        start_fen="startpos",
        side="white",
        development=(
            assignment("one", "piece:white:pawn:d", "d4"),
            assignment("two", "piece:white:pawn:d", "d3"),
        ),
    )
    with pytest.raises(FlowValidationError, match="more than one global"):
        FlowStore().validate(flow)


def test_assignment_is_retired_by_original_piece_movement_or_capture() -> None:
    flow = Flow(
        version=3,
        name="Lifecycle",
        start_fen="startpos",
        side="white",
        development=(assignment("d4", "piece:white:pawn:d", "d4"),),
    )
    runtime, board = PolicyRuntime.replay(flow, ("d4", "Nf6"))
    result = runtime.resolve(board).item_resolutions[0]
    assert result.status.value == "retired"
    assert result.retirement_reason == "White d-pawn already moved."

    captured = Flow(
        version=3,
        name="Captured",
        start_fen="rnbqkbnr/pppp1ppp/8/8/1b6/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        side="white",
        development=(assignment("knight", "piece:white:knight:queenside", "c3"),),
    )
    runtime, board = PolicyRuntime.replay(captured, ("Nc3", "Bxc3"))
    tracked = runtime.tracker.get(
        StartingPieceRef.parse("piece:white:knight:queenside").original_piece_id
    )
    assert tracked.captured
    assert board.turn == chess.WHITE


def test_author_reorders_development_by_authored_list_order(tmp_path: Path) -> None:
    path = tmp_path / "flow.toml"
    flow = Flow(
        version=3,
        name="Order",
        start_fen="startpos",
        side="white",
        development=(
            assignment("d4", "piece:white:pawn:d", "d4"),
            assignment("e4", "piece:white:pawn:e", "e4"),
        ),
    )
    FlowStore().save(path, flow)
    author = FlowAuthor(path)
    candidate = author.candidate_with_development_order(("e4", "d4"))
    assert [item.id for item in candidate.development] == ["e4", "d4"]
    assert PolicyRuntime(candidate).resolve(chess.Board()).source_id == "e4"


def test_workspace_can_add_edit_and_delete_assignment(tmp_path: Path) -> None:
    path = tmp_path / "flow.toml"
    FlowStore().save(
        path,
        Flow(version=3, name="Edit", start_fen="startpos", side="white"),
    )
    workspace = FlowWorkspace(path)
    original = assignment("d4", "piece:white:pawn:d", "d4")
    workspace.save_development_rule(original)
    assert workspace.author.flow.development == (original,)

    updated = replace(
        original,
        target="d3",
        ready_when=parse_condition({"empty": "d3"}),
    )
    workspace.save_development_rule(updated)
    assert workspace.author.flow.development[0].target == "d3"

    workspace.delete_development_rule("d4")
    assert not workspace.author.flow.development
