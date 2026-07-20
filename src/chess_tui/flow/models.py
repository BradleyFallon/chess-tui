"""Immutable persisted models for Opening Rulebook version 4."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypeAlias

from ..policy.models import ActionAttempt, Condition, StartingPieceRef

FlowSide: TypeAlias = Literal["white", "black"]


@dataclass(frozen=True, slots=True)
class OpeningTag:
    eco: str
    name: str


@dataclass(frozen=True, slots=True)
class DevelopmentInstruction:
    piece: StartingPieceRef
    to_square: str
    requires: tuple[str, ...]
    when: Condition | None
    why: str


@dataclass(frozen=True, slots=True)
class InterruptRule:
    piece: StartingPieceRef
    id: str
    requires: tuple[str, ...]
    after_san: tuple[str, ...] | None
    when: Condition | None
    required: bool
    attempts: tuple[ActionAttempt, ...]
    why: str


@dataclass(frozen=True, slots=True)
class PieceScript:
    id: str
    ref: StartingPieceRef
    development: DevelopmentInstruction | None
    rules: tuple[InterruptRule, ...]


@dataclass(frozen=True, slots=True)
class OpponentReply:
    id: str
    after_san: tuple[str, ...]
    move_san: str
    note: str | None = None


@dataclass(frozen=True, slots=True)
class Rulebook:
    version: int
    name: str
    start_fen: str
    side: FlowSide
    development_order: tuple[str, ...]
    interrupt_order: tuple[str, ...]
    pieces: tuple[PieceScript, ...]
    opening_tags: tuple[OpeningTag, ...] = ()
    opponent_replies: tuple[OpponentReply, ...] = ()

    @property
    def piece_by_alias(self) -> dict[str, PieceScript]:
        return {piece.id: piece for piece in self.pieces}

    @property
    def alias_by_ref(self) -> dict[StartingPieceRef, str]:
        return {piece.ref: piece.id for piece in self.pieces}

    @property
    def interrupt_by_ref(self) -> dict[str, InterruptRule]:
        return {
            f"{piece.id}.{rule.id}": rule
            for piece in self.pieces
            for rule in piece.rules
        }

    def instruction(self, reference: str) -> DevelopmentInstruction | InterruptRule:
        alias, separator, item_id = reference.partition(".")
        if not separator:
            raise KeyError(reference)
        piece = self.piece_by_alias[alias]
        if item_id == "develop" and piece.development is not None:
            return piece.development
        return next(rule for rule in piece.rules if rule.id == item_id)
