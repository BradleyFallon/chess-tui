"""History-sensitive lifecycle and deterministic v2 policy resolution."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import chess

from ..flow.models import ExactOverride, Flow, PolicyRule
from ..flow.position import normalized_position_key, replay_san
from .conditions import ConditionEvaluator
from .models import (
    ConditionResult,
    EffectiveRuleStatus,
    MoveAction,
    RuleLifecycle,
)
from .tracker import OriginalPieceTracker


class DecisionSource(str, Enum):
    EXACT_OVERRIDE = "exact-override"
    RULE = "rule"
    FRONTIER = "frontier"


@dataclass(slots=True)
class RuleRuntimeState:
    lifecycle: RuleLifecycle
    activated_at_ply: int | None = None
    retired_at_ply: int | None = None
    retirement_reason: str | None = None


@dataclass(frozen=True, slots=True)
class RuleResolution:
    rule: PolicyRule
    lifecycle: RuleLifecycle
    status: EffectiveRuleStatus
    move: chess.Move | None
    move_san: str | None
    legal: bool
    selected: bool
    shadowed: bool
    reason: str
    activation: ConditionResult | None
    retirement: ConditionResult | None
    activated_at_ply: int | None
    retired_at_ply: int | None
    retirement_reason: str | None


@dataclass(frozen=True, slots=True)
class OverrideResolution:
    override: ExactOverride
    matched: bool
    move: chess.Move | None
    move_san: str | None
    legal: bool
    selected: bool
    reason: str


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    source: DecisionSource
    move: chess.Move | None
    move_san: str | None
    source_id: str | None
    priority: int | None
    note: str | None
    rule_resolutions: tuple[RuleResolution, ...]
    override_resolutions: tuple[OverrideResolution, ...]
    trace: tuple[str, ...]


class PolicyRuntime:
    def __init__(self, flow: Flow) -> None:
        self.flow = flow
        self.start_board = _board_from_fen(flow.start_fen)
        self.tracker = OriginalPieceTracker(self.start_board)
        self.states = {state.id: state.when for state in flow.states}
        self.rule_states: dict[str, RuleRuntimeState] = {}
        self.overrides_by_position: dict[str, ExactOverride] = {}
        for override in flow.overrides:
            board = replay_san(
                self.start_board.fen(en_passant="fen"),
                override.after_san,
                context=f"Override {override.id!r}",
            )
            self.overrides_by_position[normalized_position_key(board)] = override
        self._initialize_lifecycle()

    def _initialize_lifecycle(self) -> None:
        evaluator = ConditionEvaluator(self.start_board, self.tracker, self.states)
        for rule in self.flow.rules:
            if not rule.enabled:
                self.rule_states[rule.id] = RuleRuntimeState(RuleLifecycle.DORMANT)
            elif rule.activate_when is None:
                self.rule_states[rule.id] = RuleRuntimeState(
                    RuleLifecycle.ACTIVE, activated_at_ply=0
                )
            elif evaluator.evaluate(rule.activate_when).value:
                self.rule_states[rule.id] = RuleRuntimeState(
                    RuleLifecycle.ACTIVE, activated_at_ply=0
                )
            else:
                self.rule_states[rule.id] = RuleRuntimeState(RuleLifecycle.DORMANT)

    def resolve(self, board: chess.Board) -> PolicyDecision:
        if board.turn != _color(self.flow.side):
            raise ValueError(
                f"Policy controls {self.flow.side}, but it is the opponent's turn."
            )
        evaluator = ConditionEvaluator(board, self.tracker, self.states)
        trace: list[str] = []
        override_results: list[OverrideResolution] = []
        selected_override: tuple[ExactOverride, chess.Move, str] | None = None
        position_key = normalized_position_key(board)
        for override in self.flow.overrides:
            matched = self.overrides_by_position.get(position_key) == override
            move, san, reason = _resolve_action(board, self.tracker, override.move)
            legal = matched and move is not None
            selected = bool(override.enabled and legal and selected_override is None)
            if matched and not override.enabled:
                reason = "Exact position matched, but the override is disabled."
            elif not matched:
                reason = "Exact position does not match."
            elif selected:
                reason = "Exact position matched and the action is legal."
                assert move is not None and san is not None
                selected_override = (override, move, san)
                trace.append(f"Selected exact override {override.id}.")
            elif matched:
                trace.append(f"Skipped exact override {override.id}: {reason}")
            override_results.append(
                OverrideResolution(
                    override,
                    matched,
                    move if matched else None,
                    san if matched else None,
                    legal,
                    selected,
                    reason,
                )
            )

        selected_rule_id: str | None = None
        candidates: dict[str, tuple[chess.Move | None, str | None, str]] = {}
        for rule in sorted(
            self.flow.rules, key=lambda item: item.priority, reverse=True
        ):
            state = self.rule_states[rule.id]
            if rule.enabled and state.lifecycle is RuleLifecycle.ACTIVE:
                move, san, reason = _resolve_action(board, self.tracker, rule.move)
                candidates[rule.id] = (move, san, reason)
                if move is None:
                    trace.append(f"Rule {rule.id} is waiting: {reason}")
                elif selected_override is not None:
                    trace.append(
                        f"Rule {rule.id} is shadowed by exact override {selected_override[0].id}."
                    )
                elif selected_rule_id is None:
                    selected_rule_id = rule.id
                    trace.append(
                        f"Selected rule {rule.id} at priority {rule.priority}."
                    )
                else:
                    trace.append(f"Rule {rule.id} is shadowed by {selected_rule_id}.")

        rule_results: list[RuleResolution] = []
        for rule in sorted(
            self.flow.rules, key=lambda item: item.priority, reverse=True
        ):
            state = self.rule_states[rule.id]
            activation = (
                evaluator.evaluate(rule.activate_when) if rule.activate_when else None
            )
            retirement = (
                evaluator.evaluate(rule.retire_when) if rule.retire_when else None
            )
            move, san, reason = candidates.get(rule.id, (None, None, ""))
            selected = rule.id == selected_rule_id
            shadowed = (
                move is not None and selected_rule_id is not None and not selected
            )
            if not rule.enabled:
                status = EffectiveRuleStatus.DISABLED
                reason = "Rule is disabled."
            elif state.lifecycle is RuleLifecycle.RETIRED:
                status = EffectiveRuleStatus.RETIRED
                reason = state.retirement_reason or "Rule retired."
            elif state.lifecycle is RuleLifecycle.DORMANT:
                status = EffectiveRuleStatus.DORMANT
                reason = (
                    activation.explanation if activation else "Activation is pending."
                )
            elif selected:
                status = EffectiveRuleStatus.SELECTED
                reason = "Highest-priority active legal rule."
            elif move is None:
                status = EffectiveRuleStatus.WAITING
            else:
                status = EffectiveRuleStatus.ACTIVE
                reason = (
                    f"Legal but shadowed by {selected_rule_id or 'an exact override'}."
                )
                shadowed = True
            rule_results.append(
                RuleResolution(
                    rule,
                    state.lifecycle,
                    status,
                    move,
                    san,
                    move is not None,
                    selected,
                    shadowed,
                    reason,
                    activation,
                    retirement,
                    state.activated_at_ply,
                    state.retired_at_ply,
                    state.retirement_reason,
                )
            )

        if selected_override is not None:
            override, move, san = selected_override
            return PolicyDecision(
                DecisionSource.EXACT_OVERRIDE,
                move,
                san,
                override.id,
                None,
                override.note,
                tuple(rule_results),
                tuple(override_results),
                tuple(trace),
            )
        if selected_rule_id is not None:
            resolution = next(
                item for item in rule_results if item.rule.id == selected_rule_id
            )
            assert resolution.move is not None and resolution.move_san is not None
            return PolicyDecision(
                DecisionSource.RULE,
                resolution.move,
                resolution.move_san,
                resolution.rule.id,
                resolution.rule.priority,
                resolution.rule.note,
                tuple(rule_results),
                tuple(override_results),
                tuple(trace),
            )
        trace.append(
            "No active legal rule or exact override resolved; frontier reached."
        )
        return PolicyDecision(
            DecisionSource.FRONTIER,
            None,
            None,
            None,
            None,
            None,
            tuple(rule_results),
            tuple(override_results),
            tuple(trace),
        )

    def commit_move(
        self,
        board_before: chess.Board,
        move: chess.Move,
        board_after: chess.Board,
        *,
        selected_rule_id: str | None = None,
        ply: int,
    ) -> None:
        self.tracker.apply_move(board_before, move)
        evaluator = ConditionEvaluator(board_after, self.tracker, self.states)
        for rule in self.flow.rules:
            state = self.rule_states[rule.id]
            if not rule.enabled or state.lifecycle is RuleLifecycle.RETIRED:
                continue
            result = evaluator.evaluate(rule.retire_when) if rule.retire_when else None
            if rule.id == selected_rule_id or (result is not None and result.value):
                state.lifecycle = RuleLifecycle.RETIRED
                state.retired_at_ply = ply
                state.retirement_reason = (
                    "Selected rule was executed."
                    if rule.id == selected_rule_id
                    else (result.explanation if result is not None else "Retired.")
                )
        for rule in self.flow.rules:
            state = self.rule_states[rule.id]
            if not rule.enabled or state.lifecycle is not RuleLifecycle.DORMANT:
                continue
            if rule.activate_when is not None:
                result = evaluator.evaluate(rule.activate_when)
                if result.value:
                    state.lifecycle = RuleLifecycle.ACTIVE
                    state.activated_at_ply = ply

    @classmethod
    def replay(
        cls, flow: Flow, history_san: tuple[str, ...]
    ) -> tuple[PolicyRuntime, chess.Board]:
        runtime = cls(flow)
        board = _board_from_fen(flow.start_fen)
        for ply, san in enumerate(history_san, start=1):
            before = board.copy(stack=False)
            move = board.parse_san(san)
            selected_rule_id: str | None = None
            if before.turn == _color(flow.side):
                decision = runtime.resolve(before)
                if decision.source is DecisionSource.RULE and decision.move == move:
                    selected_rule_id = decision.source_id
            board.push(move)
            runtime.commit_move(
                before, move, board, selected_rule_id=selected_rule_id, ply=ply
            )
        return runtime, board


def _resolve_action(
    board: chess.Board,
    tracker: OriginalPieceTracker,
    action: MoveAction,
) -> tuple[chess.Move | None, str | None, str]:
    runtime = tracker.get(action.piece)
    if runtime.current_square is None:
        return None, None, f"Original piece {action.piece} has been captured."
    move = chess.Move(runtime.current_square, chess.parse_square(action.to_square))
    if move not in board.legal_moves:
        return None, None, f"{move.uci()} is not legal in the current position."
    return move, board.san(move), "Action is legal."


def _board_from_fen(value: str) -> chess.Board:
    return chess.Board() if value == "startpos" else chess.Board(value)


def _color(value: str) -> chess.Color:
    return chess.WHITE if value == "white" else chess.BLACK
