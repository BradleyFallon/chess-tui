"""In-memory Development Mode sessions over the shared v4 Python core."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
import secrets

import chess

from ..engine import (
    ANALYSIS_PROFILES,
    DEFAULT_ANALYSIS_PROFILE,
    ChessEngineService,
    EngineError,
)
from ..flow import (
    CaptureAttempt,
    DevelopmentInstruction,
    FlowValidationError,
    FlowWorkspace,
    InterruptRule,
    MoveAttempt,
)
from ..policy import PositionAnalyzer, StartingPieceRef, condition_to_data, parse_condition
from ..policy.runtime import (
    DecisionSource,
    PolicyDecision,
    PolicyRuntime,
)
from .api_models import (
    ActionAttemptRequest,
    ActionAttemptSnapshot,
    AnalysisRunSnapshot,
    AttackSnapshot,
    AttemptSnapshot,
    ConditionEvaluationSnapshot,
    DecisionSnapshot,
    DefenseSnapshot,
    DefendersAgainstSnapshot,
    DevelopmentDraftRequest,
    DevelopmentInstructionSnapshot,
    EngineHealth,
    EvaluationSnapshot,
    FlowSourceResponse,
    FrontierSnapshot,
    InterruptDraftRequest,
    InterruptRuleSnapshot,
    MutationPreviewResponse,
    NavigationSnapshot,
    OpeningTagSnapshot,
    PieceRelationSnapshot,
    PieceScriptSnapshot,
    PositionSnapshot,
    RulebookSnapshot,
    WorkspaceSnapshot,
)
from .errors import ApiErrorCode, WebApiError


@dataclass(slots=True)
class DevelopmentSession:
    id: str
    flow_path: Path
    workspace: FlowWorkspace
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    analysis_profile_id: str = DEFAULT_ANALYSIS_PROFILE.id
    evaluation: EvaluationSnapshot = field(default_factory=EvaluationSnapshot)


class EvaluationService:
    def __init__(self, engine: ChessEngineService | None) -> None:
        self.engine = engine
        self.status = "off" if engine is None else "configured"
        self._lock = asyncio.Lock()

    @property
    def health(self) -> EngineHealth:
        return EngineHealth(status=self.status)  # type: ignore[arg-type]

    async def analyse(
        self, board: chess.Board, profile_id: str
    ) -> AnalysisRunSnapshot:
        if self.engine is None:
            return AnalysisRunSnapshot(status="off", message="Engine is not configured.")
        profile = next(item for item in ANALYSIS_PROFILES if item.id == profile_id)
        async with self._lock:
            try:
                result = (await self.engine.analyse(board, count=1, profile=profile))[0]
            except EngineError as exc:
                self.status = "error"
                return AnalysisRunSnapshot(status="error", message=str(exc))
        self.status = "ready"
        return AnalysisRunSnapshot(
            status="ready",
            centipawns=result.evaluation_cp,
            mate_in=result.mate_in,
            move_uci=result.uci,
            move_san=result.san,
        )


class SessionManager:
    def __init__(
        self,
        *,
        project_root: Path,
        allowed_flow_directory: Path,
        startup_flow_path: Path | None,
        engine: ChessEngineService | None,
        engine_identity: str = "",
    ) -> None:
        del engine_identity
        self.project_root = project_root.resolve()
        self.allowed_flow_directory = allowed_flow_directory.resolve()
        self.startup_flow_path = (
            startup_flow_path.resolve() if startup_flow_path else None
        )
        self.evaluations = EvaluationService(engine)
        self.sessions: dict[str, DevelopmentSession] = {}

    async def create_session(self, requested_flow_path: str | None) -> WorkspaceSnapshot:
        path = self._resolve_flow_path(requested_flow_path)
        workspace = FlowWorkspace(path)
        workspace.restart()
        session = DevelopmentSession(secrets.token_urlsafe(12), path, workspace)
        self.sessions[session.id] = session
        return self._snapshot(session)

    async def get_snapshot(self, session_id: str) -> WorkspaceSnapshot:
        session = self._session(session_id)
        async with session.lock:
            return self._snapshot(session)

    async def get_flow_source(self, session_id: str) -> FlowSourceResponse:
        session = self._session(session_id)
        return FlowSourceResponse(
            path=self._display_path(session.flow_path),
            source=session.flow_path.read_text(encoding="utf-8"),
        )

    async def submit_move(self, session_id: str, uci: str) -> WorkspaceSnapshot:
        session = self._session(session_id)
        async with session.lock:
            workspace = session.workspace
            try:
                if workspace.is_policy_turn:
                    attempt = workspace.submit_policy_uci(uci)
                    if attempt.result.value == "correct":
                        workspace.complete_correct_move()
                else:
                    workspace.submit_opponent_uci(uci)
                    if workspace.outcome is None:
                        workspace.begin_policy_turn()
            except (ValueError, FlowValidationError) as exc:
                raise WebApiError(
                    ApiErrorCode.INVALID_MOVE, str(exc), status_code=422
                ) from exc
            return self._snapshot(session)

    async def submit_san_move(self, session_id: str, san: str) -> WorkspaceSnapshot:
        session = self._session(session_id)
        workspace = session.workspace
        board = workspace.board
        try:
            uci = board.parse_san(san).uci()
        except ValueError as exc:
            raise WebApiError(
                ApiErrorCode.INVALID_MOVE, str(exc), status_code=422
            ) from exc
        return await self.submit_move(session_id, uci)

    async def retry_policy(self, session_id: str) -> WorkspaceSnapshot:
        session = self._session(session_id)
        async with session.lock:
            session.workspace.retry_policy_move()
            return self._snapshot(session)

    async def continue_policy(self, session_id: str) -> WorkspaceSnapshot:
        session = self._session(session_id)
        async with session.lock:
            session.workspace.continue_with_policy_move()
            return self._snapshot(session)

    async def accept_attempt_as_interrupt(self, session_id: str) -> WorkspaceSnapshot:
        session = self._session(session_id)
        async with session.lock:
            session.workspace.accept_attempt_as_interrupt()
            return self._snapshot(session)

    async def go_back(self, session_id: str) -> WorkspaceSnapshot:
        session = self._session(session_id)
        async with session.lock:
            try:
                session.workspace.go_back_to_previous_decision()
            except FlowValidationError as exc:
                raise WebApiError(
                    ApiErrorCode.INVALID_NAVIGATION, str(exc), status_code=409
                ) from exc
            return self._snapshot(session)

    async def restart(self, session_id: str) -> WorkspaceSnapshot:
        session = self._session(session_id)
        async with session.lock:
            session.workspace.restart()
            return self._snapshot(session)

    async def reload(self, session_id: str) -> WorkspaceSnapshot:
        session = self._session(session_id)
        async with session.lock:
            session.workspace.reload()
            return self._snapshot(session)

    async def analyse_position(self, session_id: str) -> WorkspaceSnapshot:
        session = self._session(session_id)
        async with session.lock:
            result = await self.evaluations.analyse(
                session.workspace.board, session.analysis_profile_id
            )
            session.evaluation = EvaluationSnapshot(
                status=result.status,
                centipawns=result.centipawns,
                mate_in=result.mate_in,
                message=result.message,
            )
            return self._snapshot(session)

    async def update_analysis_profile(
        self, session_id: str, profile_id: str
    ) -> WorkspaceSnapshot:
        session = self._session(session_id)
        session.analysis_profile_id = profile_id
        return self._snapshot(session)

    async def preview_development(
        self, session_id: str, payload: DevelopmentDraftRequest
    ) -> MutationPreviewResponse:
        session = self._session(session_id)
        return self._preview(
            session,
            lambda: session.workspace.author.candidate_with_development(
                payload.alias, _development_from_request(session, payload)
            ),
        )

    async def apply_development(
        self, session_id: str, payload: DevelopmentDraftRequest
    ) -> WorkspaceSnapshot:
        session = self._session(session_id)
        async with session.lock:
            session.workspace.save_development(
                payload.alias, _development_from_request(session, payload)
            )
            return self._snapshot(session)

    async def delete_development(
        self, session_id: str, alias: str
    ) -> WorkspaceSnapshot:
        session = self._session(session_id)
        async with session.lock:
            session.workspace.save_development(alias, None)
            return self._snapshot(session)

    async def preview_interrupt(
        self, session_id: str, payload: InterruptDraftRequest
    ) -> MutationPreviewResponse:
        session = self._session(session_id)
        return self._preview(
            session,
            lambda: session.workspace.author.candidate_with_interrupt(
                payload.alias, _interrupt_from_request(session, payload)
            ),
        )

    async def apply_interrupt(
        self, session_id: str, payload: InterruptDraftRequest
    ) -> WorkspaceSnapshot:
        session = self._session(session_id)
        async with session.lock:
            session.workspace.save_interrupt(
                payload.alias, _interrupt_from_request(session, payload)
            )
            return self._snapshot(session)

    async def delete_interrupt(
        self, session_id: str, alias: str, rule_id: str
    ) -> WorkspaceSnapshot:
        session = self._session(session_id)
        async with session.lock:
            session.workspace.delete_interrupt(alias, rule_id)
            return self._snapshot(session)

    async def reorder_development(
        self, session_id: str, aliases: tuple[str, ...]
    ) -> WorkspaceSnapshot:
        session = self._session(session_id)
        async with session.lock:
            session.workspace.reorder_development(aliases)
            return self._snapshot(session)

    async def reorder_interrupts(
        self, session_id: str, references: tuple[str, ...]
    ) -> WorkspaceSnapshot:
        session = self._session(session_id)
        async with session.lock:
            session.workspace.reorder_interrupts(references)
            return self._snapshot(session)

    def _preview(self, session: DevelopmentSession, build) -> MutationPreviewResponse:
        workspace = session.workspace
        try:
            candidate = build()
            source = workspace.author.store.encode(candidate)
            reparsed = workspace.author.store.decode(source, context="candidate Rulebook")
            runtime, board = PolicyRuntime.replay(
                reparsed,
                workspace.attempt.history_before
                if workspace.attempt
                else tuple(workspace.history),
            )
            preview = (
                runtime.resolve(board)
                if board.turn == workspace.controlled_color and not board.is_game_over()
                else None
            )
        except (ValueError, FlowValidationError) as exc:
            return MutationPreviewResponse(valid=False, errors=[str(exc)])
        current = _current_decision(workspace)
        return MutationPreviewResponse(
            valid=True,
            warnings=list(workspace.author.store.warnings(reparsed)),
            current_decision=_decision_label(current),
            preview_decision=_decision_label(preview),
            generated_toml=source,
        )

    def _snapshot(self, session: DevelopmentSession) -> WorkspaceSnapshot:
        workspace = session.workspace
        rulebook = workspace.author.rulebook
        decision = _current_decision(workspace)
        analysis_board = (
            workspace.attempt.board_before if workspace.attempt else workspace.board
        )
        relations = (
            decision.relations
            if decision is not None
            else PositionAnalyzer().analyze(analysis_board, workspace.runtime.tracker)
        )
        development_results = {
            item.reference: item
            for item in decision.development_resolutions
        } if decision else {}
        interrupt_results = {
            item.reference: item
            for item in decision.interrupt_resolutions
        } if decision else {}
        aliases = rulebook.alias_by_ref
        piece_snapshots: list[PieceScriptSnapshot] = []
        for piece in rulebook.pieces:
            runtime_piece = workspace.runtime.tracker.get(piece.ref.original_piece_id)
            facts = relations.get(piece.ref.original_piece_id)
            development = None
            if piece.development is not None:
                reference = f"{piece.id}.develop"
                result = development_results.get(reference)
                status, explanation, condition = _development_state(
                    workspace, piece.ref, result
                )
                development = DevelopmentInstructionSnapshot(
                    reference=reference,
                    to=piece.development.to_square,
                    requires=list(piece.development.requires),
                    when=(
                        condition_to_data(piece.development.when, aliases=aliases)
                        if piece.development.when
                        else None
                    ),
                    why=piece.development.why,
                    status=status,
                    explanation=explanation,
                    condition=_condition_snapshot(condition),
                )
            interrupts = [
                _interrupt_snapshot(
                    piece.id,
                    rule,
                    interrupt_results.get(f"{piece.id}.{rule.id}"),
                    aliases,
                    workspace.runtime.completed_interrupts,
                )
                for rule in piece.rules
            ]
            piece_snapshots.append(
                PieceScriptSnapshot(
                    alias=piece.id,
                    ref=str(piece.ref),
                    label=piece.ref.label,
                    current_square=(
                        chess.square_name(runtime_piece.current_square)
                        if runtime_piece.current_square is not None
                        else None
                    ),
                    mechanical_state=_mechanical_state(runtime_piece),
                    authorable=piece.ref.color == rulebook.side,
                    development=development,
                    interrupts=interrupts,
                    relationships=_relations_snapshot(facts, aliases),
                )
            )
        return WorkspaceSnapshot(
            session_id=session.id,
            rulebook=RulebookSnapshot(
                name=rulebook.name,
                version=rulebook.version,
                path=self._display_path(session.flow_path),
                side=rulebook.side,
                opening_tags=[
                    OpeningTagSnapshot(eco=item.eco, name=item.name)
                    for item in rulebook.opening_tags
                ],
                warnings=list(workspace.author.store.warnings(rulebook)),
            ),
            position=PositionSnapshot(
                fen=workspace.board.fen(en_passant="fen"),
                history_san=list(workspace.history),
                turn="white" if workspace.board.turn else "black",
                legal_moves_uci=[move.uci() for move in workspace.board.legal_moves],
                last_move_uci=(
                    workspace.controller.interaction.last_move.uci
                    if workspace.controller.interaction.last_move
                    else None
                ),
                game_over=str(workspace.outcome) if workspace.outcome else None,
            ),
            decision=_decision_snapshot(decision),
            piece_scripts=piece_snapshots,
            development_order=list(rulebook.development_order),
            interrupt_order=list(rulebook.interrupt_order),
            attempt=(
                AttemptSnapshot(
                    result=workspace.attempt.result.value,  # type: ignore[arg-type]
                    move_uci=workspace.attempt.selected_move.move.uci,
                    move_san=workspace.attempt.selected_move.san,
                    expected_uci=(
                        workspace.attempt.decision.move.uci()
                        if workspace.attempt.decision.move
                        else None
                    ),
                    expected_san=workspace.attempt.decision.move_san,
                )
                if workspace.attempt
                else None
            ),
            navigation=NavigationSnapshot(
                can_back=workspace.can_go_back, can_restart=workspace.can_restart
            ),
            evaluation=session.evaluation,
        )

    def _session(self, session_id: str) -> DevelopmentSession:
        try:
            return self.sessions[session_id]
        except KeyError as exc:
            raise WebApiError(
                ApiErrorCode.SESSION_NOT_FOUND,
                f"Session {session_id!r} does not exist.",
                status_code=404,
            ) from exc

    def _resolve_flow_path(self, requested: str | None) -> Path:
        if requested is None:
            if self.startup_flow_path is not None:
                path = self.startup_flow_path
            else:
                candidates = sorted(
                    self.allowed_flow_directory.glob("*.toml"),
                    key=lambda item: item.stat().st_mtime,
                    reverse=True,
                )
                if not candidates:
                    raise WebApiError(
                        ApiErrorCode.FLOW_PERSISTENCE_ERROR,
                        "No Rulebook files were found.",
                        status_code=404,
                    )
                path = candidates[0]
        else:
            candidate = Path(requested)
            path = (
                candidate.resolve()
                if candidate.is_absolute()
                else (self.project_root / candidate).resolve()
            )
        try:
            path.relative_to(self.allowed_flow_directory)
        except ValueError as exc:
            raise WebApiError(
                ApiErrorCode.INVALID_REQUEST,
                "Rulebook path must be inside the configured flows directory.",
                status_code=403,
            ) from exc
        return path

    def _display_path(self, path: Path) -> str:
        try:
            return str(path.relative_to(self.project_root))
        except ValueError:
            return str(path)


def _development_from_request(
    session: DevelopmentSession, payload: DevelopmentDraftRequest
) -> DevelopmentInstruction:
    rulebook = session.workspace.author.rulebook
    piece = rulebook.piece_by_alias[payload.alias]
    aliases = {item.id: item.ref for item in rulebook.pieces}
    return DevelopmentInstruction(
        piece=piece.ref,
        to_square=payload.to,
        requires=tuple(payload.requires),
        when=(
            parse_condition(payload.when, aliases=aliases)
            if payload.when
            else None
        ),
        why=payload.why,
    )


def _interrupt_from_request(
    session: DevelopmentSession, payload: InterruptDraftRequest
) -> InterruptRule:
    rulebook = session.workspace.author.rulebook
    piece = rulebook.piece_by_alias[payload.alias]
    aliases = {item.id: item.ref for item in rulebook.pieces}
    attempts = tuple(_attempt_from_request(item, aliases) for item in payload.attempts)
    return InterruptRule(
        piece=piece.ref,
        id=payload.id or _new_rule_id(piece.rules),
        requires=tuple(payload.requires),
        after_san=tuple(payload.after_san) if payload.after_san is not None else None,
        when=(
            parse_condition(payload.when, aliases=aliases)
            if payload.when is not None
            else None
        ),
        required=payload.required,
        attempts=attempts,
        why=payload.why,
    )


def _attempt_from_request(
    payload: ActionAttemptRequest, aliases: dict[str, StartingPieceRef]
):
    if payload.move is not None:
        return MoveAttempt(payload.move)
    if payload.capture_type is not None:
        return CaptureAttempt(target_type=payload.capture_type)
    assert payload.capture is not None
    if payload.capture == "attacker":
        return CaptureAttempt(triggering_attacker=True)
    try:
        target = aliases.get(payload.capture) or StartingPieceRef.parse(payload.capture)
    except ValueError as exc:
        raise FlowValidationError(
            f"Unknown capture target {payload.capture!r}."
        ) from exc
    return CaptureAttempt(target_piece=target)


def _new_rule_id(rules: tuple[InterruptRule, ...]) -> str:
    existing = {item.id for item in rules}
    index = 1
    while f"interrupt-{index}" in existing:
        index += 1
    return f"interrupt-{index}"


def _current_decision(workspace: FlowWorkspace) -> PolicyDecision | None:
    if workspace.attempt is not None:
        return workspace.attempt.decision
    if workspace.policy_turn is not None:
        return workspace.policy_turn.decision
    return None


def _decision_label(decision: PolicyDecision | None) -> str | None:
    if decision is None:
        return None
    if decision.move_san:
        return f"{decision.source_id}: {decision.move_san}"
    return f"Frontier: {decision.frontier_reason.value if decision.frontier_reason else 'unknown'}"


def _decision_snapshot(decision: PolicyDecision | None) -> DecisionSnapshot | None:
    if decision is None:
        return None
    frontier = (
        FrontierSnapshot(
            reason=decision.frontier_reason.value,  # type: ignore[arg-type]
            explanation=decision.trace[-1],
        )
        if decision.frontier_reason
        else None
    )
    return DecisionSnapshot(
        status="frontier" if decision.source is DecisionSource.FRONTIER else "ready",
        source=decision.source.value,  # type: ignore[arg-type]
        move_uci=decision.move.uci() if decision.move else None,
        move_san=decision.move_san,
        instruction_ref=decision.source_id,
        why=decision.why,
        frontier=frontier,
        trace=list(decision.trace),
    )


def _condition_snapshot(result) -> ConditionEvaluationSnapshot | None:
    if result is None:
        return None
    return ConditionEvaluationSnapshot(
        value=result.value,
        explanation=result.explanation,
        details=dict(result.details),
    )


def _development_state(workspace, ref, result):
    if result is not None:
        return result.status.value, result.reason, result.condition
    runtime = workspace.runtime.tracker.get(ref.original_piece_id)
    if runtime.captured:
        return "captured", "Original piece is captured.", None
    if runtime.has_moved:
        return "completed", "Original piece has moved.", None
    return "not-ready", "Not evaluated on the current turn.", None


def _interrupt_snapshot(alias, rule, result, aliases, completed):
    attempt_results = result.attempts if result else ()
    attempts = []
    for index, attempt in enumerate(rule.attempts):
        evaluation = attempt_results[index] if index < len(attempt_results) else None
        if isinstance(attempt, MoveAttempt):
            kind, value = "move", attempt.to_square
        elif attempt.triggering_attacker:
            kind, value = "capture-attacker", "attacker"
        elif attempt.target_piece is not None:
            kind, value = "capture-piece", aliases.get(
                attempt.target_piece, str(attempt.target_piece)
            )
        else:
            kind, value = "capture-type", str(attempt.target_type)
        attempts.append(
            ActionAttemptSnapshot(
                kind=kind,  # type: ignore[arg-type]
                value=value,
                status=(
                    evaluation.status.value if evaluation else "not-evaluated"
                ),  # type: ignore[arg-type]
                candidates=[
                    move.uci() for move in evaluation.candidates
                ] if evaluation else [],
                reason=evaluation.reason if evaluation else None,
            )
        )
    reference = f"{alias}.{rule.id}"
    status = (
        result.status.value
        if result
        else "completed"
        if reference in completed
        else "trigger-false"
    )
    return InterruptRuleSnapshot(
        reference=reference,
        id=rule.id,
        requires=list(rule.requires),
        after_san=list(rule.after_san) if rule.after_san is not None else None,
        when=condition_to_data(rule.when, aliases=aliases) if rule.when else None,
        required=rule.required,
        attempts=attempts,
        why=rule.why,
        status=status,  # type: ignore[arg-type]
        explanation=result.reason if result else "Not evaluated on the current turn.",
        trigger=_condition_snapshot(result.trigger if result else None),
    )


def _relations_snapshot(facts, aliases):
    alias_by_id = {
        ref.original_piece_id: alias for ref, alias in aliases.items()
    }
    return PieceRelationSnapshot(
        attacks=[
            AttackSnapshot(
                piece=str(item.target),
                alias=alias_by_id.get(item.target),
                move_uci=item.capture.uci(),
            )
            for item in facts.attacks
        ],
        attackers=[
            AttackSnapshot(
                piece=str(item.attacker),
                alias=alias_by_id.get(item.attacker),
                move_uci=item.capture.uci(),
            )
            for item in facts.attackers
        ],
        defenders_by_attacker=[
            DefendersAgainstSnapshot(
                attacker=str(attacker),
                attacker_alias=alias_by_id.get(attacker),
                defenders=[
                    DefenseSnapshot(
                        piece=str(item.defender),
                        alias=alias_by_id.get(item.defender),
                        move_uci=item.recapture.uci(),
                    )
                    for item in defenders
                ],
            )
            for attacker, defenders in facts.defenders_by_attacker.items()
        ],
        distinct_defenders=[str(item) for item in facts.distinct_defenders],
        attacker_count=facts.attacker_count,
        defender_count=facts.defender_count,
        attack_balance=facts.attack_balance,
        attacked=facts.attacked,
        undefended=facts.undefended,
        under_defended=facts.under_defended,
        king_pinned=facts.king_pinned,
        pinned_by=str(facts.pinned_by) if facts.pinned_by else None,
    )


def _mechanical_state(piece):
    if piece.captured:
        return "captured-developed" if piece.has_moved else "captured-undeveloped"
    return "developed" if piece.has_moved else "undeveloped"
