from __future__ import annotations

import pytest

from chess_tui.commands import (
    CommandAvailability,
    CommandFailure,
    CommandId,
    CommandRegistry,
)


def context(**overrides: object) -> CommandAvailability:
    values: dict[str, object] = {
        "phase": "policy-ready",
        "engine_available": True,
        "has_decision": True,
        "has_decision_move": True,
        "mismatch": False,
        "can_back": False,
        "can_restart": False,
        "has_rules": True,
    }
    values.update(overrides)
    return CommandAvailability(**values)  # type: ignore[arg-type]


def available(**overrides: object) -> set[CommandId]:
    registry = CommandRegistry()
    return {item.id for item in registry.available(context(**overrides))}


def test_policy_ready_command_availability_tracks_engine_and_navigation() -> None:
    commands = available()
    assert {
        CommandId.ANALYSE_POSITION,
        CommandId.EXPLAIN_DECISION,
        CommandId.INSPECT_RULE,
        CommandId.LIST_RULES,
        CommandId.TRACE_DECISION,
        CommandId.INSPECT_POSITION,
        CommandId.INSPECT_OPENING,
        CommandId.LIST_OPENINGS,
        CommandId.LIST_DEFENSES,
        CommandId.INSPECT_BOOK,
        CommandId.INSPECT_BOOK_HISTORY,
        CommandId.PLAY_MOVE,
        CommandId.HINT_POLICY_MOVE,
        CommandId.LIST_COMMANDS,
    } <= commands
    assert CommandId.NEXT_OPPONENT not in commands
    assert CommandId.RESTART not in commands

    commands = available(
        engine_available=False,
        can_back=True,
        can_restart=True,
    )
    assert CommandId.ANALYSE_POSITION not in commands
    assert {CommandId.GO_BACK, CommandId.RESTART} <= commands


def test_mismatch_opponent_frontier_and_game_over_availability() -> None:
    mismatch = available(
        phase="policy-result",
        mismatch=True,
        can_back=True,
        can_restart=True,
    )
    assert {
        CommandId.RETRY_POLICY,
        CommandId.CONTINUE_POLICY,
        CommandId.ADD_RULE_FOR_MISMATCH,
    } <= mismatch
    assert CommandId.PLAY_MOVE not in mismatch

    opponent = available(
        phase="opponent-ready",
        has_decision=False,
        has_decision_move=False,
    )
    assert {CommandId.PLAY_MOVE, CommandId.NEXT_OPPONENT} <= opponent
    assert CommandId.EXPLAIN_DECISION not in opponent
    assert CommandId.HINT_POLICY_MOVE not in opponent

    frontier = available(has_decision=True, has_decision_move=False)
    assert CommandId.EXPLAIN_DECISION in frontier
    assert CommandId.HINT_POLICY_MOVE not in frontier

    game_over = available(
        phase="game-over",
        has_decision=False,
        has_decision_move=False,
        can_back=True,
        can_restart=True,
    )
    assert CommandId.ANALYSE_POSITION not in game_over
    assert CommandId.PLAY_MOVE not in game_over
    assert {CommandId.GO_BACK, CommandId.RESTART} <= game_over


def test_command_availability_is_side_agnostic_for_black_controlled_flows() -> None:
    # Side ownership is intentionally absent from the availability context. A
    # controlled-side turn has the same application commands for either color.
    assert available() == available()


@pytest.mark.parametrize(
    ("text", "command", "move", "rule_id"),
    [
        ("d4", CommandId.PLAY_MOVE, "d4", None),
        ("/play Nf3", CommandId.PLAY_MOVE, "Nf3", None),
        ("/analyse", CommandId.ANALYSE_POSITION, None, None),
        ("/rule develop-d-pawn", CommandId.INSPECT_RULE, None, "develop-d-pawn"),
        ("/why", CommandId.EXPLAIN_DECISION, None, None),
        ("/rules", CommandId.LIST_RULES, None, None),
        ("/trace", CommandId.TRACE_DECISION, None, None),
        ("/position", CommandId.INSPECT_POSITION, None, None),
        ("/opening", CommandId.INSPECT_OPENING, None, None),
        ("/openings", CommandId.LIST_OPENINGS, None, None),
        ("/defenses", CommandId.LIST_DEFENSES, None, None),
        ("/book", CommandId.INSPECT_BOOK, None, None),
        ("/book-history", CommandId.INSPECT_BOOK_HISTORY, None, None),
        ("/next", CommandId.NEXT_OPPONENT, None, None),
        ("/retry", CommandId.RETRY_POLICY, None, None),
        ("/continue", CommandId.CONTINUE_POLICY, None, None),
        ("/add-rule", CommandId.ADD_RULE_FOR_MISMATCH, None, None),
        ("/back", CommandId.GO_BACK, None, None),
        ("/restart", CommandId.RESTART, None, None),
        ("/hint", CommandId.HINT_POLICY_MOVE, None, None),
        ("/help", CommandId.LIST_COMMANDS, None, None),
    ],
)
def test_chat_parser_builds_typed_invocations(
    text: str,
    command: CommandId,
    move: str | None,
    rule_id: str | None,
) -> None:
    invocation = CommandRegistry().parse_chat(text)
    assert invocation.command is command
    assert invocation.source == "chat"
    assert invocation.move == move
    assert invocation.rule_id == rule_id


@pytest.mark.parametrize(
    "text",
    ["", "   ", "/unknown", "/why extra", "/rule", "/play", "/play d4 extra"],
)
def test_chat_parser_rejects_unknown_or_malformed_commands(text: str) -> None:
    with pytest.raises(CommandFailure):
        CommandRegistry().parse_chat(text)
