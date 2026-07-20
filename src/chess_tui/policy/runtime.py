"""History-sensitive scheduler for Opening Rule Engine v4."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import chess

from ..flow.models import (
    DevelopmentInstruction,
    InterruptRule,
    Rulebook,
)
from ..flow.position import normalized_position_key, replay_san
from .actions import ActionResolution, ActionResolver, ActionStatus
from .conditions import ConditionEvaluator
from .models import ConditionResult, LastMove
from .relations import PositionAnalyzer, PositionRelations
from .tracker import OriginalPieceTracker


class DecisionSource(str, Enum):
    INTERRUPT = "interrupt"
    DEVELOPMENT = "development"
    FRONTIER = "frontier"


class FrontierReason(str, Enum):
    DEVELOPMENT_COMPLETE = "development-complete"
    NO_AUTHORED_LEGAL_MOVE = "no-authored-legal-move"
    UNHANDLED_REQUIRED_RULE = "unhandled-required-rule"
    AMBIGUOUS_ACTION = "ambiguous-action"


class DevelopmentStatus(str, Enum):
    NOT_READY = "not-ready"
    WAITING_FOR_LEGALITY = "waiting-for-legality"
    AVAILABLE = "available"
    SELECTED = "selected"
    COMPLETED = "completed"
    CAPTURED = "captured"


class InterruptStatus(str, Enum):
    TRIGGER_FALSE = "trigger-false"
    NO_ACTION = "no-action"
    APPLICABLE = "applicable"
    SELECTED = "selected"
    COMPLETED = "completed"
    AMBIGUOUS = "ambiguous"
    REQUIRED_UNHANDLED = "required-unhandled"


@dataclass(frozen=True, slots=True)
class DevelopmentResolution:
    reference: str
    instruction: DevelopmentInstruction
    status: DevelopmentStatus
    prerequisites_complete: bool
    condition: ConditionResult | None
    move: chess.Move | None
    move_san: str | None
    reason: str


@dataclass(frozen=True, slots=True)
class InterruptResolution:
    reference: str
    rule: InterruptRule
    status: InterruptStatus
    exact_position: bool
    prerequisites_complete: bool
    trigger: ConditionResult | None
    attempts: tuple[ActionResolution, ...]
    move: chess.Move | None
    move_san: str | None
    reason: str


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    source: DecisionSource
    move: chess.Move | None
    move_san: str | None
    source_id: str | None
    why: str | None
    frontier_reason: FrontierReason | None
    development_resolutions: tuple[DevelopmentResolution, ...]
    interrupt_resolutions: tuple[InterruptResolution, ...]
    relations: PositionRelations
    trace: tuple[str, ...]

    @property
    def note(self) -> str | None:
        return self.why


class PolicyRuntime:
    def __init__(self, rulebook: Rulebook) -> None:
        self.rulebook = rulebook
        self.start_board = _board_from_fen(rulebook.start_fen)
        self.tracker = OriginalPieceTracker(self.start_board)
        self.last_move: LastMove | None = None
        self.history_san: tuple[str, ...] = ()
        self.completed_interrupts: set[str] = set()
        self.exact_positions: dict[str, tuple[str, ...]] = {}
        for reference in rulebook.interrupt_order:
            rule = rulebook.interrupt_by_ref[reference]
            if rule.after_san is None:
                continue
            board = replay_san(
                self.start_board.fen(en_passant="fen"),
                rule.after_san,
                context=f"Interrupt {reference!r}",
            )
            self.exact_positions.setdefault(normalized_position_key(board), ())
            self.exact_positions[normalized_position_key(board)] += (reference,)

    def resolve(self, board: chess.Board) -> PolicyDecision:
        if board.turn != _color(self.rulebook.side):
            raise ValueError(
                f"Rulebook controls {self.rulebook.side}, but it is the opponent's turn."
            )
        relations = PositionAnalyzer().analyze(board, self.tracker)
        trace: list[str] = []
        interrupt_results: list[InterruptResolution] = []
        development_results: list[DevelopmentResolution] = []
        selected_move: chess.Move | None = None
        selected_san: str | None = None
        selected_reference: str | None = None
        selected_why: str | None = None
        frontier: FrontierReason | None = None

        exact_refs = set(self.exact_positions.get(normalized_position_key(board), ()))
        ordered_refs = tuple(
            ref for ref in self.rulebook.interrupt_order if ref in exact_refs
        ) + tuple(ref for ref in self.rulebook.interrupt_order if ref not in exact_refs)
        exact_phase_complete = False
        for reference in ordered_refs:
            is_exact = reference in exact_refs
            if not is_exact and not exact_phase_complete:
                exact_phase_complete = True
            rule = self.rulebook.interrupt_by_ref[reference]
            can_select = selected_move is None and frontier is None
            result = self._resolve_interrupt(
                reference,
                rule,
                board,
                relations,
                is_exact=is_exact,
                can_select=can_select,
            )
            interrupt_results.append(result)
            trace.append(
                f"Interrupt {reference}: {result.status.value} — {result.reason}"
            )
            if result.status is InterruptStatus.SELECTED:
                selected_move = result.move
                selected_san = result.move_san
                selected_reference = reference
                selected_why = rule.why
            elif (
                result.status is InterruptStatus.AMBIGUOUS
                and can_select
                and (is_exact or rule.required)
            ):
                frontier = FrontierReason.AMBIGUOUS_ACTION
                selected_reference = reference
                selected_why = rule.why
            elif result.status is InterruptStatus.REQUIRED_UNHANDLED and can_select:
                frontier = FrontierReason.UNHANDLED_REQUIRED_RULE
                selected_reference = reference
                selected_why = rule.why

        if selected_move is None and frontier is None:
            for alias in self.rulebook.development_order:
                piece = self.rulebook.piece_by_alias[alias]
                instruction = piece.development
                assert instruction is not None
                result = self._resolve_development(
                    alias,
                    instruction,
                    board,
                    relations,
                    can_select=selected_move is None,
                )
                development_results.append(result)
                trace.append(
                    f"Development {alias}.develop: {result.status.value} — "
                    f"{result.reason}"
                )
                if result.status is DevelopmentStatus.SELECTED:
                    selected_move = result.move
                    selected_san = result.move_san
                    selected_reference = f"{alias}.develop"
                    selected_why = instruction.why

        if selected_move is not None:
            source = (
                DecisionSource.DEVELOPMENT
                if selected_reference and selected_reference.endswith(".develop")
                else DecisionSource.INTERRUPT
            )
            return PolicyDecision(
                source=source,
                move=selected_move,
                move_san=selected_san,
                source_id=selected_reference,
                why=selected_why,
                frontier_reason=None,
                development_resolutions=tuple(development_results),
                interrupt_resolutions=tuple(interrupt_results),
                relations=relations,
                trace=tuple(trace),
            )

        if frontier is None:
            frontier = (
                FrontierReason.DEVELOPMENT_COMPLETE
                if self._all_development_terminal()
                else FrontierReason.NO_AUTHORED_LEGAL_MOVE
            )
        trace.append(f"Frontier reached: {frontier.value}.")
        return PolicyDecision(
            source=DecisionSource.FRONTIER,
            move=None,
            move_san=None,
            source_id=selected_reference,
            why=selected_why,
            frontier_reason=frontier,
            development_resolutions=tuple(development_results),
            interrupt_resolutions=tuple(interrupt_results),
            relations=relations,
            trace=tuple(trace),
        )

    def _resolve_interrupt(
        self,
        reference: str,
        rule: InterruptRule,
        board: chess.Board,
        relations: PositionRelations,
        *,
        is_exact: bool,
        can_select: bool,
    ) -> InterruptResolution:
        if reference in self.completed_interrupts:
            return InterruptResolution(
                reference,
                rule,
                InterruptStatus.COMPLETED,
                is_exact,
                True,
                None,
                (),
                None,
                None,
                "One-shot interrupt already completed.",
            )
        prerequisites = all(self._instruction_complete(item) for item in rule.requires)
        if not prerequisites:
            return InterruptResolution(
                reference,
                rule,
                InterruptStatus.TRIGGER_FALSE,
                is_exact,
                False,
                None,
                (),
                None,
                None,
                "Prerequisites are incomplete.",
            )
        if rule.after_san is not None and not is_exact:
            return InterruptResolution(
                reference,
                rule,
                InterruptStatus.TRIGGER_FALSE,
                False,
                True,
                None,
                (),
                None,
                None,
                "Exact position does not match.",
            )
        evaluator = ConditionEvaluator(
            board,
            self.tracker,
            relations=relations,
            last_move=self.last_move,
            subject=rule.piece,
        )
        trigger = evaluator.evaluate(rule.when) if rule.when is not None else None
        if trigger is not None and not trigger.value:
            return InterruptResolution(
                reference,
                rule,
                InterruptStatus.TRIGGER_FALSE,
                is_exact,
                True,
                trigger,
                (),
                None,
                None,
                trigger.explanation,
            )
        attempt_results: list[ActionResolution] = []
        resolved: ActionResolution | None = None
        ambiguous = False
        resolver = ActionResolver()
        for attempt in rule.attempts:
            result = resolver.resolve(
                attempt,
                board=board,
                tracker=self.tracker,
                relations=relations,
                subject=rule.piece,
                trigger=trigger,
            )
            attempt_results.append(result)
            if result.status is ActionStatus.AMBIGUOUS:
                ambiguous = True
                break
            if result.status is ActionStatus.RESOLVED:
                resolved = result
                break
        if resolved is not None:
            status = (
                InterruptStatus.SELECTED if can_select else InterruptStatus.APPLICABLE
            )
            return InterruptResolution(
                reference,
                rule,
                status,
                is_exact,
                True,
                trigger,
                tuple(attempt_results),
                resolved.move,
                resolved.move_san,
                (
                    "First resolving action selected."
                    if can_select
                    else "Applicable, but an earlier instruction wins."
                ),
            )
        if ambiguous:
            return InterruptResolution(
                reference,
                rule,
                InterruptStatus.AMBIGUOUS,
                is_exact,
                True,
                trigger,
                tuple(attempt_results),
                None,
                None,
                attempt_results[-1].reason,
            )
        # A triggerless opportunity is applicable only through a resolving action.
        required_unhandled = rule.required and trigger is not None
        if is_exact:
            required_unhandled = True
        status = (
            InterruptStatus.REQUIRED_UNHANDLED
            if required_unhandled
            else InterruptStatus.NO_ACTION
        )
        return InterruptResolution(
            reference,
            rule,
            status,
            is_exact,
            True,
            trigger,
            tuple(attempt_results),
            None,
            None,
            (
                "Triggered required interrupt has no resolving action."
                if required_unhandled
                else "No ordered action resolves uniquely."
            ),
        )

    def _resolve_development(
        self,
        alias: str,
        instruction: DevelopmentInstruction,
        board: chess.Board,
        relations: PositionRelations,
        *,
        can_select: bool,
    ) -> DevelopmentResolution:
        runtime = self.tracker.get(instruction.piece.original_piece_id)
        if runtime.captured:
            return DevelopmentResolution(
                f"{alias}.develop",
                instruction,
                DevelopmentStatus.CAPTURED,
                False,
                None,
                None,
                None,
                (
                    f"{instruction.piece.label} was captured after developing."
                    if runtime.has_moved
                    else f"{instruction.piece.label} was captured undeveloped."
                ),
            )
        if runtime.has_moved:
            return DevelopmentResolution(
                f"{alias}.develop",
                instruction,
                DevelopmentStatus.COMPLETED,
                True,
                None,
                None,
                None,
                f"{instruction.piece.label} has moved.",
            )
        prerequisites = all(
            self._instruction_complete(item) for item in instruction.requires
        )
        if not prerequisites:
            return DevelopmentResolution(
                f"{alias}.develop",
                instruction,
                DevelopmentStatus.NOT_READY,
                False,
                None,
                None,
                None,
                "Prerequisites are incomplete.",
            )
        condition = None
        if instruction.when is not None:
            condition = ConditionEvaluator(
                board,
                self.tracker,
                relations=relations,
                last_move=self.last_move,
                subject=instruction.piece,
            ).evaluate(instruction.when)
            if not condition.value:
                return DevelopmentResolution(
                    f"{alias}.develop",
                    instruction,
                    DevelopmentStatus.NOT_READY,
                    True,
                    condition,
                    None,
                    None,
                    condition.explanation,
                )
        assert runtime.current_square is not None
        move = chess.Move(
            runtime.current_square, chess.parse_square(instruction.to_square)
        )
        if move not in board.legal_moves:
            return DevelopmentResolution(
                f"{alias}.develop",
                instruction,
                DevelopmentStatus.WAITING_FOR_LEGALITY,
                True,
                condition,
                None,
                None,
                f"{move.uci()} is not currently legal.",
            )
        status = (
            DevelopmentStatus.SELECTED if can_select else DevelopmentStatus.AVAILABLE
        )
        return DevelopmentResolution(
            f"{alias}.develop",
            instruction,
            status,
            True,
            condition,
            move,
            board.san(move),
            (
                "First legal instruction in development order."
                if can_select
                else "Available, but an earlier development instruction wins."
            ),
        )

    def _instruction_complete(self, reference: str) -> bool:
        instruction = self.rulebook.instruction(reference)
        if isinstance(instruction, InterruptRule):
            return reference in self.completed_interrupts
        runtime = self.tracker.get(instruction.piece.original_piece_id)
        return runtime.has_moved

    def _all_development_terminal(self) -> bool:
        for alias in self.rulebook.development_order:
            instruction = self.rulebook.piece_by_alias[alias].development
            assert instruction is not None
            runtime = self.tracker.get(instruction.piece.original_piece_id)
            if not runtime.has_moved and not runtime.captured:
                return False
        return True

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
                f"No tracked original piece is on {chess.square_name(move.from_square)}."
            )
        san = board_before.san(move)
        self.tracker.apply_move(board_before, move, ply=ply)
        self.last_move = LastMove(moving_piece_id, chess.square_name(move.to_square))
        self.history_san = (*self.history_san, san)
        if (
            selected_rule_id is not None
            and not selected_rule_id.endswith(".develop")
            and selected_rule_id in self.rulebook.interrupt_by_ref
        ):
            self.completed_interrupts.add(selected_rule_id)

    @classmethod
    def replay(
        cls, rulebook: Rulebook, history_san: tuple[str, ...]
    ) -> tuple[PolicyRuntime, chess.Board]:
        runtime = cls(rulebook)
        board = _board_from_fen(rulebook.start_fen)
        for ply, san in enumerate(history_san, start=1):
            before = board.copy(stack=False)
            move = board.parse_san(san)
            selected_rule_id: str | None = None
            if before.turn == _color(rulebook.side):
                decision = runtime.resolve(before)
                if decision.move == move:
                    selected_rule_id = decision.source_id
            board.push(move)
            runtime.commit_move(
                before, move, board, selected_rule_id=selected_rule_id, ply=ply
            )
        return runtime, board


def _board_from_fen(value: str) -> chess.Board:
    return chess.Board() if value == "startpos" else chess.Board(value)


def _color(value: str) -> chess.Color:
    return chess.WHITE if value == "white" else chess.BLACK
