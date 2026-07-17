"""Immutable persisted models for deterministic version 2 flows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypeAlias

from ..policy.models import Condition, MoveAction, MovedCondition, StartingPieceRef

FlowSide: TypeAlias = Literal["white", "black"]


@dataclass(frozen=True, slots=True)
class OpeningTag:
    eco: str
    name: str


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
    kind: Literal["generic", "development"] = "generic"
    development_ref: StartingPieceRef | None = None


@dataclass(frozen=True, slots=True)
class DevelopmentRule:
    id: str
    piece: StartingPieceRef
    target: str
    priority: int
    enabled: bool = True
    note: str | None = None
    ready_when: Condition | None = None

    def compile(self) -> PolicyRule:
        piece_id = self.piece.original_piece_id
        return PolicyRule(
            id=self.id,
            priority=self.priority,
            move=MoveAction(piece_id, self.target),
            enabled=self.enabled,
            note=self.note,
            activate_when=self.ready_when,
            retire_when=MovedCondition(piece_id),
            kind="development",
            development_ref=self.piece,
        )


AuthoredRule: TypeAlias = PolicyRule | DevelopmentRule


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
    opening_tags: tuple[OpeningTag, ...] = ()
    states: tuple[NamedState, ...] = ()
    rules: tuple[AuthoredRule, ...] = ()
    overrides: tuple[ExactOverride, ...] = ()
    opponent_replies: tuple[OpponentReply, ...] = ()

    @property
    def compiled_rules(self) -> tuple[PolicyRule, ...]:
        return tuple(
            rule.compile() if isinstance(rule, DevelopmentRule) else rule
            for rule in self.rules
        )
