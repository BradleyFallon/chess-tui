"""Typed HTTP models for the Opening Rule Engine v4 web API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

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


class OpponentModeRequest(ApiModel):
    mode: Literal["stored", "engine", "manual"]


class ActionAttemptRequest(ApiModel):
    move: str | None = Field(default=None, min_length=2, max_length=2)
    capture: str | None = Field(default=None, min_length=1, max_length=100)
    capture_type: (
        Literal["pawn", "knight", "bishop", "rook", "queen", "king"] | None
    ) = None

    @model_validator(mode="after")
    def exactly_one_action(self) -> ActionAttemptRequest:
        if (
            sum(
                value is not None
                for value in (self.move, self.capture, self.capture_type)
            )
            != 1
        ):
            raise ValueError("An attempt requires exactly one action.")
        return self


class DevelopmentDraftRequest(ApiModel):
    alias: str = Field(min_length=1, max_length=100)
    to: str = Field(min_length=2, max_length=2)
    requires: list[str] = Field(default_factory=list)
    when: dict[str, object] | None = None
    why: str = Field(min_length=1)


class InterruptDraftRequest(ApiModel):
    alias: str = Field(min_length=1, max_length=100)
    id: str | None = Field(default=None, min_length=1, max_length=100)
    requires: list[str] = Field(default_factory=list)
    after_san: list[str] | None = None
    when: dict[str, object] | None = None
    required: bool = False
    attempts: list[ActionAttemptRequest] = Field(min_length=1)
    why: str = Field(min_length=1)


class DevelopmentOrderRequest(ApiModel):
    aliases: list[str]


class InterruptOrderRequest(ApiModel):
    rule_refs: list[str]


class OpeningTagRequest(ApiModel):
    record_id: int = Field(ge=0)


class AnalysisSettingsRequest(ApiModel):
    profile_id: Literal["blunder-check", "quick", "analysis", "deep"]


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
    source: str


class OpeningTagSnapshot(ApiModel):
    eco: str
    name: str


class RulebookSnapshot(ApiModel):
    name: str
    version: int
    path: str
    side: Literal["white", "black"]
    opening_tags: list[OpeningTagSnapshot] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class PositionSnapshot(ApiModel):
    fen: str
    history_san: list[str]
    turn: Literal["white", "black"]
    legal_moves_uci: list[str]
    last_move_uci: str | None
    game_over: str | None = None


class ConditionEvaluationSnapshot(ApiModel):
    value: bool
    explanation: str
    details: dict[str, object] = Field(default_factory=dict)


class ActionAttemptSnapshot(ApiModel):
    kind: Literal["move", "capture-attacker", "capture-piece", "capture-type"]
    value: str
    status: Literal["not-evaluated", "failed", "resolved", "ambiguous"]
    candidates: list[str] = Field(default_factory=list)
    reason: str | None = None


class DevelopmentInstructionSnapshot(ApiModel):
    reference: str
    to: str
    requires: list[str]
    when: dict[str, object] | None
    why: str
    status: Literal[
        "not-ready",
        "waiting-for-legality",
        "available",
        "selected",
        "completed",
        "captured",
    ]
    explanation: str
    condition: ConditionEvaluationSnapshot | None = None


class InterruptRuleSnapshot(ApiModel):
    reference: str
    id: str
    requires: list[str]
    after_san: list[str] | None
    when: dict[str, object] | None
    required: bool
    attempts: list[ActionAttemptSnapshot]
    why: str
    status: Literal[
        "trigger-false",
        "no-action",
        "applicable",
        "selected",
        "completed",
        "ambiguous",
        "required-unhandled",
    ]
    explanation: str
    trigger: ConditionEvaluationSnapshot | None = None


class AttackSnapshot(ApiModel):
    piece: str
    alias: str | None
    move_uci: str


class DefenseSnapshot(ApiModel):
    piece: str
    alias: str | None
    move_uci: str


class DefendersAgainstSnapshot(ApiModel):
    attacker: str
    attacker_alias: str | None
    defenders: list[DefenseSnapshot]


class PieceRelationSnapshot(ApiModel):
    attacks: list[AttackSnapshot]
    attackers: list[AttackSnapshot]
    defenders_by_attacker: list[DefendersAgainstSnapshot]
    distinct_defenders: list[str]
    attacker_count: int
    defender_count: int
    attack_balance: int
    attacked: bool
    undefended: bool
    under_defended: bool
    king_pinned: bool
    pinned_by: str | None


class PieceScriptSnapshot(ApiModel):
    alias: str
    ref: str
    label: str
    current_square: str | None
    mechanical_state: Literal[
        "undeveloped", "developed", "captured-undeveloped", "captured-developed"
    ]
    authorable: bool
    development: DevelopmentInstructionSnapshot | None
    interrupts: list[InterruptRuleSnapshot]
    relationships: PieceRelationSnapshot


class FrontierSnapshot(ApiModel):
    reason: Literal[
        "development-complete",
        "no-authored-legal-move",
        "unhandled-required-rule",
        "ambiguous-action",
    ]
    explanation: str


class DecisionSnapshot(ApiModel):
    status: Literal["ready", "frontier"]
    source: Literal["interrupt", "development", "frontier"]
    move_uci: str | None
    move_san: str | None
    instruction_ref: str | None
    why: str | None
    frontier: FrontierSnapshot | None
    trace: list[str]


class AttemptSnapshot(ApiModel):
    result: Literal["correct", "mismatch", "frontier"]
    move_uci: str
    move_san: str
    expected_uci: str | None
    expected_san: str | None


class NavigationSnapshot(ApiModel):
    can_back: bool
    can_restart: bool


class TimelineEntrySnapshot(ApiModel):
    id: int
    kind: Literal[
        "system",
        "user",
        "assistant",
        "move",
        "success",
        "warning",
        "error",
        "opening",
        "analysis",
    ]
    title: str
    message: str


class AvailableCommandSnapshot(ApiModel):
    id: str
    slash: str
    usage: str
    description: str
    arguments: list[str] = Field(default_factory=list)


class AnalysisProfileSnapshot(ApiModel):
    id: str
    label: str
    depth: int
    cost_label: str
    cost_description: str


class AnalysisSettingsSnapshot(ApiModel):
    status: Literal["off", "configured", "ready", "error"]
    selected_profile_id: str
    engine_name: str | None = None
    profiles: list[AnalysisProfileSnapshot] = Field(default_factory=list)


class OpponentSettingsSnapshot(ApiModel):
    mode: Literal["stored", "engine", "manual"]
    stored_reply_available: bool
    engine_available: bool
    last_source: Literal["stored", "engine", "manual"] | None = None


class OpeningSummarySnapshot(ApiModel):
    record_id: int | None = None
    name: str | None = None
    eco: str | None = None
    last_known_name: str | None = None
    move_source: str | None = None
    book_continuations: list[str] = Field(default_factory=list)
    reachable_defenses: list[str] = Field(default_factory=list)
    is_tagged: bool = False


class OpeningHistorySnapshot(ApiModel):
    ply: int
    san: str
    opening_name: str | None = None
    move_source: str | None = None


class EvaluationSnapshot(ApiModel):
    status: Literal["off", "ready", "error"] = "off"
    centipawns: int | None = None
    mate_in: int | None = None
    previous_centipawns: int | None = None
    previous_mate_in: int | None = None
    change_centipawns: int | None = None
    message: str | None = None
    engine_name: str | None = None
    profile_id: str | None = None
    requested_depth: int | None = None
    actual_depth: int | None = None
    selective_depth: int | None = None
    nodes: int | None = None
    nps: int | None = None
    time_ms: int | None = None
    best_move_uci: str | None = None
    best_move_san: str | None = None


class EngineLineSnapshot(ApiModel):
    uci: str
    san: str
    centipawns: int | None = None
    mate_in: int | None = None
    principal_variation: list[str] = Field(default_factory=list)


class PositionAnalysisSnapshot(ApiModel):
    book_moves: list[str] = Field(default_factory=list)
    engine_moves: list[EngineLineSnapshot] = Field(default_factory=list)


class WorkspaceSnapshot(ApiModel):
    session_id: str
    mode: Literal["develop"] = "develop"
    rulebook: RulebookSnapshot
    position: PositionSnapshot
    decision: DecisionSnapshot | None
    piece_scripts: list[PieceScriptSnapshot]
    development_order: list[str]
    interrupt_order: list[str]
    attempt: AttemptSnapshot | None
    navigation: NavigationSnapshot
    evaluation: EvaluationSnapshot = Field(default_factory=EvaluationSnapshot)
    analysis_settings: AnalysisSettingsSnapshot
    opponent: OpponentSettingsSnapshot
    opening: OpeningSummarySnapshot
    opening_history: list[OpeningHistorySnapshot] = Field(default_factory=list)
    position_analysis: PositionAnalysisSnapshot | None = None
    timeline: list[TimelineEntrySnapshot] = Field(default_factory=list)
    available_commands: list[AvailableCommandSnapshot] = Field(default_factory=list)
    hint_move_uci: str | None = None
    rulebook_source: str = ""
    errors: list[str] = Field(default_factory=list)


class MutationPreviewResponse(ApiModel):
    valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    current_decision: str | None = None
    preview_decision: str | None = None
    generated_toml: str | None = None


class AnalysisRunSnapshot(ApiModel):
    status: Literal["off", "ready", "error"]
    centipawns: int | None = None
    mate_in: int | None = None
    move_uci: str | None = None
    move_san: str | None = None
    message: str | None = None
    engine_name: str | None = None
    profile_id: str | None = None
    requested_depth: int | None = None
    actual_depth: int | None = None
    selective_depth: int | None = None
    nodes: int | None = None
    nps: int | None = None
    time_ms: int | None = None
