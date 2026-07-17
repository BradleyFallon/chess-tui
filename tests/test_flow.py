from __future__ import annotations

from pathlib import Path

import chess
import pytest

from chess_tui.flow import FlowStore, FlowValidationError, OpeningTag
from chess_tui.policy import (
    ConditionEvaluator,
    LastMove,
    OriginalPieceId,
    OriginalPieceTracker,
    parse_condition,
)
from chess_tui.policy.runtime import DecisionSource, PolicyRuntime

FIXTURE = Path(__file__).parents[1] / "flows" / "london.toml"


def test_loads_strict_v3_flow_and_round_trips_in_authored_order() -> None:
    store = FlowStore()
    flow = store.load(FIXTURE)
    assert flow.version == 3
    assert flow.side == "white"
    assert [item.id for item in flow.responses] == [
        "advance-against-early-c5",
        "retreat-attacked-london-bishop",
    ]
    assert [item.id for item in flow.development[:3]] == [
        "develop-d-pawn",
        "develop-dark-bishop",
        "develop-e-pawn",
    ]
    assert flow.overrides[0].after_san == ("d4", "e5")
    assert store.decode(store.encode(flow)) == flow


def test_opening_tags_round_trip_and_validate() -> None:
    store = FlowStore()
    flow = store.decode("""
version=3
name="Tagged"
start_fen="startpos"
side="white"
opening_tags=[
  {eco="A40", name="Queen's Pawn Game"},
  {eco="D00", name="Queen's Pawn Game: Accelerated London System"},
]
""")
    assert flow.opening_tags == (
        OpeningTag("A40", "Queen's Pawn Game"),
        OpeningTag("D00", "Queen's Pawn Game: Accelerated London System"),
    )
    assert store.decode(store.encode(flow)) == flow

    with pytest.raises(FlowValidationError, match="must be unique"):
        store.decode("""
version=3
name="Duplicate"
start_fen="startpos"
side="white"
opening_tags=[
  {eco="D00", name="Queen's Pawn Game"},
  {eco="D00", name="Queen's Pawn Game"},
]
""")


@pytest.mark.parametrize("version", [1, 2, 4])
def test_rejects_every_non_v3_version_without_fallback(version: int) -> None:
    with pytest.raises(FlowValidationError, match="expected 3"):
        FlowStore().decode(
            f'version={version}\nname="Old"\nstart_fen="startpos"\nside="white"\n'
        )


def test_rejects_v2_fields_instead_of_translating_them() -> None:
    with pytest.raises(FlowValidationError, match="Unknown fields"):
        FlowStore().decode("""
version=3
name="No compatibility"
start_fen="startpos"
side="white"
[[rules]]
id="old"
priority=10
move={piece="piece:white:pawn:d",to="d4"}
""")


@pytest.mark.parametrize(
    "condition, expected",
    [
        ({"moved": "piece:white:pawn:d"}, False),
        ({"unmoved": "piece:white:pawn:d"}, True),
        ({"captured": "piece:white:pawn:d"}, False),
        ({"at": {"piece": "piece:white:pawn:d", "square": "d2"}}, True),
        ({"occupied": "d2"}, True),
        ({"empty": "e4"}, True),
        ({"occupied_by": {"square": "d2", "color": "white", "type": "pawn"}}, True),
        ({"attacked": "piece:white:king"}, False),
        (
            {
                "attacked_by": {
                    "target": "piece:white:pawn:d",
                    "attacker": "piece:black:pawn:d",
                }
            },
            False,
        ),
        ({"in_check": "white"}, False),
        ({"all": [{"occupied": "d2"}, {"empty": "d4"}]}, True),
        ({"any": [{"empty": "d2"}, {"occupied": "e2"}]}, True),
        ({"not": {"empty": "d2"}}, True),
    ],
)
def test_evaluates_v3_condition_language(condition: dict, expected: bool) -> None:
    board = chess.Board()
    tracker = OriginalPieceTracker(board)
    result = ConditionEvaluator(board, tracker, {}).evaluate(parse_condition(condition))
    assert result.value is expected
    assert result.explanation


def test_last_move_and_named_condition_reference_evaluate() -> None:
    board = chess.Board()
    tracker = OriginalPieceTracker(board)
    conditions = {
        "ready": parse_condition(
            {"at": {"piece": "piece:white:pawn:d", "square": "d2"}}
        )
    }
    last_move = LastMove(OriginalPieceId.parse("black:c7"), "c5")
    evaluator = ConditionEvaluator(board, tracker, conditions, last_move)
    assert evaluator.evaluate(parse_condition({"condition": "ready"})).value
    assert evaluator.evaluate(
        parse_condition(
            {
                "last_move": {
                    "piece": "piece:black:pawn:c",
                    "to": "c5",
                }
            }
        )
    ).value


def test_last_move_unlocks_an_immediate_response_and_latches() -> None:
    flow = FlowStore().decode("""
version=3
name="Immediate response"
start_fen="startpos"
side="white"
[[responses]]
id="meet-c5"
move={piece="piece:white:pawn:d",to="d5"}
unlock_when={last_move={piece="piece:black:pawn:c",to="c5"}}
when={at={piece="piece:white:pawn:d",square="d4"}}
[[development]]
id="d4"
piece="piece:white:pawn:d"
target="d4"
""")
    runtime, board = PolicyRuntime.replay(flow, ("d4", "c5"))
    decision = runtime.resolve(board)
    assert decision.source is DecisionSource.RESPONSE
    assert decision.source_id == "meet-c5"
    assert decision.move_san == "d5"
    assert runtime.rule_states["meet-c5"].unlocked


def test_rejects_condition_cycles_unknown_scopes_and_overlapping_development() -> None:
    with pytest.raises(FlowValidationError, match="cycle"):
        FlowStore().decode("""
version=3
name="Cycle"
start_fen="startpos"
side="white"
[[conditions]]
id="a"
when={condition="b"}
[[conditions]]
id="b"
when={condition="a"}
""")

    with pytest.raises(FlowValidationError, match="unknown structures"):
        FlowStore().decode("""
version=3
name="Scope"
start_fen="startpos"
side="white"
[[responses]]
id="one"
structures=["missing"]
move={piece="piece:white:pawn:d",to="d4"}
""")

    with pytest.raises(FlowValidationError, match="overlapping"):
        FlowStore().decode("""
version=3
name="Overlap"
start_fen="startpos"
side="white"
[[structures]]
id="shell"
name="Shell"
available_when={occupied="d2"}
selected_when={at={piece="piece:white:pawn:c",square="c3"}}
[[development]]
id="one"
piece="piece:white:pawn:c"
target="c3"
structures=["shell"]
[[development]]
id="two"
piece="piece:white:pawn:c"
target="c4"
structures=["shell"]
""")


def test_rejects_structure_selected_in_initial_position() -> None:
    with pytest.raises(FlowValidationError, match="initial position"):
        FlowStore().decode("""
version=3
name="Initial selection"
start_fen="startpos"
side="white"
[[structures]]
id="bad"
name="Bad"
available_when={occupied="d2"}
selected_when={at={piece="piece:white:pawn:d",square="d2"}}
""")


def test_static_authoring_warnings_are_non_fatal() -> None:
    flow = FlowStore().decode("""
version=3
name="Warnings"
start_fen="startpos"
side="white"
[[conditions]]
id="unused-condition"
when={empty="e4"}
[[structures]]
id="unused-structure"
name="Unused"
available_when={empty="e4"}
selected_when={at={piece="piece:white:pawn:e",square="e4"}}
""")
    warnings = FlowStore().warnings(flow)
    assert any("unused-condition" in item for item in warnings)
    assert any("unused-structure" in item for item in warnings)


def test_resolution_uses_override_then_sections_then_authored_order() -> None:
    flow = FlowStore().load(FIXTURE)
    runtime, board = PolicyRuntime.replay(flow, ("d4", "e5"))
    decision = runtime.resolve(board)
    assert decision.source is DecisionSource.EXACT_OVERRIDE
    assert decision.move_san == "dxe5"

    decision = PolicyRuntime(flow).resolve(chess.Board())
    assert decision.source is DecisionSource.DEVELOPMENT
    assert decision.source_id == "develop-d-pawn"
    assert decision.move_san == "d4"

    empty = FlowStore().decode(
        'version=3\nname="Empty"\nstart_fen="startpos"\nside="white"\n'
    )
    assert PolicyRuntime(empty).resolve(chess.Board()).source is DecisionSource.FRONTIER


def test_illegal_earlier_rule_waits_and_next_rule_wins() -> None:
    flow = FlowStore().decode("""
version=3
name="Fallback"
start_fen="startpos"
side="white"
[[responses]]
id="blocked-bishop"
move={piece="piece:white:bishop:queenside",to="f4"}
[[responses]]
id="pawn"
move={piece="piece:white:pawn:d",to="d4"}
""")
    decision = PolicyRuntime(flow).resolve(chess.Board())
    assert decision.source_id == "pawn"
    blocked = next(
        item for item in decision.item_resolutions if item.rule.id == "blocked-bishop"
    )
    assert blocked.status.value == "waiting"
    assert not blocked.legal


def test_unlock_latches_expiration_wins_and_execution_retires() -> None:
    flow = FlowStore().decode("""
version=3
name="Lifecycle"
start_fen="startpos"
side="white"
[[responses]]
id="latched"
move={piece="piece:white:pawn:c",to="c4"}
unlock_when={at={piece="piece:black:knight:queenside",square="c6"}}
when={unmoved="piece:white:pawn:c"}
[[responses]]
id="retirement-wins"
move={piece="piece:white:pawn:e",to="e4"}
unlock_when={moved="piece:white:pawn:d"}
expire_when={moved="piece:white:pawn:d"}
""")
    runtime, _ = PolicyRuntime.replay(flow, ("d4", "Nc6", "Nf3", "Nb8"))
    assert runtime.rule_states["latched"].unlocked
    runtime, _ = PolicyRuntime.replay(flow, ("d4",))
    losing = runtime.rule_states["retirement-wins"]
    assert losing.retired
    assert losing.unlocked_at_ply is None

    one_shot = FlowStore().decode("""
version=3
name="One shot"
start_fen="startpos"
side="white"
[[responses]]
id="d4"
move={piece="piece:white:pawn:d",to="d4"}
""")
    runtime, _ = PolicyRuntime.replay(one_shot, ("d4",))
    assert runtime.rule_states["d4"].retired


def test_structure_selection_is_ordered_latched_and_scopes_items() -> None:
    flow = FlowStore().decode("""
version=3
name="Structures"
start_fen="startpos"
side="white"
[[structures]]
id="first"
name="First"
available_when={moved="piece:white:pawn:d"}
selected_when={moved="piece:white:pawn:d"}
[[structures]]
id="second"
name="Second"
available_when={moved="piece:white:pawn:d"}
selected_when={moved="piece:white:pawn:d"}
[[development]]
id="d4"
piece="piece:white:pawn:d"
target="d4"
[[development]]
id="first-c3"
piece="piece:white:pawn:c"
target="c3"
structures=["first"]
[[development]]
id="second-c4"
piece="piece:white:pawn:c"
target="c4"
structures=["second"]
""")
    runtime, board = PolicyRuntime.replay(flow, ("d4", "Nf6"))
    assert runtime.selected_structure_id == "first"
    decision = runtime.resolve(board)
    assert decision.source_id == "first-c3"
    second = next(
        item for item in decision.item_resolutions if item.rule.id == "second-c4"
    )
    assert second.status.value == "out-of-scope"


def test_tracker_handles_capture_castling_en_passant_and_promotion() -> None:
    runtime, board = PolicyRuntime.replay(
        FlowStore().decode(
            'version=3\nname="Track"\nstart_fen="startpos"\nside="white"\n'
        ),
        ("e4", "a6", "e5", "d5", "exd6", "Nf6", "Nf3", "e6", "Be2", "Be7", "O-O"),
    )
    white_pawn = runtime.tracker.get(OriginalPieceId.parse("white:e2"))
    black_pawn = runtime.tracker.get(OriginalPieceId.parse("black:d7"))
    rook = runtime.tracker.get(OriginalPieceId.parse("white:h1"))
    assert chess.square_name(white_pawn.current_square or 0) == "d6"
    assert black_pawn.captured and black_pawn.current_square is None
    assert rook.has_moved and chess.square_name(rook.current_square or 0) == "f1"
    assert board.king(chess.WHITE) == chess.G1

    promotion_flow = FlowStore().decode(
        'version=3\nname="Promotion"\n'
        'start_fen="8/P7/8/8/8/8/7p/k6K w - - 0 1"\nside="white"\n'
    )
    promoted, _ = PolicyRuntime.replay(promotion_flow, ("a8=Q",))
    pawn = next(item for item in promoted.tracker.pieces if str(item.id) == "white:a7")
    assert pawn.piece_type == chess.QUEEN and pawn.has_moved
