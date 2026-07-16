"""Typed request and complete-workspace response models for the v2 web API."""

from __future__ import annotations

from typing import Annotated, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field

from .errors import ApiErrorCode


def _to_camel(value: str) -> str:
    first, *rest = value.split("_")
    return first + "".join(part.capitalize() for part in rest)


class ApiModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=_to_camel, populate_by_name=True, extra="forbid"
    )


class CreateSessionRequest(ApiModel):
    flow_path: str | None = None


class MoveRequest(ApiModel):
    uci: str = Field(min_length=4, max_length=5)


class SanMoveRequest(ApiModel):
    san: str = Field(min_length=1, max_length=20)


class ChatRequest(ApiModel):
    text: str = Field(min_length=1, max_length=500)


class SimpleCommandRequest(ApiModel):
    command: Literal[
        "analyse_position",
        "explain_decision",
        "list_rules",
        "trace_decision",
        "inspect_position",
        "next_opponent",
        "retry_policy",
        "continue_policy",
        "add_rule_for_mismatch",
        "go_back",
        "restart",
        "hint_policy_move",
        "list_commands",
    ]
    source: Literal["ui", "tool"] = "ui"


class PlayMoveCommandRequest(ApiModel):
    command: Literal["play_move"]
    source: Literal["ui", "tool"] = "ui"
    notation: Literal["san", "uci"]
    move: str = Field(min_length=1, max_length=20)


class InspectRuleCommandRequest(ApiModel):
    command: Literal["inspect_rule"]
    source: Literal["ui", "tool"] = "ui"
    rule_id: str = Field(min_length=1, max_length=100)


TypedCommandRequest: TypeAlias = Annotated[
    SimpleCommandRequest | PlayMoveCommandRequest | InspectRuleCommandRequest,
    Field(discriminator="command"),
]


class MoveActionRequest(ApiModel):
    piece: str = Field(min_length=3)
    to: str = Field(min_length=2, max_length=2)


class UpdateRuleRequest(ApiModel):
    priority: int
    enabled: bool = True
    note: str | None = None
    move: MoveActionRequest
    activate_when: dict[str, object] | None = None
    retire_when: dict[str, object] | None = None


class UpdateOverrideRequest(ApiModel):
    after_san: list[str]
    enabled: bool = True
    note: str | None = None
    move: MoveActionRequest


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


class FlowSourceResponse(ApiModel):
    path: str
    content: str


class FlowSnapshot(ApiModel):
    name: str
    version: int
    path: str
    side: Literal["white", "black"]
    policy_model: Literal["deterministic-v2"] = "deterministic-v2"


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


class ConditionSnapshot(ApiModel):
    expression: dict[str, object]
    value: bool
    explanation: str


class RuleRuntimeSnapshot(ApiModel):
    kind: Literal["rule"] = "rule"
    id: str
    priority: int
    enabled: bool
    piece: str
    destination: str
    move_uci: str | None
    move_san: str | None
    legal: bool
    lifecycle: Literal["dormant", "active", "retired"]
    status: Literal["selected", "active", "waiting", "dormant", "retired", "disabled"]
    selected: bool
    shadowed: bool
    note: str | None
    activate_when: ConditionSnapshot | None
    retire_when: ConditionSnapshot | None
    activated_at_ply: int | None
    retired_at_ply: int | None
    reason: str


class OverrideRuntimeSnapshot(ApiModel):
    kind: Literal["exact-override"] = "exact-override"
    id: str
    enabled: bool
    after_san: list[str]
    piece: str
    destination: str
    move_uci: str | None
    move_san: str | None
    matched: bool
    legal: bool
    selected: bool
    note: str | None
    reason: str


class RuleGroupsSnapshot(ApiModel):
    selected: RuleRuntimeSnapshot | OverrideRuntimeSnapshot | None
    applies_now: list[RuleRuntimeSnapshot] = Field(default_factory=list)
    waiting: list[RuleRuntimeSnapshot] = Field(default_factory=list)
    dormant: list[RuleRuntimeSnapshot] = Field(default_factory=list)
    retired: list[RuleRuntimeSnapshot] = Field(default_factory=list)
    disabled: list[RuleRuntimeSnapshot] = Field(default_factory=list)
    overrides: list[OverrideRuntimeSnapshot] = Field(default_factory=list)


class DecisionSnapshot(ApiModel):
    status: Literal["ready", "frontier"]
    move_uci: str | None
    move_san: str | None
    source: Literal["rule", "exact-override", "frontier"]
    source_id: str | None
    priority: int | None
    note: str | None
    trace: list[str] = Field(default_factory=list)


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
    result: Literal["correct", "mismatch", "frontier"]
    played_uci: str
    played_san: str
    expected_uci: str | None
    expected_san: str | None
    source: Literal["rule", "exact-override", "frontier"]
    source_id: str | None
    note: str | None
    trace: list[str] = Field(default_factory=list)
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


class BookMoveSnapshot(ApiModel):
    uci: str
    san: str
    source: Literal["local-book", "policy", "opponent-branch"]
    games: int | None = None
    frequency: float | None = None


class EngineMoveSnapshot(ApiModel):
    uci: str
    san: str
    evaluation_cp: int | None = None
    mate_in: int | None = None
    principal_variation: list[str] = Field(default_factory=list)


class PositionAnalysisSnapshot(ApiModel):
    book_moves: list[BookMoveSnapshot] = Field(default_factory=list)
    engine_moves: list[EngineMoveSnapshot] = Field(default_factory=list)


class AvailableCommandSnapshot(ApiModel):
    id: str
    slash: str
    usage: str
    description: str
    arguments: list[dict[str, object]] = Field(default_factory=list)


class PositionAnalysisAttachment(ApiModel):
    kind: Literal["position-analysis"] = "position-analysis"
    analysis: PositionAnalysisSnapshot


class PolicyReferenceSnapshot(ApiModel):
    kind: Literal["rule", "exact-override"]
    id: str
    priority: int | None = None
    move_san: str | None = None
    note: str | None = None
    reason: str


class DecisionExplanationAttachment(ApiModel):
    kind: Literal["decision-explanation"] = "decision-explanation"
    selected: PolicyReferenceSnapshot | None
    higher_priority_waiting: list[PolicyReferenceSnapshot] = Field(default_factory=list)
    shadowed_active: list[PolicyReferenceSnapshot] = Field(default_factory=list)
    dormant: list[PolicyReferenceSnapshot] = Field(default_factory=list)
    condition_reasons: list[str] = Field(default_factory=list)
    provenance: list[str] = Field(default_factory=list)


class RuleDetailsAttachment(ApiModel):
    kind: Literal["rule-details"] = "rule-details"
    rule: RuleRuntimeSnapshot | OverrideRuntimeSnapshot
    provenance: list[str] = Field(default_factory=list)


class RuleListAttachment(ApiModel):
    kind: Literal["rule-list"] = "rule-list"
    groups: RuleGroupsSnapshot


class DecisionTraceAttachment(ApiModel):
    kind: Literal["decision-trace"] = "decision-trace"
    entries: list[str] = Field(default_factory=list)
    provenance: Literal["policy-trace"] = "policy-trace"


class LegalMoveSnapshot(ApiModel):
    uci: str
    san: str


class PositionDetailsAttachment(ApiModel):
    kind: Literal["position-details"] = "position-details"
    fen: str
    history_san: list[str]
    turn: Literal["white", "black"]
    ply: int
    in_check: bool
    last_move_uci: str | None
    legal_moves: list[LegalMoveSnapshot] = Field(default_factory=list)
    game_over: GameOverSnapshot | None


class CommandListAttachment(ApiModel):
    kind: Literal["command-list"] = "command-list"
    commands: list[AvailableCommandSnapshot] = Field(default_factory=list)


class ValidationErrorAttachment(ApiModel):
    kind: Literal["validation-error"] = "validation-error"
    code: str
    details: dict[str, object] = Field(default_factory=dict)


ChatAttachment: TypeAlias = Annotated[
    PositionAnalysisAttachment
    | DecisionExplanationAttachment
    | RuleDetailsAttachment
    | RuleListAttachment
    | DecisionTraceAttachment
    | PositionDetailsAttachment
    | CommandListAttachment
    | ValidationErrorAttachment,
    Field(discriminator="kind"),
]


class ChatMessageSnapshot(ApiModel):
    id: str
    sequence: int
    role: Literal["user", "assistant", "system", "tool"]
    text: str
    attachment: ChatAttachment | None = None


class ActivitySnapshot(ApiModel):
    id: int
    sequence: int
    kind: Literal["info", "move", "success", "warning"]
    title: str
    message: str


class WorkspaceSnapshot(ApiModel):
    session_id: str
    mode: Literal["develop"] = "develop"
    phase: Literal["policy-ready", "policy-result", "opponent-ready", "game-over"]
    flow: FlowSnapshot
    position: PositionSnapshot
    decision: DecisionSnapshot | None
    attempt: AttemptSnapshot | None
    rules: RuleGroupsSnapshot
    evaluation: EvaluationSnapshot
    navigation: NavigationSnapshot
    activity: list[ActivitySnapshot] = Field(default_factory=list)
    chat: list[ChatMessageSnapshot] = Field(default_factory=list)
    available_commands: list[AvailableCommandSnapshot] = Field(default_factory=list)
    errors: list[ApiErrorItem] = Field(default_factory=list)


class HighlightMoveEffect(ApiModel):
    kind: Literal["highlight-move"] = "highlight-move"
    uci: str


class CommandResponse(ApiModel):
    workspace: WorkspaceSnapshot
    effects: list[HighlightMoveEffect] = Field(default_factory=list)
