"""Typed request and complete-workspace response models."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .errors import ApiErrorCode


def _to_camel(value: str) -> str:
    first, *rest = value.split("_")
    return first + "".join(part.capitalize() for part in rest)


class ApiModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
        extra="forbid",
    )


class CreateSessionRequest(ApiModel):
    flow_path: str | None = None


class MoveRequest(ApiModel):
    uci: str = Field(min_length=4, max_length=5)


class ApiErrorItem(ApiModel):
    code: ApiErrorCode
    message: str
    details: dict[str, object] = Field(default_factory=dict)


class ApiErrorEnvelope(ApiModel):
    error: ApiErrorItem


class EngineHealth(ApiModel):
    status: Literal["off", "configured", "ready", "error"]


class HealthResponse(ApiModel):
    status: Literal["ok"] = "ok"
    engine: EngineHealth


class FlowSnapshot(ApiModel):
    name: str
    version: int
    path: str
    policy_model: Literal["legacy-v1"] = "legacy-v1"


class GameOverSnapshot(ApiModel):
    result: str
    termination: str
    winner: Literal["white", "black"] | None


class PositionSnapshot(ApiModel):
    fen: str
    history_san: list[str]
    turn: Literal["white", "black"]
    ply: int
    last_move_uci: str | None
    legal_moves_uci: list[str]
    game_over: GameOverSnapshot | None


class DecisionSnapshot(ApiModel):
    status: Literal["ready", "frontier", "unavailable"]
    move_uci: str | None
    move_san: str | None
    source: Literal["default", "exception", "frontier"]
    source_id: str | None
    step: int
    priority: int | None = None
    note: str | None
    unavailable_reason: str | None = None


class RuleSummary(ApiModel):
    source: Literal["default", "exception"]
    source_id: str | None
    step: int
    move_san: str
    note: str | None


class RuleGroupsSnapshot(ApiModel):
    selected: RuleSummary | None
    active: list[RuleSummary] = Field(default_factory=list)
    dormant: list[RuleSummary] = Field(default_factory=list)
    retired: list[RuleSummary] = Field(default_factory=list)
    model_message: str


class EngineReviewSnapshot(ApiModel):
    status: Literal["ready", "engine-off", "error"]
    quality: str | None = None
    loss_cp: int | None = None
    best_move_uci: str | None = None
    best_move_san: str | None = None
    evaluation_before_cp: int | None = None
    evaluation_after_cp: int | None = None
    mate_before: int | None = None
    mate_after: int | None = None
    error_message: str | None = None


class AttemptSnapshot(ApiModel):
    result: Literal[
        "correct",
        "mismatch-default",
        "mismatch-exception",
        "frontier",
        "rule-unavailable",
    ]
    played_uci: str
    played_san: str
    expected_uci: str | None
    expected_san: str | None
    source: Literal["default", "exception", "frontier"]
    engine_review: EngineReviewSnapshot | None


class EvaluationSnapshot(ApiModel):
    status: Literal["ready", "analyzing", "engine-off", "error", "game-over"]
    perspective: Literal["white"] = "white"
    centipawns: int | None = None
    mate_in: int | None = None
    previous_centipawns: int | None = None
    previous_mate_in: int | None = None
    change_centipawns: int | None = None
    error_message: str | None = None


class NavigationSnapshot(ApiModel):
    can_back: bool
    can_restart: bool


class ActivitySnapshot(ApiModel):
    id: int
    kind: Literal["info", "move", "success", "warning"]
    title: str
    message: str


class WorkspaceSnapshot(ApiModel):
    session_id: str
    mode: Literal["develop"] = "develop"
    phase: Literal["white-ready", "white-result", "black-ready", "game-over"]
    flow: FlowSnapshot
    position: PositionSnapshot
    decision: DecisionSnapshot | None
    attempt: AttemptSnapshot | None
    rules: RuleGroupsSnapshot
    evaluation: EvaluationSnapshot
    navigation: NavigationSnapshot
    activity: list[ActivitySnapshot] = Field(default_factory=list)
    errors: list[ApiErrorItem] = Field(default_factory=list)
