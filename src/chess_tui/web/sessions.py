"""In-memory Development Mode sessions over the shared v2 Python core."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
import secrets
from typing import Literal

import chess

from ..engine import (
    ENGINE_PROTOTYPE_PROFILE,
    AnalysedMove,
    ChessEngineService,
    EngineError,
    build_white_move_assessment,
    quality_for_loss,
)
from ..flow import (
    AttemptResult,
    ExactOverride,
    FlowError,
    FlowStorageError,
    FlowStore,
    FlowWorkspace,
    PolicyMoveAttempt,
    PolicyRule,
    normalized_position_key,
)
from ..flow.position import replay_san
from ..policy import MoveAction, OriginalPieceId, condition_to_data, parse_condition
from ..policy.conditions import ConditionEvaluator
from ..policy.models import EffectiveRuleStatus
from ..policy.runtime import (
    DecisionSource,
    OverrideResolution,
    PolicyDecision,
    RuleResolution,
)
from .api_models import (
    ActivitySnapshot,
    AttemptSnapshot,
    ConditionSnapshot,
    DecisionSnapshot,
    EngineHealth,
    EngineReviewSnapshot,
    EvaluationSnapshot,
    FlowSnapshot,
    FlowSourceResponse,
    GameOverSnapshot,
    NavigationSnapshot,
    OverrideRuntimeSnapshot,
    PositionSnapshot,
    RuleGroupsSnapshot,
    RuleRuntimeSnapshot,
    UpdateOverrideRequest,
    UpdateRuleRequest,
    WorkspaceSnapshot,
)
from .errors import ApiErrorCode, WebApiError


@dataclass(slots=True)
class DevelopmentSession:
    id: str
    flow_path: Path
    workspace: FlowWorkspace
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    activity: list[ActivitySnapshot] = field(default_factory=list)
    next_activity_id: int = 1


class EvaluationCache:
    def __init__(
        self,
        engine: ChessEngineService | None,
        *,
        engine_identity: str = "engine-off",
        profile_id: str = "web-analysis-0.1s",
    ) -> None:
        self.engine = engine
        self.engine_identity = engine_identity
        self.profile_id = profile_id
        self._cache: dict[tuple[str, str, str], AnalysedMove] = {}
        self._lock = asyncio.Lock()
        self._status = "off" if engine is None else "configured"
        self.last_error: str | None = None

    @property
    def health(self) -> EngineHealth:
        return EngineHealth(status=self._status)  # type: ignore[arg-type]

    async def analyse(self, board: chess.Board) -> AnalysedMove:
        if self.engine is None:
            raise RuntimeError("Engine analysis is disabled.")
        key = (normalized_position_key(board), self.profile_id, self.engine_identity)
        async with self._lock:
            if key in self._cache:
                return self._cache[key]
            try:
                lines = await self.engine.analyse(board, count=1)
                if not lines:
                    raise RuntimeError("Engine returned no analysis rows.")
            except EngineError as error:
                self._status = "error"
                self.last_error = str(error)
                raise
            self._cache[key] = lines[0]
            self._status = "ready"
            self.last_error = None
            return lines[0]


class SessionManager:
    def __init__(
        self,
        *,
        project_root: Path,
        allowed_flow_directory: Path,
        startup_flow_path: Path | None,
        engine: ChessEngineService | None,
        engine_identity: str,
    ) -> None:
        self.project_root = project_root.resolve()
        self.allowed_flow_directory = allowed_flow_directory.resolve()
        self.startup_flow_path = (
            startup_flow_path.resolve() if startup_flow_path else None
        )
        self.evaluations = EvaluationCache(engine, engine_identity=engine_identity)
        self.sessions: dict[str, DevelopmentSession] = {}

    async def create_session(
        self, requested_flow_path: str | None
    ) -> WorkspaceSnapshot:
        path = self._resolve_flow_path(requested_flow_path)
        workspace = FlowWorkspace(path)
        workspace.restart()
        session = DevelopmentSession(secrets.token_urlsafe(18), path, workspace)
        side = workspace.author.flow.side.capitalize()
        self._append_activity(
            session,
            "info",
            "Development session ready",
            f"Loaded {workspace.author.flow.name}. {side} follows the deterministic policy.",
        )
        self.sessions[session.id] = session
        async with session.lock:
            return await self._snapshot(session)

    async def get_snapshot(self, session_id: str) -> WorkspaceSnapshot:
        session = self._session(session_id)
        async with session.lock:
            return await self._snapshot(session)

    async def get_flow_source(self, session_id: str) -> FlowSourceResponse:
        session = self._session(session_id)
        async with session.lock:
            try:
                content = session.flow_path.read_text(encoding="utf-8")
            except (OSError, UnicodeError) as error:
                raise FlowStorageError(
                    f"Could not read flow {session.flow_path}: {error}"
                ) from error
            return FlowSourceResponse(
                path=self._display_path(session.flow_path), content=content
            )

    async def submit_move(self, session_id: str, uci: str) -> WorkspaceSnapshot:
        session = self._session(session_id)
        async with session.lock:
            move = self._legal_move(session.workspace.board, uci)
            await self._submit_legal_move(session, move, typed=False)
            return await self._snapshot(session)

    async def submit_san_move(self, session_id: str, san: str) -> WorkspaceSnapshot:
        session = self._session(session_id)
        async with session.lock:
            try:
                move = session.workspace.board.parse_san(san.strip())
            except ValueError as error:
                raise WebApiError(
                    ApiErrorCode.INVALID_MOVE,
                    f"{san.strip()!r} is not legal SAN in the current position.",
                ) from error
            await self._submit_legal_move(session, move, typed=True)
            return await self._snapshot(session)

    async def retry_policy(self, session_id: str) -> WorkspaceSnapshot:
        session = self._session(session_id)
        async with session.lock:
            if session.workspace.attempt is None:
                raise WebApiError(
                    ApiErrorCode.INVALID_REQUEST,
                    "No policy result is available to retry.",
                )
            side = session.workspace.author.flow.side.capitalize()
            session.workspace.retry_policy_move()
            self._append_activity(
                session,
                "info",
                f"Retry {side}'s move",
                "The position was restored. Try again or ask for a hint.",
            )
            return await self._snapshot(session)

    async def continue_policy(self, session_id: str) -> WorkspaceSnapshot:
        session = self._session(session_id)
        async with session.lock:
            attempt = session.workspace.attempt
            if attempt is None or attempt.result is not AttemptResult.MISMATCH:
                raise WebApiError(
                    ApiErrorCode.INVALID_REQUEST,
                    "Only a mismatching policy move can continue with the selected rule.",
                )
            expected = attempt.decision.move_san or "the selected move"
            session.workspace.continue_with_policy_move()
            self._append_activity(
                session,
                "success",
                f"Continued with {expected}",
                attempt.decision.note or "The selected policy rule was kept unchanged.",
            )
            return await self._snapshot(session)

    async def play_next_opponent(self, session_id: str) -> WorkspaceSnapshot:
        session = self._session(session_id)
        async with session.lock:
            workspace = session.workspace
            if (
                workspace.attempt is not None
                or workspace.outcome is not None
                or workspace.is_policy_turn
            ):
                raise WebApiError(
                    ApiErrorCode.INVALID_REQUEST,
                    "Next is only available while the opponent is ready to move.",
                )
            engine = self.evaluations.engine
            if engine is None:
                raise WebApiError(
                    ApiErrorCode.ENGINE_ERROR,
                    "The opponent's next move requires a configured chess engine.",
                    status_code=503,
                )
            try:
                move = await engine.choose_move(
                    workspace.board.copy(stack=False), ENGINE_PROTOTYPE_PROFILE
                )
            except EngineError as error:
                raise WebApiError(
                    ApiErrorCode.ENGINE_ERROR,
                    f"The chess engine could not choose the opponent move: {error}",
                    status_code=502,
                ) from error
            if move not in workspace.board.legal_moves:
                raise WebApiError(
                    ApiErrorCode.ENGINE_ERROR,
                    "The chess engine returned an illegal opponent move.",
                    status_code=502,
                )
            san = workspace.board.san(move)
            color = "White" if workspace.board.turn == chess.WHITE else "Black"
            workspace.submit_opponent_uci(move.uci())
            self._append_activity(
                session,
                "move",
                f"{color} played {san}",
                "The engine selected this reply after you chose Next.",
            )
            if workspace.outcome is None:
                workspace.begin_policy_turn()
            return await self._snapshot(session)

    async def update_rule(
        self, session_id: str, rule_id: str, payload: UpdateRuleRequest
    ) -> WorkspaceSnapshot:
        session = self._session(session_id)
        async with session.lock:
            workspace = session.workspace
            if all(rule.id != rule_id for rule in workspace.author.flow.rules):
                raise WebApiError(
                    ApiErrorCode.INVALID_REQUEST, f"Unknown rule id {rule_id!r}."
                )
            try:
                replacement = PolicyRule(
                    id=rule_id,
                    priority=payload.priority,
                    enabled=payload.enabled,
                    note=_clean_note(payload.note),
                    move=MoveAction(
                        OriginalPieceId.parse(payload.move.piece), payload.move.to
                    ),
                    activate_when=(
                        parse_condition(payload.activate_when, context="activateWhen")
                        if payload.activate_when is not None
                        else None
                    ),
                    retire_when=(
                        parse_condition(payload.retire_when, context="retireWhen")
                        if payload.retire_when is not None
                        else None
                    ),
                )
                workspace.update_rule(replacement)
            except (TypeError, ValueError, FlowError) as error:
                if isinstance(error, FlowError):
                    raise
                raise WebApiError(
                    ApiErrorCode.FLOW_VALIDATION_ERROR, str(error), status_code=422
                ) from error
            self._append_activity(
                session,
                "info",
                f"Updated rule {rule_id}",
                "The complete flow was validated, saved atomically, and replayed.",
            )
            return await self._snapshot(session)

    async def update_override(
        self, session_id: str, override_id: str, payload: UpdateOverrideRequest
    ) -> WorkspaceSnapshot:
        session = self._session(session_id)
        async with session.lock:
            workspace = session.workspace
            if all(item.id != override_id for item in workspace.author.flow.overrides):
                raise WebApiError(
                    ApiErrorCode.INVALID_REQUEST,
                    f"Unknown override id {override_id!r}.",
                )
            try:
                replacement = ExactOverride(
                    id=override_id,
                    after_san=tuple(payload.after_san),
                    enabled=payload.enabled,
                    note=_clean_note(payload.note),
                    move=MoveAction(
                        OriginalPieceId.parse(payload.move.piece), payload.move.to
                    ),
                )
                workspace.update_override(replacement)
            except (TypeError, ValueError, FlowError) as error:
                if isinstance(error, FlowError):
                    raise
                raise WebApiError(
                    ApiErrorCode.FLOW_VALIDATION_ERROR, str(error), status_code=422
                ) from error
            self._append_activity(
                session,
                "info",
                f"Updated override {override_id}",
                "The exact position, action, and flow replay all validated.",
            )
            return await self._snapshot(session)

    async def go_back(self, session_id: str) -> WorkspaceSnapshot:
        session = self._session(session_id)
        async with session.lock:
            if not session.workspace.can_go_back:
                raise WebApiError(
                    ApiErrorCode.INVALID_NAVIGATION,
                    "There is no earlier policy decision.",
                )
            session.workspace.go_back_to_previous_decision()
            self._append_activity(
                session,
                "info",
                "Moved back",
                "Replayed the retained line and restored policy lifecycle state.",
            )
            return await self._snapshot(session)

    async def restart(self, session_id: str) -> WorkspaceSnapshot:
        session = self._session(session_id)
        async with session.lock:
            session.workspace.restart()
            session.activity.clear()
            session.next_activity_id = 1
            self._append_activity(
                session,
                "info",
                "Line restarted",
                "Returned to the beginning without changing saved rules or branches.",
            )
            return await self._snapshot(session)

    async def _submit_legal_move(
        self, session: DevelopmentSession, move: chess.Move, *, typed: bool
    ) -> None:
        workspace = session.workspace
        if workspace.attempt is not None:
            raise WebApiError(
                ApiErrorCode.INVALID_REQUEST,
                "Resolve the current policy result before playing another move.",
            )
        san = workspace.board.san(move)
        color = "White" if workspace.board.turn == chess.WHITE else "Black"
        if workspace.is_policy_turn:
            attempt = workspace.submit_policy_uci(move.uci())
            self._record_policy_attempt(session, attempt)
            if attempt.result is AttemptResult.CORRECT:
                workspace.complete_correct_move()
        else:
            workspace.submit_opponent_uci(move.uci())
            reason = (
                "This reply was entered in the move composer."
                if typed
                else "This is the selected opponent reply for the current line."
            )
            self._append_activity(session, "move", f"{color} played {san}", reason)
            if workspace.outcome is None:
                workspace.begin_policy_turn()

    def _record_policy_attempt(
        self, session: DevelopmentSession, attempt: PolicyMoveAttempt
    ) -> None:
        color = "White" if attempt.selected_move.color == chess.WHITE else "Black"
        decision = attempt.decision
        if attempt.result is AttemptResult.CORRECT:
            kind = "success"
            message = f"Correct. {decision.note or f'This matches {decision.source.value} {decision.source_id}.' }"
        elif attempt.result is AttemptResult.MISMATCH:
            kind = "warning"
            message = f"Incorrect for this policy. Expected {decision.move_san}. {decision.note or ''} Retry, use the selected move, or edit the rule."
        else:
            kind = "warning"
            message = "The policy is at a frontier. Edit the TOML or an existing rule, then retry."
        self._append_activity(
            session,
            kind,
            f"{color} played {attempt.selected_move.san}",
            message.strip(),
        )

    async def _snapshot(self, session: DevelopmentSession) -> WorkspaceSnapshot:
        workspace = session.workspace
        phase = _phase(workspace)
        decision = _current_decision(workspace, phase)
        attempt = await self._attempt(workspace)
        evaluation, evaluation_error = await self._evaluation(workspace)
        errors = []
        if evaluation_error:
            from .api_models import ApiErrorItem

            errors.append(
                ApiErrorItem(code=ApiErrorCode.ENGINE_ERROR, message=evaluation_error)
            )
        visible_history = list(workspace.history)
        if workspace.attempt is not None:
            visible_history.append(workspace.attempt.selected_move.san)
        return WorkspaceSnapshot(
            session_id=session.id,
            phase=phase,  # type: ignore[arg-type]
            flow=FlowSnapshot(
                name=workspace.author.flow.name,
                version=workspace.author.flow.version,
                path=self._display_path(session.flow_path),
                side=workspace.author.flow.side,
            ),
            position=PositionSnapshot(
                fen=workspace.board.fen(en_passant="fen"),
                history_san=visible_history,
                turn="white" if workspace.board.turn == chess.WHITE else "black",
                ply=len(visible_history),
                last_move_uci=(
                    workspace.controller.interaction.last_move.uci
                    if workspace.controller.interaction.last_move
                    else None
                ),
                legal_moves_uci=(
                    [move.uci() for move in workspace.board.legal_moves]
                    if workspace.attempt is None
                    else []
                ),
                game_over=_game_over(workspace.outcome),
            ),
            decision=_decision_snapshot(decision),
            attempt=attempt,
            rules=_rule_groups(workspace, decision),
            evaluation=evaluation,
            navigation=NavigationSnapshot(
                can_back=workspace.can_go_back, can_restart=workspace.can_restart
            ),
            activity=list(session.activity),
            errors=errors,
        )

    async def _evaluation(
        self, workspace: FlowWorkspace
    ) -> tuple[EvaluationSnapshot, str | None]:
        if self.evaluations.engine is None:
            return EvaluationSnapshot(status="engine-off"), None
        outcome = workspace.outcome
        try:
            if outcome is not None:
                current = _terminal_analysis(outcome)
            else:
                current = await self.evaluations.analyse(workspace.board)
            previous_board: chess.Board | None = None
            if workspace.attempt is not None:
                previous_board = workspace.attempt.board_before
            elif workspace.history:
                previous_board = replay_san(
                    workspace.author.flow.start_fen, tuple(workspace.history[:-1])
                )
            previous = (
                await self.evaluations.analyse(previous_board)
                if previous_board is not None
                else None
            )
        except (EngineError, RuntimeError) as error:
            return EvaluationSnapshot(status="error", error_message=str(error)), str(
                error
            )
        change = (
            current.evaluation_cp - previous.evaluation_cp
            if current.evaluation_cp is not None
            and previous is not None
            and previous.evaluation_cp is not None
            else None
        )
        return (
            EvaluationSnapshot(
                status="game-over" if outcome is not None else "ready",
                centipawns=current.evaluation_cp,
                mate_in=current.mate_in,
                previous_centipawns=previous.evaluation_cp if previous else None,
                previous_mate_in=previous.mate_in if previous else None,
                change_centipawns=change,
            ),
            None,
        )

    async def _attempt(self, workspace: FlowWorkspace) -> AttemptSnapshot | None:
        attempt = workspace.attempt
        if attempt is None:
            return None
        review = (
            await self._engine_review(workspace)
            if attempt.result is AttemptResult.MISMATCH
            else None
        )
        decision = attempt.decision
        return AttemptSnapshot(
            result=attempt.result.value,  # type: ignore[arg-type]
            played_uci=attempt.selected_move.move.uci,
            played_san=attempt.selected_move.san,
            expected_uci=decision.move.uci() if decision.move else None,
            expected_san=decision.move_san,
            source=decision.source.value,  # type: ignore[arg-type]
            source_id=decision.source_id,
            note=decision.note,
            trace=list(decision.trace),
            engine_review=review,
        )

    async def _engine_review(self, workspace: FlowWorkspace) -> EngineReviewSnapshot:
        if self.evaluations.engine is None:
            return EngineReviewSnapshot(status="engine-off")
        attempt = workspace.attempt
        assert attempt is not None
        try:
            before = await self.evaluations.analyse(attempt.board_before)
            after = (
                _terminal_analysis(workspace.outcome)
                if workspace.outcome
                else await self.evaluations.analyse(workspace.board)
            )
            move = chess.Move.from_uci(attempt.selected_move.move.uci)
            if attempt.selected_move.color == chess.WHITE:
                assessment = build_white_move_assessment(
                    attempt.board_before, move, before, after
                )
                quality = assessment.quality.value
                loss = assessment.loss_cp
            elif before.evaluation_cp is not None and after.evaluation_cp is not None:
                loss = max(0, after.evaluation_cp - before.evaluation_cp)
                quality = quality_for_loss(loss).value
            else:
                loss = None
                quality = (
                    "blunder"
                    if after.mate_in is not None and after.mate_in > 0
                    else "good"
                )
        except (EngineError, RuntimeError) as error:
            return EngineReviewSnapshot(status="error", error_message=str(error))
        return EngineReviewSnapshot(
            status="ready",
            quality=quality,
            loss_cp=loss,
            best_move_uci=before.uci,
            best_move_san=before.san,
            evaluation_before_cp=before.evaluation_cp,
            evaluation_after_cp=after.evaluation_cp,
            mate_before=before.mate_in,
            mate_after=after.mate_in,
        )

    @staticmethod
    def _append_activity(
        session: DevelopmentSession,
        kind: Literal["info", "move", "success", "warning"],
        title: str,
        message: str,
    ) -> None:
        session.activity.append(
            ActivitySnapshot(
                id=session.next_activity_id, kind=kind, title=title, message=message
            )
        )
        session.next_activity_id += 1
        if len(session.activity) > 100:
            del session.activity[:-100]

    def _session(self, session_id: str) -> DevelopmentSession:
        try:
            return self.sessions[session_id]
        except KeyError as error:
            raise WebApiError(
                ApiErrorCode.SESSION_NOT_FOUND,
                "Development session was not found.",
                status_code=404,
            ) from error

    def _resolve_flow_path(self, requested: str | None) -> Path:
        if requested is None:
            candidate = self.startup_flow_path or self._most_recent_flow()
        else:
            raw = Path(requested).expanduser()
            candidate = (
                raw if raw.is_absolute() else self.project_root / raw
            ).resolve()
        allowed = _is_relative_to(candidate, self.allowed_flow_directory)
        configured = (
            self.startup_flow_path is not None and candidate == self.startup_flow_path
        )
        if not allowed and not configured:
            raise WebApiError(
                ApiErrorCode.INVALID_REQUEST,
                "Requested flow is outside the allowed flow directory.",
            )
        try:
            FlowStore().load(candidate)
        except FlowError as error:
            raise WebApiError(
                ApiErrorCode.FLOW_VALIDATION_ERROR, str(error), status_code=422
            ) from error
        return candidate

    def _most_recent_flow(self) -> Path:
        candidates = tuple(self.allowed_flow_directory.glob("*.toml"))
        if not candidates:
            raise WebApiError(
                ApiErrorCode.FLOW_VALIDATION_ERROR,
                "No flow TOML files are available.",
                status_code=422,
            )
        return max(candidates, key=lambda path: path.stat().st_mtime).resolve()

    @staticmethod
    def _legal_move(board: chess.Board, uci: str) -> chess.Move:
        try:
            move = chess.Move.from_uci(uci)
        except ValueError as error:
            raise WebApiError(
                ApiErrorCode.INVALID_MOVE, f"{uci!r} is not valid UCI."
            ) from error
        if move not in board.legal_moves:
            raise WebApiError(
                ApiErrorCode.INVALID_MOVE,
                f"{uci!r} is not legal in the current position.",
            )
        return move

    def _display_path(self, path: Path) -> str:
        try:
            return path.relative_to(self.project_root).as_posix()
        except ValueError:
            return path.name


def _phase(workspace: FlowWorkspace) -> str:
    if workspace.outcome is not None:
        return "game-over"
    if workspace.attempt is not None:
        return "policy-result"
    return "policy-ready" if workspace.is_policy_turn else "opponent-ready"


def _current_decision(workspace: FlowWorkspace, phase: str) -> PolicyDecision | None:
    if workspace.attempt is not None:
        return workspace.attempt.decision
    if phase != "policy-ready":
        return None
    if workspace.policy_turn is None:
        workspace.begin_policy_turn()
    assert workspace.policy_turn is not None
    return workspace.policy_turn.decision


def _decision_snapshot(decision: PolicyDecision | None) -> DecisionSnapshot | None:
    if decision is None:
        return None
    return DecisionSnapshot(
        status="frontier" if decision.source is DecisionSource.FRONTIER else "ready",
        move_uci=decision.move.uci() if decision.move else None,
        move_san=decision.move_san,
        source=decision.source.value,  # type: ignore[arg-type]
        source_id=decision.source_id,
        priority=decision.priority,
        note=decision.note,
        trace=list(decision.trace),
    )


def _rule_groups(
    workspace: FlowWorkspace, decision: PolicyDecision | None
) -> RuleGroupsSnapshot:
    if decision is not None:
        rules = [_rule_snapshot(item) for item in decision.rule_resolutions]
        overrides = [_override_snapshot(item) for item in decision.override_resolutions]
    else:
        rules = _passive_rule_snapshots(workspace)
        overrides = [
            OverrideRuntimeSnapshot(
                id=item.id,
                enabled=item.enabled,
                after_san=list(item.after_san),
                piece=str(item.move.piece),
                destination=item.move.to_square,
                move_uci=None,
                move_san=None,
                matched=False,
                legal=False,
                selected=False,
                note=item.note,
                reason="Exact overrides are evaluated on the controlled side's turn.",
            )
            for item in workspace.author.flow.overrides
        ]
    selected_rule = next((item for item in rules if item.selected), None)
    selected_override = next((item for item in overrides if item.selected), None)
    return RuleGroupsSnapshot(
        selected=selected_override or selected_rule,
        applies_now=[item for item in rules if item.status == "active"],
        waiting=[item for item in rules if item.status == "waiting"],
        dormant=[item for item in rules if item.status == "dormant"],
        retired=[item for item in rules if item.status == "retired"],
        disabled=[item for item in rules if item.status == "disabled"],
        overrides=overrides,
    )


def _rule_snapshot(item: RuleResolution) -> RuleRuntimeSnapshot:
    return RuleRuntimeSnapshot(
        id=item.rule.id,
        priority=item.rule.priority,
        enabled=item.rule.enabled,
        piece=str(item.rule.move.piece),
        destination=item.rule.move.to_square,
        move_uci=item.move.uci() if item.move else None,
        move_san=item.move_san,
        legal=item.legal,
        lifecycle=item.lifecycle.value,
        status=item.status.value,
        selected=item.selected,
        shadowed=item.shadowed,
        note=item.rule.note,
        activate_when=_condition_snapshot(item.rule.activate_when, item.activation),
        retire_when=_condition_snapshot(item.rule.retire_when, item.retirement),
        activated_at_ply=item.activated_at_ply,
        retired_at_ply=item.retired_at_ply,
        reason=item.reason,
    )


def _override_snapshot(item: OverrideResolution) -> OverrideRuntimeSnapshot:
    return OverrideRuntimeSnapshot(
        id=item.override.id,
        enabled=item.override.enabled,
        after_san=list(item.override.after_san),
        piece=str(item.override.move.piece),
        destination=item.override.move.to_square,
        move_uci=item.move.uci() if item.move else None,
        move_san=item.move_san,
        matched=item.matched,
        legal=item.legal,
        selected=item.selected,
        note=item.override.note,
        reason=item.reason,
    )


def _passive_rule_snapshots(workspace: FlowWorkspace) -> list[RuleRuntimeSnapshot]:
    evaluator = ConditionEvaluator(
        workspace.board, workspace.runtime.tracker, workspace.runtime.states
    )
    snapshots: list[RuleRuntimeSnapshot] = []
    for rule in sorted(
        workspace.author.flow.rules, key=lambda item: item.priority, reverse=True
    ):
        state = workspace.runtime.rule_states[rule.id]
        if not rule.enabled:
            status = EffectiveRuleStatus.DISABLED
            reason = "Rule is disabled."
        elif state.lifecycle.value == "retired":
            status = EffectiveRuleStatus.RETIRED
            reason = state.retirement_reason or "Rule retired."
        elif state.lifecycle.value == "dormant":
            status = EffectiveRuleStatus.DORMANT
            reason = "Activation is pending."
        else:
            status = EffectiveRuleStatus.ACTIVE
            reason = "Active; legality will be checked on the controlled side's turn."
        activation = (
            evaluator.evaluate(rule.activate_when) if rule.activate_when else None
        )
        retirement = evaluator.evaluate(rule.retire_when) if rule.retire_when else None
        snapshots.append(
            RuleRuntimeSnapshot(
                id=rule.id,
                priority=rule.priority,
                enabled=rule.enabled,
                piece=str(rule.move.piece),
                destination=rule.move.to_square,
                move_uci=None,
                move_san=None,
                legal=False,
                lifecycle=state.lifecycle.value,
                status=status.value,
                selected=False,
                shadowed=False,
                note=rule.note,
                activate_when=_condition_snapshot(rule.activate_when, activation),
                retire_when=_condition_snapshot(rule.retire_when, retirement),
                activated_at_ply=state.activated_at_ply,
                retired_at_ply=state.retired_at_ply,
                reason=reason,
            )
        )
    return snapshots


def _condition_snapshot(condition, result) -> ConditionSnapshot | None:
    if condition is None or result is None:
        return None
    return ConditionSnapshot(
        expression=condition_to_data(condition),
        value=result.value,
        explanation=result.explanation,
    )


def _game_over(outcome: chess.Outcome | None) -> GameOverSnapshot | None:
    if outcome is None:
        return None
    winner = (
        None
        if outcome.winner is None
        else ("white" if outcome.winner == chess.WHITE else "black")
    )
    return GameOverSnapshot(result=outcome.result(), termination=outcome.termination.name.lower().replace("_", "-"), winner=winner)  # type: ignore[arg-type]


def _terminal_analysis(outcome: chess.Outcome) -> AnalysedMove:
    if outcome.termination is chess.Termination.CHECKMATE:
        return AnalysedMove(
            "", "", None, (), mate_in=0 if outcome.winner is chess.WHITE else -1
        )
    return AnalysedMove("", "", 0, ())


def _clean_note(note: str | None) -> str | None:
    return note.strip() if note and note.strip() else None


def _is_relative_to(path: Path, directory: Path) -> bool:
    try:
        path.relative_to(directory)
        return True
    except ValueError:
        return False
