"""Immutable models for a local White opening policy."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class DefaultRule:
    step: int
    move_san: str
    note: str | None = None


@dataclass(frozen=True, slots=True)
class ExceptionRule:
    id: str
    step: int
    after_san: tuple[str, ...]
    move_san: str
    note: str | None = None


@dataclass(frozen=True, slots=True)
class OpponentReply:
    id: str
    after_san: tuple[str, ...]
    move_san: str
    note: str | None = None


@dataclass(frozen=True, slots=True)
class WhiteFlow:
    version: int
    name: str
    start_fen: str
    defaults: tuple[DefaultRule, ...]
    exceptions: tuple[ExceptionRule, ...]
    opponent_replies: tuple[OpponentReply, ...] = ()


@dataclass(frozen=True, slots=True)
class Recommendation:
    step: int
    move_san: str
    note: str | None
    source: Literal["default", "exception"]
    exception_id: str | None = None
