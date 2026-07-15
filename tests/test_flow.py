from __future__ import annotations

from pathlib import Path

import chess
import pytest

from chess_tui.flow import FlowStore, FlowValidationError
from chess_tui.policy import ConditionEvaluator, OriginalPieceTracker, parse_condition
from chess_tui.policy.runtime import DecisionSource, PolicyRuntime

FIXTURE = Path(__file__).parent / "fixtures" / "london-flow.toml"


def test_loads_strict_v2_flow_and_round_trips() -> None:
    store = FlowStore()
    flow = store.load(FIXTURE)
    assert flow.version == 2
    assert flow.side == "white"
    assert [rule.id for rule in flow.rules] == [
        "develop-d-pawn",
        "develop-dark-bishop",
        "develop-e-pawn",
        "develop-knight",
    ]
    assert flow.overrides[0].after_san == ("d4", "e5")
    assert store.decode(store.encode(flow)) == flow


def test_rejects_version_one_without_fallback() -> None:
    with pytest.raises(FlowValidationError, match="expected 2"):
        FlowStore().decode(
            'version=1\nname="Old"\nstart_fen="startpos"\nside="white"\n'
        )


@pytest.mark.parametrize(
    "condition, expected",
    [
        ({"moved": "white:d2"}, False),
        ({"at": {"piece": "white:d2", "square": "d2"}}, True),
        ({"occupied": "d2"}, True),
        ({"empty": "e4"}, True),
        ({"occupied_by": {"square": "d2", "color": "white", "type": "pawn"}}, True),
        ({"attacked": "white:e1"}, False),
        ({"attacked_by": {"target": "white:d2", "attacker": "black:d7"}}, False),
        ({"in_check": "white"}, False),
        ({"all": [{"occupied": "d2"}, {"empty": "d4"}]}, True),
        ({"any": [{"empty": "d2"}, {"occupied": "e2"}]}, True),
        ({"not": {"empty": "d2"}}, True),
    ],
)
def test_evaluates_complete_condition_language(condition: dict, expected: bool) -> None:
    board = chess.Board()
    tracker = OriginalPieceTracker(board)
    result = ConditionEvaluator(board, tracker, {}).evaluate(parse_condition(condition))
    assert result.value is expected
    assert result.explanation


def test_named_state_reference_evaluates() -> None:
    board = chess.Board()
    tracker = OriginalPieceTracker(board)
    states = {"ready": parse_condition({"at": {"piece": "white:d2", "square": "d2"}})}
    result = ConditionEvaluator(board, tracker, states).evaluate(
        parse_condition({"state": "ready"})
    )
    assert result.value


def test_rejects_state_cycles_duplicate_priorities_and_missing_pieces() -> None:
    cycle = """
version=2
name="Cycle"
start_fen="startpos"
side="white"
[[states]]
id="a"
when={state="b"}
[[states]]
id="b"
when={state="a"}
"""
    with pytest.raises(FlowValidationError, match="cycle"):
        FlowStore().decode(cycle)

    duplicate = """
version=2
name="Duplicate"
start_fen="startpos"
side="white"
[[rules]]
id="one"
priority=1
move={piece="white:d2",to="d4"}
[[rules]]
id="two"
priority=1
move={piece="white:e2",to="e4"}
"""
    with pytest.raises(FlowValidationError, match="duplicate 1"):
        FlowStore().decode(duplicate)

    missing = duplicate.replace('piece="white:d2"', 'piece="white:d3"').replace(
        'priority=1\nmove={piece="white:e2"', 'priority=2\nmove={piece="white:e2"'
    )
    with pytest.raises(FlowValidationError, match="absent from start_fen"):
        FlowStore().decode(missing)


def test_resolver_uses_override_then_highest_legal_rule_and_frontier() -> None:
    flow = FlowStore().load(FIXTURE)
    runtime, board = PolicyRuntime.replay(flow, ("d4", "e5"))
    decision = runtime.resolve(board)
    assert decision.source is DecisionSource.EXACT_OVERRIDE
    assert decision.move_san == "dxe5"

    runtime = PolicyRuntime(flow)
    decision = runtime.resolve(chess.Board())
    assert decision.source is DecisionSource.RULE
    assert decision.source_id == "develop-d-pawn"
    assert decision.move_san == "d4"

    empty = FlowStore().decode(
        'version=2\nname="Empty"\nstart_fen="startpos"\nside="white"\n'
    )
    assert PolicyRuntime(empty).resolve(chess.Board()).source is DecisionSource.FRONTIER


def test_illegal_active_rule_waits_and_lower_priority_rule_wins() -> None:
    flow = FlowStore().decode("""
version=2
name="Fallback"
start_fen="startpos"
side="white"
[[rules]]
id="blocked-bishop"
priority=20
move={piece="white:c1",to="f4"}
[[rules]]
id="pawn"
priority=10
move={piece="white:d2",to="d4"}
""")
    decision = PolicyRuntime(flow).resolve(chess.Board())
    assert decision.source_id == "pawn"
    blocked = next(
        item for item in decision.rule_resolutions if item.rule.id == "blocked-bishop"
    )
    assert blocked.status.value == "waiting"
    assert not blocked.legal


def test_activation_latches_and_retirement_wins_same_transition() -> None:
    flow = FlowStore().decode("""
version=2
name="Lifecycle"
start_fen="startpos"
side="white"
[[rules]]
id="c4-after-nc6"
priority=20
move={piece="white:c2",to="c4"}
activate_when={at={piece="black:b8",square="c6"}}
retire_when={moved="white:c2"}
[[rules]]
id="retirement-wins"
priority=10
move={piece="white:c2",to="c3"}
activate_when={moved="white:c2"}
retire_when={moved="white:c2"}
""")
    runtime, _ = PolicyRuntime.replay(flow, ("d4", "Nc6", "Nf3", "Nb8"))
    assert runtime.rule_states["c4-after-nc6"].lifecycle.value == "active"
    runtime, _ = PolicyRuntime.replay(flow, ("c3",))
    assert runtime.rule_states["retirement-wins"].lifecycle.value == "retired"
    assert runtime.rule_states["retirement-wins"].activated_at_ply is None


def test_disabled_rule_is_visible_but_does_not_resolve() -> None:
    flow = FlowStore().decode("""
version=2
name="Disabled"
start_fen="startpos"
side="white"
[[rules]]
id="disabled"
priority=20
enabled=false
move={piece="white:e2",to="e4"}
[[rules]]
id="selected"
priority=10
move={piece="white:d2",to="d4"}
""")
    decision = PolicyRuntime(flow).resolve(chess.Board())
    assert decision.source_id == "selected"
    disabled = next(
        item for item in decision.rule_resolutions if item.rule.id == "disabled"
    )
    assert disabled.status.value == "disabled"


def test_tracker_handles_capture_castling_en_passant_and_promotion() -> None:
    runtime, board = PolicyRuntime.replay(
        FlowStore().decode(
            'version=2\nname="Track"\nstart_fen="startpos"\nside="white"\n'
        ),
        ("e4", "a6", "e5", "d5", "exd6", "Nf6", "Nf3", "e6", "Be2", "Be7", "O-O"),
    )
    white_pawn = runtime.tracker.get(
        next(item.id for item in runtime.tracker.pieces if str(item.id) == "white:e2")
    )
    black_pawn = runtime.tracker.get(
        next(item.id for item in runtime.tracker.pieces if str(item.id) == "black:d7")
    )
    rook = runtime.tracker.get(
        next(item.id for item in runtime.tracker.pieces if str(item.id) == "white:h1")
    )
    assert white_pawn.current_square is not None
    assert chess.square_name(white_pawn.current_square) == "d6"
    assert black_pawn.captured and black_pawn.current_square is None
    assert rook.current_square is not None
    assert rook.has_moved and chess.square_name(rook.current_square) == "f1"
    assert board.king(chess.WHITE) == chess.G1

    promotion_flow = FlowStore().decode(
        'version=2\nname="Promotion"\nstart_fen="8/P7/8/8/8/8/7p/k6K w - - 0 1"\nside="white"\n'
    )
    promoted, _ = PolicyRuntime.replay(promotion_flow, ("a8=Q",))
    pawn = next(item for item in promoted.tracker.pieces if str(item.id) == "white:a7")
    assert pawn.piece_type == chess.QUEEN and pawn.has_moved
