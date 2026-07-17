"""Immutable persisted models for deterministic version 3 flows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypeAlias

from ..policy.models import Condition, MoveAction, StartingPieceRef

FlowSide: TypeAlias = Literal["white", "black"]
MoveRuleSection: TypeAlias = Literal["response", "continuation"]
PolicySection: TypeAlias = Literal["response", "development", "continuation"]


@dataclass(frozen=True, slots=True)
class OpeningTag:
    eco: str
    name: str


@dataclass(frozen=True, slots=True)
class NamedCondition:
    id: str
    when: Condition


@dataclass(frozen=True, slots=True)
class Structure:
    id: str
    name: str
    available_when: Condition
    selected_when: Condition
    note: str | None = None


@dataclass(frozen=True, slots=True)
class MoveRule:
    id: str
    move: MoveAction
    structures: tuple[str, ...] = ()
    unlock_when: Condition | None = None
    when: Condition | None = None
    expire_when: Condition | None = None
    note: str | None = None


@dataclass(frozen=True, slots=True)
class DevelopmentAssignment:
    id: str
    piece: StartingPieceRef
    target: str
    structures: tuple[str, ...] = ()
    ready_when: Condition | None = None
    note: str | None = None

    @property
    def move(self) -> MoveAction:
        return MoveAction(self.piece.original_piece_id, self.target)


AuthoredPolicyItem: TypeAlias = MoveRule | DevelopmentAssignment


@dataclass(frozen=True, slots=True)
class ExactOverride:
    id: str
    after_san: tuple[str, ...]
    move: MoveAction
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
    opening_tags: tuple[OpeningTag, ...] = ()
    conditions: tuple[NamedCondition, ...] = ()
    structures: tuple[Structure, ...] = ()
    responses: tuple[MoveRule, ...] = ()
    development: tuple[DevelopmentAssignment, ...] = ()
    continuations: tuple[MoveRule, ...] = ()
    overrides: tuple[ExactOverride, ...] = ()
    opponent_replies: tuple[OpponentReply, ...] = ()

    @property
    def policy_items(self) -> tuple[AuthoredPolicyItem, ...]:
        return (*self.responses, *self.development, *self.continuations)

    def section_for(self, item_id: str) -> PolicySection:
        if any(item.id == item_id for item in self.responses):
            return "response"
        if any(item.id == item_id for item in self.development):
            return "development"
        if any(item.id == item_id for item in self.continuations):
            return "continuation"
        raise KeyError(item_id)
