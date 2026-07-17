from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import shutil

import chess
import pytest

from chess_tui.flow import (
    DevelopmentRule,
    Flow,
    FlowStore,
    FlowValidationError,
    FlowWorkspace,
)
from chess_tui.policy import StartingPieceRef, parse_condition
from chess_tui.policy.runtime import PolicyRuntime

FIXTURE = Path(__file__).parent / "fixtures" / "london-flow.toml"


@pytest.mark.parametrize(
    ("source", "square"),
    [
        ("piece:white:pawn:a", "a2"),
        ("piece:white:pawn:h", "h2"),
        ("piece:black:pawn:d", "d7"),
        ("piece:white:rook:queenside", "a1"),
        ("piece:black:rook:kingside", "h8"),
        ("piece:white:knight:kingside", "g1"),
        ("piece:black:knight:queenside", "b8"),
        ("piece:white:bishop:queenside", "c1"),
        ("piece:black:bishop:kingside", "f8"),
        ("piece:white:queen", "d1"),
        ("piece:black:king", "e8"),
    ],
)
def test_starting_piece_references_map_deterministically(
    source: str, square: str
) -> None:
    reference = StartingPieceRef.parse(source)
    assert str(reference) == source
    assert reference.original_piece_id.start_square == square
    assert StartingPieceRef.from_original(reference.original_piece_id) == reference


@pytest.mark.parametrize(
    "source",
    [
        "white:d2",
        "piece:white:pawn",
        "piece:white:pawn:queenside",
        "piece:white:queen:kingside",
        "piece:black:knight:c",
        "piece:white:bishop:left",
        "piece:green:king",
    ],
)
def test_starting_piece_references_reject_invalid_shapes(source: str) -> None:
    with pytest.raises(ValueError, match="[Ss]tarting-piece"):
        StartingPieceRef.parse(source)


def test_development_rule_round_trip_and_duplicate_piece_validation() -> None:
    source = """
version=2
name="Development"
start_fen="startpos"
side="white"
[[rules]]
id="d-pawn"
kind="development"
piece="piece:white:pawn:d"
target="d4"
priority=1000
ready_when={empty="d4"}
note="Claim the center."
"""
    store = FlowStore()
    flow = store.decode(source)
    rule = flow.rules[0]
    assert isinstance(rule, DevelopmentRule)
    assert rule.ready_when == parse_condition({"empty": "d4"})
    assert store.decode(store.encode(flow)) == flow

    duplicate = source + """
[[rules]]
id="other-d-pawn"
kind="development"
piece="piece:white:pawn:d"
target="d3"
priority=900
"""
    with pytest.raises(FlowValidationError, match="at most once"):
        store.decode(duplicate)

    wrong_piece_type = source.replace(
        'start_fen="startpos"',
        'start_fen="4k3/8/8/8/8/8/3N4/4K3 w - - 0 1"',
    )
    with pytest.raises(FlowValidationError, match="expected pawn"):
        store.decode(wrong_piece_type)


def test_development_statuses_use_existing_runtime_resolution() -> None:
    flow = Flow(
        version=2,
        name="Statuses",
        start_fen="startpos",
        side="white",
        rules=(
            DevelopmentRule(
                "d-pawn",
                StartingPieceRef.parse("piece:white:pawn:d"),
                "d4",
                1000,
            ),
            DevelopmentRule(
                "e-pawn",
                StartingPieceRef.parse("piece:white:pawn:e"),
                "e4",
                900,
            ),
            DevelopmentRule(
                "blocked-bishop",
                StartingPieceRef.parse("piece:white:bishop:queenside"),
                "f4",
                800,
            ),
            DevelopmentRule(
                "dormant-knight",
                StartingPieceRef.parse("piece:white:knight:kingside"),
                "f3",
                700,
                ready_when=parse_condition({"moved": "piece:white:pawn:d"}),
            ),
            DevelopmentRule(
                "disabled-pawn",
                StartingPieceRef.parse("piece:white:pawn:a"),
                "a3",
                600,
                enabled=False,
            ),
        ),
    )
    decision = PolicyRuntime(flow).resolve(chess.Board())
    statuses = {item.rule.id: item.status.value for item in decision.rule_resolutions}
    assert decision.source_id == "d-pawn"
    assert statuses == {
        "d-pawn": "selected",
        "e-pawn": "active",
        "blocked-bishop": "waiting",
        "dormant-knight": "dormant",
        "disabled-pawn": "disabled",
    }


def test_development_rule_retires_after_target_or_other_move() -> None:
    rule = DevelopmentRule(
        "d-pawn",
        StartingPieceRef.parse("piece:white:pawn:d"),
        "d4",
        1000,
    )
    flow = Flow(2, "Retire", "startpos", "white", rules=(rule,))
    target_runtime, _ = PolicyRuntime.replay(flow, ("d4",))
    assert target_runtime.rule_states["d-pawn"].lifecycle.value == "retired"
    assert target_runtime.tracker.get(rule.piece.original_piece_id).first_moved_ply == 1

    other_runtime, _ = PolicyRuntime.replay(flow, ("d3",))
    state = other_runtime.rule_states["d-pawn"]
    assert state.lifecycle.value == "retired"
    assert state.retirement_reason == "White d-pawn moved."


def test_capture_before_and_after_development_reconstructs_mechanical_state() -> None:
    undeveloped_rule = DevelopmentRule(
        "bishop",
        StartingPieceRef.parse("piece:white:bishop:queenside"),
        "d2",
        1000,
    )
    before_flow = Flow(
        2,
        "Captured before",
        "k1r5/8/8/8/8/8/8/2B1K3 w - - 0 1",
        "white",
        rules=(undeveloped_rule,),
    )
    runtime, _ = PolicyRuntime.replay(before_flow, ("Kf2", "Rxc1"))
    bishop = runtime.tracker.get(undeveloped_rule.piece.original_piece_id)
    assert bishop.captured and not bishop.has_moved
    assert bishop.captured_ply == 2 and bishop.first_moved_ply is None
    assert runtime.rule_states["bishop"].lifecycle.value == "retired"

    after_flow = replace(
        before_flow,
        name="Captured after",
        start_fen="k2r4/8/8/8/8/8/8/2B1K3 w - - 0 1",
    )
    runtime, _ = PolicyRuntime.replay(after_flow, ("Bd2", "Rxd2+"))
    bishop = runtime.tracker.get(undeveloped_rule.piece.original_piece_id)
    assert bishop.captured and bishop.has_moved
    assert bishop.first_moved_ply == 1 and bishop.captured_ply == 2


def test_reorder_is_deterministic_and_invalid_edit_is_atomic(
    tmp_path: Path,
) -> None:
    path = tmp_path / "flow.toml"
    shutil.copy2(FIXTURE, path)
    workspace = FlowWorkspace(path)
    ids = tuple(
        reversed(
            [
                rule.id
                for rule in workspace.author.flow.rules
                if isinstance(rule, DevelopmentRule)
            ]
        )
    )
    workspace.reorder_development_rules(ids)
    rules = sorted(
        (
            rule
            for rule in workspace.author.flow.rules
            if isinstance(rule, DevelopmentRule)
        ),
        key=lambda item: item.priority,
        reverse=True,
    )
    assert tuple(rule.id for rule in rules) == ids
    assert len({rule.priority for rule in rules}) == len(rules)

    original = path.read_text(encoding="utf-8")
    with pytest.raises(FlowValidationError):
        workspace.update_rule(replace(rules[0], target="z9"))
    assert path.read_text(encoding="utf-8") == original


def test_london_flow_uses_development_rules_and_canonical_references() -> None:
    flow = FlowStore().load(Path("flows/london.toml"))
    development = [rule for rule in flow.rules if isinstance(rule, DevelopmentRule)]
    assert [str(rule.piece) for rule in development[:4]] == [
        "piece:white:pawn:d",
        "piece:white:bishop:queenside",
        "piece:white:pawn:e",
        "piece:white:knight:kingside",
    ]
    assert "white:d2" not in FlowStore().encode(flow)
