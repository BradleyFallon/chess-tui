"""Immutable persisted models for deterministic version 2 flows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypeAlias

from ..policy.models import Condition, MoveAction

FlowSide: TypeAlias = Literal["white", "black"]


@dataclass(frozen=True, slots=True)
class NamedState:
    id: str
    when: Condition


@dataclass(frozen=True, slots=True)
class PolicyRule:
    id: str
    priority: int
    move: MoveAction
    enabled: bool = True
    note: str | None = None
    activate_when: Condition | None = None
    retire_when: Condition | None = None


@dataclass(frozen=True, slots=True)
class ExactOverride:
    id: str
    after_san: tuple[str, ...]
    move: MoveAction
    enabled: bool = True
    note: str | None = None


@dataclass(frozen=True, slots=True)
class OpponentReply:
    id: str
    after_san: tuple[str, ...]
    move_san: str
    note: str | None = None


@dataclass(frozen=True, slots=True)
class Flow:
    version: int
    name: str
    start_fen: str
    side: FlowSide
    states: tuple[NamedState, ...] = ()
    rules: tuple[PolicyRule, ...] = ()
    overrides: tuple[ExactOverride, ...] = ()
    opponent_replies: tuple[OpponentReply, ...] = ()
