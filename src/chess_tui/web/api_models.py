"""Typed request and complete-workspace response models for the v3 web API."""

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
        "inspect_opening",
        "list_openings",
        "list_defenses",
        "inspect_book",
        "inspect_book_history",
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
    note: str | None = None
    move: MoveActionRequest
    structures: list[str] = Field(default_factory=list)
    unlock_when: dict[str, object] | None = None
    when: dict[str, object] | None = None
    expire_when: dict[str, object] | None = None


class UpdateOverrideRequest(ApiModel):
    after_san: list[str]
    note: str | None = None
    move: MoveActionRequest


class DevelopmentRuleDraftRequest(ApiModel):
    id: str | None = Field(default=None, min_length=1, max_length=100)
    piece: str = Field(min_length=3, max_length=80)
    target: str = Field(min_length=2, max_length=2)
    structures: list[str] = Field(default_factory=list)
    note: str | None = None
    ready_when: dict[str, object] | None = None


class DevelopmentOrderRequest(ApiModel):
    rule_ids: list[str] = Field(min_length=1)


class PolicyOrderRequest(ApiModel):
    item_ids: list[str] = Field(min_length=1)


class UpdateStructureRequest(ApiModel):
    name: str = Field(min_length=1, max_length=120)
    note: str | None = None
    available_when: dict[str, object]
    selected_when: dict[str, object]


class StructureOrderRequest(ApiModel):
    structure_ids: list[str] = Field(min_length=1)


class DevelopmentRuleValidationResponse(ApiModel):
    valid: bool
    rule_id: str
    piece: str
    target: str
    order: int
    errors: list[str] = Field(default_factory=list)


class OpeningTagRequest(ApiModel):
    record_id: int = Field(ge=0)


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


class AnalysisSettingsRequest(ApiModel):
    profile_id: Literal["blunder-check", "quick", "analysis", "deep"]


class AnalysisProfileSnapshot(ApiModel):
    id: str
    label: str
    depth: int
    cost_label: str
    cost_description: str


class AnalysisSettingsSnapshot(ApiModel):
    status: Literal["off", "configured", "ready", "error"]
    engine_name: str | None = None
    selected_profile_id: str
    profiles: list[AnalysisProfileSnapshot] = Field(default_factory=list)
    candidate_count: int = 4
    billing_note: str = "Local engine: no API or per-analysis fee."


class AnalysisRunSnapshot(ApiModel):
    engine_name: str
    profile_id: str
    requested_depth: int | None = None
    actual_depth: int | None = None
    selective_depth: int | None = None
    nodes: int | None = None
    nps: int | None = None
    time_ms: int | None = None
    lines: int = 1


class FlowSourceResponse(ApiModel):
    path: str
    content: str


class OpeningTagSnapshot(ApiModel):
    record_id: int | None
    eco: str
    name: str


class FlowSnapshot(ApiModel):
    name: str
    version: int
    path: str
    side: Literal["white", "black"]
    opening_tags: list[OpeningTagSnapshot] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    policy_model: Literal["deterministic-v3"] = "deterministic-v3"


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
    section: Literal["response", "development", "continuation"]
    id: str
    order: int
    structures: list[str] = Field(default_factory=list)
    piece: str
    destination: str
    move_uci: str | None
    move_san: str | None
    legal: bool
    lifecycle: Literal["locked", "unlocked", "retired"]
    status: Literal[
        "locked",
        "inactive",
        "waiting",
        "applicable",
        "selected",
        "retired",
        "out-of-scope",
    ]
    selected: bool
    shadowed: bool
    note: str | None
    unlock_when: ConditionSnapshot | None
    when: ConditionSnapshot | None
    expire_when: ConditionSnapshot | None
    unlocked_at_ply: int | None
    retired_at_ply: int | None
    reason: str


class DevelopmentRuleSnapshot(ApiModel):
    id: str
    target: str
    order: int
    structures: list[str] = Field(default_factory=list)
    status: Literal[
        "inactive",
        "waiting",
        "applicable",
        "selected",
        "developed",
        "captured",
        "out-of-scope",
    ]
    ready_when: ConditionSnapshot | None
    note: str | None
    reason: str


class StartingPieceSnapshot(ApiModel):
    ref: str
    original_piece_id: str
    color: Literal["white", "black"]
    piece_type: Literal["pawn", "rook", "knight", "bishop", "queen", "king"]
    qualifier: str | None
    label: str
    starting_square: str
    current_square: str | None
    state: Literal[
        "undeveloped",
        "developed",
        "captured-undeveloped",
        "captured-developed",
    ]
    first_moved_ply: int | None
    captured_ply: int | None
    development_rules: list[DevelopmentRuleSnapshot] = Field(default_factory=list)


class StructureRuntimeSnapshot(ApiModel):
    id: str
    name: str
    status: Literal["unavailable", "available", "selected", "rejected"]
    available_when: ConditionSnapshot
    selected_when: ConditionSnapshot
    selected_at_ply: int | None
    note: str | None
    reason: str


class OverrideRuntimeSnapshot(ApiModel):
    kind: Literal["exact-override"] = "exact-override"
    id: str
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
    responses: list[RuleRuntimeSnapshot] = Field(default_factory=list)
    development: list[RuleRuntimeSnapshot] = Field(default_factory=list)
    continuations: list[RuleRuntimeSnapshot] = Field(default_factory=list)
    overrides: list[OverrideRuntimeSnapshot] = Field(default_factory=list)
    structures: list[StructureRuntimeSnapshot] = Field(default_factory=list)


class DecisionSnapshot(ApiModel):
    status: Literal["ready", "frontier"]
    move_uci: str | None
    move_san: str | None
    source: Literal[
        "response", "development", "continuation", "exact-override", "frontier"
    ]
    source_id: str | None
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
    source: Literal[
        "response", "development", "continuation", "exact-override", "frontier"
    ]
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
    analysis: AnalysisRunSnapshot | None = None


class NavigationSnapshot(ApiModel):
    can_back: bool
    can_restart: bool


class OpeningMatchSnapshot(ApiModel):
    record_id: int
    eco: str
    name: str
    family: str
    variation: str | None
    line_depth: int


class BookContinuationSnapshot(ApiModel):
    uci: str
    san: str
    opening_names: list[str] = Field(default_factory=list)
    defense_names: list[str] = Field(default_factory=list)


class OpeningContextSnapshot(ApiModel):
    primary_match: OpeningMatchSnapshot | None
    current_matches: list[OpeningMatchSnapshot] = Field(default_factory=list)
    last_known_match: OpeningMatchSnapshot | None
    entered: list[OpeningMatchSnapshot] = Field(default_factory=list)
    maintained: list[OpeningMatchSnapshot] = Field(default_factory=list)
    exited: list[OpeningMatchSnapshot] = Field(default_factory=list)
    played_move_in_book: bool | None
    book_continuations: list[BookContinuationSnapshot] = Field(default_factory=list)
    reachable_defenses: list[str] = Field(default_factory=list)
    move_source: (
        Literal[
            "book-and-policy",
            "policy-only",
            "exact-override",
            "recorded-branch",
            "book",
            "engine",
            "manual",
            "frontier",
        ]
        | None
    )
    policy_rule_id: str | None
    exact_override_id: str | None
    recorded_reply_id: str | None


class OpeningHistoryItemSnapshot(ApiModel):
    ply: int
    san: str
    uci: str
    position_key: str
    context: OpeningContextSnapshot


class BookMoveSnapshot(ApiModel):
    uci: str
    san: str
    source: Literal["opening-index", "book-and-policy", "policy", "opponent-branch"]
    opening_names: list[str] = Field(default_factory=list)
    defense_names: list[str] = Field(default_factory=list)


class EngineMoveSnapshot(ApiModel):
    uci: str
    san: str
    evaluation_cp: int | None = None
    mate_in: int | None = None
    principal_variation: list[str] = Field(default_factory=list)


class PositionAnalysisSnapshot(ApiModel):
    book_moves: list[BookMoveSnapshot] = Field(default_factory=list)
    engine_moves: list[EngineMoveSnapshot] = Field(default_factory=list)
    engine: AnalysisRunSnapshot | None = None


class AvailableCommandSnapshot(ApiModel):
    id: str
    slash: str
    usage: str
    description: str
    arguments: list[dict[str, object]] = Field(default_factory=list)


class OpeningContextAttachment(ApiModel):
    kind: Literal["opening-context"] = "opening-context"
    entry: OpeningHistoryItemSnapshot | None
    context: OpeningContextSnapshot
    presentation: Literal["compact", "transition", "current"]


class OpeningListAttachment(ApiModel):
    kind: Literal["opening-list"] = "opening-list"
    primary_match: OpeningMatchSnapshot | None
    matches: list[OpeningMatchSnapshot] = Field(default_factory=list)


class DefenseListAttachment(ApiModel):
    kind: Literal["defense-list"] = "defense-list"
    reachable: list[str] = Field(default_factory=list)
    entered: list[str] = Field(default_factory=list)


class BookDetailsAttachment(ApiModel):
    kind: Literal["book-details"] = "book-details"
    played_move_in_book: bool | None
    continuations: list[BookContinuationSnapshot] = Field(default_factory=list)


class BookHistoryAttachment(ApiModel):
    kind: Literal["book-history"] = "book-history"
    entries: list[OpeningHistoryItemSnapshot] = Field(default_factory=list)
    first_policy_without_book_ply: int | None


class PositionAnalysisAttachment(ApiModel):
    kind: Literal["position-analysis"] = "position-analysis"
    analysis: PositionAnalysisSnapshot


class PolicyReferenceSnapshot(ApiModel):
    kind: Literal["rule", "exact-override"]
    id: str
    move_san: str | None = None
    note: str | None = None
    reason: str


class DecisionExplanationAttachment(ApiModel):
    kind: Literal["decision-explanation"] = "decision-explanation"
    selected: PolicyReferenceSnapshot | None
    waiting: list[PolicyReferenceSnapshot] = Field(default_factory=list)
    applicable_later: list[PolicyReferenceSnapshot] = Field(default_factory=list)
    unavailable: list[PolicyReferenceSnapshot] = Field(default_factory=list)
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
    OpeningContextAttachment
    | OpeningListAttachment
    | DefenseListAttachment
    | BookDetailsAttachment
    | BookHistoryAttachment
    | PositionAnalysisAttachment
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
    kind: Literal["info", "move", "success", "warning", "commentary"]
    title: str
    message: str
    attachment: OpeningContextAttachment | None = None


class WorkspaceSnapshot(ApiModel):
    session_id: str
    mode: Literal["develop"] = "develop"
    phase: Literal["policy-ready", "policy-result", "opponent-ready", "game-over"]
    flow: FlowSnapshot
    position: PositionSnapshot
    decision: DecisionSnapshot | None
    attempt: AttemptSnapshot | None
    rules: RuleGroupsSnapshot
    starting_pieces: list[StartingPieceSnapshot] = Field(default_factory=list)
    opening: OpeningContextSnapshot
    opening_history: list[OpeningHistoryItemSnapshot] = Field(default_factory=list)
    evaluation: EvaluationSnapshot
    analysis_settings: AnalysisSettingsSnapshot
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
