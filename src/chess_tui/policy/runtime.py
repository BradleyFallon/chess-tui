"""History-sensitive deterministic version 3 policy resolution."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import chess

from ..flow.models import (
    AuthoredPolicyItem,
    DevelopmentAssignment,
    ExactOverride,
    Flow,
    MoveRule,
    PolicySection,
    Structure,
)
from ..flow.position import normalized_position_key, replay_san
from .conditions import ConditionEvaluator
from .models import (
    ConditionResult,
    EffectiveRuleStatus,
    LastMove,
    MoveAction,
    RuleLifecycle,
)
from .tracker import OriginalPieceTracker


class DecisionSource(str, Enum):
    EXACT_OVERRIDE = "exact-override"
    RESPONSE = "response"
    DEVELOPMENT = "development"
    CONTINUATION = "continuation"
    FRONTIER = "frontier"


class StructureStatus(str, Enum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    SELECTED = "selected"
    REJECTED = "rejected"


@dataclass(slots=True)
class RuleRuntimeState:
    unlocked: bool
    unlocked_at_ply: int | None = None
    retired: bool = False
    retired_at_ply: int | None = None
    retirement_reason: str | None = None

    @property
    def lifecycle(self) -> RuleLifecycle:
        if self.retired:
            return RuleLifecycle.RETIRED
        if self.unlocked:
            return RuleLifecycle.UNLOCKED
        return RuleLifecycle.LOCKED


@dataclass(frozen=True, slots=True)
class StructureResolution:
    structure: Structure
    status: StructureStatus
    available: ConditionResult
    selected: ConditionResult
    selected_at_ply: int | None
    reason: str


@dataclass(frozen=True, slots=True)
class PolicyItemResolution:
    item: AuthoredPolicyItem
    section: PolicySection
    status: EffectiveRuleStatus
    lifecycle: RuleLifecycle
    move: chess.Move | None
    move_san: str | None
    legal: bool
    selected: bool
    shadowed: bool
    in_scope: bool
    reason: str
    unlock: ConditionResult | None
    live_condition: ConditionResult | None
    expiration: ConditionResult | None
    unlocked_at_ply: int | None
    retired_at_ply: int | None
    retirement_reason: str | None

    @property
    def rule(self) -> AuthoredPolicyItem:
        """Compatibility-free convenience for presentation code."""

        return self.item


RuleResolution = PolicyItemResolution


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
    note: str | None
    selected_structure_id: str | None
    structure_resolutions: tuple[StructureResolution, ...]
    item_resolutions: tuple[PolicyItemResolution, ...]
    override_resolutions: tuple[OverrideResolution, ...]
    trace: tuple[str, ...]

    @property
    def rule_resolutions(self) -> tuple[PolicyItemResolution, ...]:
        return self.item_resolutions


class PolicyRuntime:
    def __init__(self, flow: Flow) -> None:
        self.flow = flow
        self.start_board = _board_from_fen(flow.start_fen)
        self.tracker = OriginalPieceTracker(self.start_board)
        self.conditions = {item.id: item.when for item in flow.conditions}
        self.last_move: LastMove | None = None
        self.selected_structure_id: str | None = None
        self.selected_structure_at_ply: int | None = None
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

    @property
    def move_rules(self) -> tuple[MoveRule, ...]:
        return (*self.flow.responses, *self.flow.continuations)

    def _initialize_lifecycle(self) -> None:
        evaluator = self._evaluator(self.start_board)
        for rule in self.move_rules:
            unlocked = (
                rule.unlock_when is None or evaluator.evaluate(rule.unlock_when).value
            )
            self.rule_states[rule.id] = RuleRuntimeState(
                unlocked=unlocked,
                unlocked_at_ply=0 if unlocked else None,
            )

    def _evaluator(self, board: chess.Board) -> ConditionEvaluator:
        return ConditionEvaluator(
            board,
            self.tracker,
            self.conditions,
            self.last_move,
        )

    def resolve(self, board: chess.Board) -> PolicyDecision:
        if board.turn != _color(self.flow.side):
            raise ValueError(
                f"Policy controls {self.flow.side}, but it is the opponent's turn."
            )

        evaluator = self._evaluator(board)
        trace: list[str] = []
        structures = self._resolve_structures(evaluator)
        for result in structures:
            trace.append(
                f"Structure {result.structure.id}: {result.status.value} — "
                f"{result.reason}"
            )

        override_results: list[OverrideResolution] = []
        selected_override: tuple[ExactOverride, chess.Move, str] | None = None
        position_key = normalized_position_key(board)
        for override in self.flow.overrides:
            matched = self.overrides_by_position.get(position_key) == override
            move, san, action_reason = _resolve_action(
                board, self.tracker, override.move
            )
            legal = matched and move is not None
            selected = matched and legal and selected_override is None
            if not matched:
                reason = "Exact position does not match."
            elif not legal:
                reason = action_reason
            elif selected:
                reason = "Exact position matched and the action is legal."
                assert move is not None and san is not None
                selected_override = (override, move, san)
            else:
                reason = "A preceding override already matched."
            trace.append(
                f"Override {override.id}: "
                f"{'selected' if selected else 'skipped'} — {reason}"
            )
            override_results.append(
                OverrideResolution(
                    override=override,
                    matched=matched,
                    move=move if matched else None,
                    move_san=san if matched else None,
                    legal=legal,
                    selected=selected,
                    reason=reason,
                )
            )

        selected_id: str | None = None
        results: list[PolicyItemResolution] = []
        sections: tuple[tuple[PolicySection, tuple[AuthoredPolicyItem, ...]], ...] = (
            ("response", self.flow.responses),
            ("development", self.flow.development),
            ("continuation", self.flow.continuations),
        )
        for section, items in sections:
            for item in items:
                result = self._resolve_item(
                    board,
                    evaluator,
                    item,
                    section,
                    can_select=selected_override is None and selected_id is None,
                )
                if result.selected:
                    selected_id = item.id
                results.append(result)
                trace.append(
                    f"{section.title()} {item.id}: {result.status.value} — "
                    f"{result.reason}"
                )

        if selected_override is not None:
            override, move, san = selected_override
            return PolicyDecision(
                source=DecisionSource.EXACT_OVERRIDE,
                move=move,
                move_san=san,
                source_id=override.id,
                note=override.note,
                selected_structure_id=self.selected_structure_id,
                structure_resolutions=structures,
                item_resolutions=tuple(results),
                override_resolutions=tuple(override_results),
                trace=tuple(trace),
            )

        selected_result = next((item for item in results if item.selected), None)
        if selected_result is not None:
            assert (
                selected_result.move is not None
                and selected_result.move_san is not None
            )
            source = {
                "response": DecisionSource.RESPONSE,
                "development": DecisionSource.DEVELOPMENT,
                "continuation": DecisionSource.CONTINUATION,
            }[selected_result.section]
            return PolicyDecision(
                source=source,
                move=selected_result.move,
                move_san=selected_result.move_san,
                source_id=selected_result.item.id,
                note=selected_result.item.note,
                selected_structure_id=self.selected_structure_id,
                structure_resolutions=structures,
                item_resolutions=tuple(results),
                override_resolutions=tuple(override_results),
                trace=tuple(trace),
            )

        trace.append(
            "No exact override, response, development assignment, or continuation "
            "resolved; frontier reached."
        )
        return PolicyDecision(
            source=DecisionSource.FRONTIER,
            move=None,
            move_san=None,
            source_id=None,
            note=None,
            selected_structure_id=self.selected_structure_id,
            structure_resolutions=structures,
            item_resolutions=tuple(results),
            override_resolutions=tuple(override_results),
            trace=tuple(trace),
        )

    def _resolve_item(
        self,
        board: chess.Board,
        evaluator: ConditionEvaluator,
        item: AuthoredPolicyItem,
        section: PolicySection,
        *,
        can_select: bool,
    ) -> PolicyItemResolution:
        in_scope, scope_reason = self._scope(item.structures, evaluator)
        move, san, action_reason = _resolve_action(board, self.tracker, item.move)

        if isinstance(item, DevelopmentAssignment):
            piece = self.tracker.get(item.piece.original_piece_id)
            lifecycle = (
                RuleLifecycle.RETIRED
                if piece.has_moved or piece.captured
                else RuleLifecycle.UNLOCKED
            )
            live = (
                evaluator.evaluate(item.ready_when)
                if item.ready_when is not None
                else None
            )
            if not in_scope:
                status = EffectiveRuleStatus.OUT_OF_SCOPE
                reason = scope_reason
            elif piece.captured:
                status = EffectiveRuleStatus.RETIRED
                reason = f"{item.piece.label} was captured."
            elif piece.has_moved:
                status = EffectiveRuleStatus.RETIRED
                reason = f"{item.piece.label} already moved."
            elif live is not None and not live.value:
                status = EffectiveRuleStatus.INACTIVE
                reason = live.explanation
            elif move is None:
                status = EffectiveRuleStatus.WAITING
                reason = action_reason
            elif can_select:
                status = EffectiveRuleStatus.SELECTED
                reason = "First applicable assignment in development order."
            else:
                status = EffectiveRuleStatus.APPLICABLE
                reason = "Applicable, but an earlier policy item wins."
            return PolicyItemResolution(
                item=item,
                section=section,
                status=status,
                lifecycle=lifecycle,
                move=move,
                move_san=san,
                legal=move is not None,
                selected=status is EffectiveRuleStatus.SELECTED,
                shadowed=status is EffectiveRuleStatus.APPLICABLE,
                in_scope=in_scope,
                reason=reason,
                unlock=None,
                live_condition=live,
                expiration=None,
                unlocked_at_ply=0,
                retired_at_ply=(
                    piece.captured_ply if piece.captured else piece.first_moved_ply
                ),
                retirement_reason=(
                    reason if status is EffectiveRuleStatus.RETIRED else None
                ),
            )

        state = self.rule_states[item.id]
        unlock = (
            evaluator.evaluate(item.unlock_when)
            if item.unlock_when is not None
            else None
        )
        live = evaluator.evaluate(item.when) if item.when is not None else None
        expiration = (
            evaluator.evaluate(item.expire_when)
            if item.expire_when is not None
            else None
        )
        if not in_scope:
            status = EffectiveRuleStatus.OUT_OF_SCOPE
            reason = scope_reason
        elif state.retired:
            status = EffectiveRuleStatus.RETIRED
            reason = state.retirement_reason or "Rule retired."
        elif not state.unlocked:
            status = EffectiveRuleStatus.LOCKED
            reason = unlock.explanation if unlock else "Unlock condition is pending."
        elif live is not None and not live.value:
            status = EffectiveRuleStatus.INACTIVE
            reason = live.explanation
        elif move is None:
            status = EffectiveRuleStatus.WAITING
            reason = action_reason
        elif can_select:
            status = EffectiveRuleStatus.SELECTED
            reason = f"First applicable rule in {section} order."
        else:
            status = EffectiveRuleStatus.APPLICABLE
            reason = "Applicable, but an earlier policy item wins."
        return PolicyItemResolution(
            item=item,
            section=section,
            status=status,
            lifecycle=state.lifecycle,
            move=move,
            move_san=san,
            legal=move is not None,
            selected=status is EffectiveRuleStatus.SELECTED,
            shadowed=status is EffectiveRuleStatus.APPLICABLE,
            in_scope=in_scope,
            reason=reason,
            unlock=unlock,
            live_condition=live,
            expiration=expiration,
            unlocked_at_ply=state.unlocked_at_ply,
            retired_at_ply=state.retired_at_ply,
            retirement_reason=state.retirement_reason,
        )

    def _scope(
        self,
        structure_ids: tuple[str, ...],
        evaluator: ConditionEvaluator,
    ) -> tuple[bool, str]:
        if not structure_ids:
            return True, "Global item."
        if self.selected_structure_id is not None:
            in_scope = self.selected_structure_id in structure_ids
            return (
                in_scope,
                (
                    f"Selected structure {self.selected_structure_id} is in scope."
                    if in_scope
                    else f"Selected structure {self.selected_structure_id} is not "
                    "in this item's scopes."
                ),
            )
        available_ids = {
            structure.id
            for structure in self.flow.structures
            if evaluator.evaluate(structure.available_when).value
        }
        matching = available_ids.intersection(structure_ids)
        return (
            bool(matching),
            (
                f"Available structure scope: {sorted(matching)[0]}."
                if matching
                else "None of this item's structure scopes are currently available."
            ),
        )

    def _resolve_structures(
        self, evaluator: ConditionEvaluator
    ) -> tuple[StructureResolution, ...]:
        resolutions: list[StructureResolution] = []
        for structure in self.flow.structures:
            available = evaluator.evaluate(structure.available_when)
            selected = evaluator.evaluate(structure.selected_when)
            if self.selected_structure_id is None:
                status = (
                    StructureStatus.AVAILABLE
                    if available.value
                    else StructureStatus.UNAVAILABLE
                )
                reason = (
                    available.explanation
                    if available.value
                    else f"Availability pending: {available.explanation}"
                )
            elif structure.id == self.selected_structure_id:
                status = StructureStatus.SELECTED
                reason = "This structure was selected permanently on this line."
            else:
                status = StructureStatus.REJECTED
                reason = f"Structure {self.selected_structure_id} was selected first."
            resolutions.append(
                StructureResolution(
                    structure=structure,
                    status=status,
                    available=available,
                    selected=selected,
                    selected_at_ply=(
                        self.selected_structure_at_ply
                        if structure.id == self.selected_structure_id
                        else None
                    ),
                    reason=reason,
                )
            )
        return tuple(resolutions)

    def commit_move(
        self,
        board_before: chess.Board,
        move: chess.Move,
        board_after: chess.Board,
        *,
        selected_rule_id: str | None = None,
        ply: int,
    ) -> None:
        moving_piece_id = self.tracker.piece_id_at(move.from_square)
        if moving_piece_id is None:
            raise ValueError(
                f"No tracked original piece is on "
                f"{chess.square_name(move.from_square)}."
            )
        self.tracker.apply_move(board_before, move, ply=ply)
        self.last_move = LastMove(moving_piece_id, chess.square_name(move.to_square))
        evaluator = self._evaluator(board_after)

        # Retirement is evaluated before unlocking and structure selection.
        for rule in self.move_rules:
            state = self.rule_states[rule.id]
            if state.retired:
                continue
            expiration = (
                evaluator.evaluate(rule.expire_when)
                if rule.expire_when is not None
                else None
            )
            if rule.id == selected_rule_id or (
                expiration is not None and expiration.value
            ):
                state.retired = True
                state.retired_at_ply = ply
                if rule.id == selected_rule_id:
                    state.retirement_reason = "Selected one-shot rule was executed."
                else:
                    assert expiration is not None
                    state.retirement_reason = expiration.explanation

        for rule in self.move_rules:
            state = self.rule_states[rule.id]
            if state.retired or state.unlocked or rule.unlock_when is None:
                continue
            result = evaluator.evaluate(rule.unlock_when)
            if result.value:
                state.unlocked = True
                state.unlocked_at_ply = ply

        if self.selected_structure_id is None:
            for structure in self.flow.structures:
                available = evaluator.evaluate(structure.available_when)
                selected = evaluator.evaluate(structure.selected_when)
                if available.value and selected.value:
                    self.selected_structure_id = structure.id
                    self.selected_structure_at_ply = ply
                    break

    @classmethod
    def replay(
        cls, flow: Flow, history_san: tuple[str, ...]
    ) -> tuple[PolicyRuntime, chess.Board]:
        runtime = cls(flow)
        board = _board_from_fen(flow.start_fen)
        controlled_sources = {
            DecisionSource.RESPONSE,
            DecisionSource.DEVELOPMENT,
            DecisionSource.CONTINUATION,
        }
        for ply, san in enumerate(history_san, start=1):
            before = board.copy(stack=False)
            move = board.parse_san(san)
            selected_rule_id: str | None = None
            if before.turn == _color(flow.side):
                decision = runtime.resolve(before)
                if decision.source in controlled_sources and decision.move == move:
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
