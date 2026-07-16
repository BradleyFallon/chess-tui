"""Typed application-command primitives shared by UI and future tool callers."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Literal, TypeAlias


class CommandId(str, Enum):
    ANALYSE_POSITION = "analyse_position"
    EXPLAIN_DECISION = "explain_decision"
    INSPECT_RULE = "inspect_rule"
    LIST_RULES = "list_rules"
    TRACE_DECISION = "trace_decision"
    INSPECT_POSITION = "inspect_position"
    PLAY_MOVE = "play_move"
    NEXT_OPPONENT = "next_opponent"
    RETRY_POLICY = "retry_policy"
    CONTINUE_POLICY = "continue_policy"
    ADD_RULE_FOR_MISMATCH = "add_rule_for_mismatch"
    GO_BACK = "go_back"
    RESTART = "restart"
    HINT_POLICY_MOVE = "hint_policy_move"
    LIST_COMMANDS = "list_commands"


CommandSource: TypeAlias = Literal["chat", "ui", "tool"]
MoveNotation: TypeAlias = Literal["san", "uci"]


@dataclass(frozen=True, slots=True)
class CommandArgument:
    name: str
    description: str
    required: bool = True


@dataclass(frozen=True, slots=True)
class CommandDefinition:
    id: CommandId
    slash: str
    usage: str
    description: str
    arguments: tuple[CommandArgument, ...] = ()


@dataclass(frozen=True, slots=True)
class CommandInvocation:
    command: CommandId
    source: CommandSource
    notation: MoveNotation | None = None
    move: str | None = None
    rule_id: str | None = None


@dataclass(frozen=True, slots=True)
class CommandAvailability:
    phase: Literal["policy-ready", "policy-result", "opponent-ready", "game-over"]
    engine_available: bool
    has_decision: bool
    has_decision_move: bool
    mismatch: bool
    can_back: bool
    can_restart: bool
    has_rules: bool


@dataclass(frozen=True, slots=True)
class ClientEffect:
    kind: Literal["highlight-move"]
    uci: str


@dataclass(frozen=True, slots=True)
class ActivityEvent:
    kind: Literal["info", "move", "success", "warning"]
    title: str
    message: str


@dataclass(frozen=True, slots=True)
class AssistantReply:
    text: str
    attachment_kind: str | None = None
    attachment: object | None = None


@dataclass(frozen=True, slots=True)
class CommandOutcome:
    activity: tuple[ActivityEvent, ...] = ()
    reply: AssistantReply | None = None
    effects: tuple[ClientEffect, ...] = ()


@dataclass(frozen=True, slots=True)
class CommandFailure(Exception):
    code: str
    message: str
    details: dict[str, object] = field(default_factory=dict)

    def __str__(self) -> str:
        return self.message
