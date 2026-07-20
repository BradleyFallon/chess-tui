"""In-memory Development Mode sessions over the shared v4 Python core."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
import secrets

import chess

from ..commands import (
    CommandAvailability,
    CommandFailure,
    CommandId,
    CommandInvocation,
    CommandRegistry,
)
from ..engine import (
    ANALYSIS_PROFILES,
    DEFAULT_ANALYSIS_PROFILE,
    ENGINE_PROTOTYPE_PROFILE,
    AnalysedMove,
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
    OpeningTag,
    PieceScript,
    Rulebook,
    normalized_position_key,
    replay_san,
)
from ..opening import OpeningDataError, OpeningMoveProvenance
from ..policy import (
    PositionAnalyzer,
    StartingPieceRef,
    condition_to_data,
    parse_condition,
)
from ..policy.runtime import (
    DecisionSource,
    PolicyDecision,
    PolicyRuntime,
)
from .api_models import (
    ActionAttemptRequest,
    ActionAttemptSnapshot,
    AnalysisProfileSnapshot,
    AnalysisRunSnapshot,
    AnalysisSettingsSnapshot,
    AttackSnapshot,
    AttemptSnapshot,
    AvailableCommandSnapshot,
    ConditionEvaluationSnapshot,
    DecisionSnapshot,
    DefenseSnapshot,
    DefendersAgainstSnapshot,
    DevelopmentDraftRequest,
    DevelopmentInstructionSnapshot,
    EngineLineSnapshot,
    EngineHealth,
    EvaluationSnapshot,
    FlowSourceResponse,
    FrontierSnapshot,
    InterruptDraftRequest,
    InterruptRuleSnapshot,
    MutationPreviewResponse,
    NavigationSnapshot,
    OpeningHistorySnapshot,
    OpeningSummarySnapshot,
    OpeningTagSnapshot,
    OpponentSettingsSnapshot,
    PieceRelationSnapshot,
    PieceScriptSnapshot,
    PositionSnapshot,
    PositionAnalysisSnapshot,
    RulebookSnapshot,
    TimelineEntrySnapshot,
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
    opponent_mode: str = "stored"
    last_opponent_source: str | None = None
    position_analysis: PositionAnalysisSnapshot | None = None
    hint_move_uci: str | None = None
    timeline: list[TimelineEntrySnapshot] = field(default_factory=list)
    next_timeline_id: int = 1


class EvaluationService:
    def __init__(
        self,
        engine: ChessEngineService | None,
        *,
        engine_identity: str = "",
    ) -> None:
        self.engine = engine
        self.engine_identity = engine_identity or None
        self.status = "off" if engine is None else "configured"
        self.last_engine_name: str | None = None
        self._cache: dict[tuple[str, str, str], tuple[AnalysedMove, ...]] = {}
        self._lock = asyncio.Lock()

    @property
    def health(self) -> EngineHealth:
        return EngineHealth(status=self.status)  # type: ignore[arg-type]

    async def analyse(self, board: chess.Board, profile_id: str) -> AnalysisRunSnapshot:
        if self.engine is None:
            return AnalysisRunSnapshot(
                status="off", message="Engine is not configured."
            )
        profile = next(item for item in ANALYSIS_PROFILES if item.id == profile_id)
        try:
            result = (await self.analyse_lines(board, profile_id, count=1))[0]
        except (EngineError, RuntimeError) as exc:
            self.status = "error"
            return AnalysisRunSnapshot(status="error", message=str(exc))
        return _analysis_run_snapshot(result, profile.id, profile.depth)

    async def analyse_lines(
        self,
        board: chess.Board,
        profile_id: str,
        *,
        count: int,
    ) -> tuple[AnalysedMove, ...]:
        if self.engine is None:
            raise RuntimeError("Engine analysis is disabled.")
        legal_count = board.legal_moves.count()
        if legal_count == 0:
            raise RuntimeError("The position has no legal moves to analyse.")
        profile = next(item for item in ANALYSIS_PROFILES if item.id == profile_id)
        requested = min(count, legal_count)
        key = (
            normalized_position_key(board),
            profile.id,
            self.engine_identity or type(self.engine).__name__,
        )
        async with self._lock:
            cached = self._cache.get(key, ())
            if len(cached) >= requested:
                return cached[:requested]
            try:
                results = await self.engine.analyse(
                    board.copy(stack=False),
                    count=requested,
                    profile=profile,
                )
                if not results:
                    raise RuntimeError("Engine returned no analysis rows.")
            except EngineError:
                self.status = "error"
                raise
            self._cache[key] = results
        self.status = "ready"
        self.last_engine_name = results[0].engine_name or self.engine_identity
        return results

    async def choose_move(self, board: chess.Board) -> chess.Move:
        if self.engine is None:
            raise WebApiError(
                ApiErrorCode.ENGINE_ERROR,
                "Engine reply mode requires a configured chess engine.",
                status_code=503,
            )
        async with self._lock:
            try:
                return await self.engine.choose_move(board, ENGINE_PROTOTYPE_PROFILE)
            except EngineError as exc:
                self.status = "error"
                raise WebApiError(
                    ApiErrorCode.ENGINE_ERROR,
                    f"The configured engine could not choose a reply: {exc}",
                    status_code=502,
                ) from exc


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
        self.project_root = project_root.resolve()
        self.allowed_flow_directory = allowed_flow_directory.resolve()
        self.startup_flow_path = (
            startup_flow_path.resolve() if startup_flow_path else None
        )
        self.evaluations = EvaluationService(
            engine,
            engine_identity=engine_identity,
        )
        self.commands = CommandRegistry()
        self.sessions: dict[str, DevelopmentSession] = {}

    async def create_session(
        self, requested_flow_path: str | None
    ) -> WorkspaceSnapshot:
        path = self._resolve_flow_path(requested_flow_path)
        workspace = FlowWorkspace(path)
        workspace.restart()
        session = DevelopmentSession(secrets.token_urlsafe(12), path, workspace)
        if self.evaluations.engine is not None:
            session.opponent_mode = "engine"
        self._append_timeline(
            session,
            "system",
            "Development session ready",
            f"Loaded {workspace.author.rulebook.name} as a v4 Rulebook.",
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
        return FlowSourceResponse(
            path=self._display_path(session.flow_path),
            source=session.flow_path.read_text(encoding="utf-8"),
        )

    async def submit_move(self, session_id: str, uci: str) -> WorkspaceSnapshot:
        session = self._session(session_id)
        async with session.lock:
            try:
                self._submit_move_locked(session, uci)
            except (ValueError, FlowValidationError) as exc:
                raise WebApiError(
                    ApiErrorCode.INVALID_MOVE, str(exc), status_code=422
                ) from exc
            return await self._snapshot(session)

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

    async def submit_chat(self, session_id: str, text: str) -> WorkspaceSnapshot:
        session = self._session(session_id)
        async with session.lock:
            self._append_timeline(session, "user", "You", text.strip())
            try:
                invocation = self.commands.parse_chat(text)
                await self._execute_command_locked(session, invocation)
            except (
                CommandFailure,
                FlowValidationError,
                ValueError,
                WebApiError,
            ) as exc:
                self._append_timeline(
                    session,
                    "error",
                    "Command failed",
                    str(exc),
                )
            return await self._snapshot(session)

    async def next_opponent(self, session_id: str) -> WorkspaceSnapshot:
        session = self._session(session_id)
        async with session.lock:
            try:
                await self._play_next_opponent_locked(session)
            except CommandFailure as exc:
                raise WebApiError(
                    ApiErrorCode.INVALID_REQUEST,
                    str(exc),
                    status_code=409,
                ) from exc
            return await self._snapshot(session)

    async def update_opponent_mode(
        self,
        session_id: str,
        mode: str,
    ) -> WorkspaceSnapshot:
        session = self._session(session_id)
        async with session.lock:
            session.opponent_mode = mode
            self._append_timeline(
                session,
                "system",
                "Opponent mode changed",
                {
                    "stored": "Stored replies only. Missing branches will fail clearly.",
                    "engine": "Configured engine replies only. Engine errors remain visible.",
                    "manual": "Opponent moves must be entered manually.",
                }[mode],
            )
            return await self._snapshot(session)

    async def retry_policy(self, session_id: str) -> WorkspaceSnapshot:
        session = self._session(session_id)
        async with session.lock:
            session.workspace.retry_policy_move()
            session.position_analysis = None
            session.hint_move_uci = None
            self._append_timeline(
                session,
                "system",
                "Retry",
                "Restored the position before the attempted move.",
            )
            return await self._snapshot(session)

    async def continue_policy(self, session_id: str) -> WorkspaceSnapshot:
        session = self._session(session_id)
        async with session.lock:
            attempt = session.workspace.attempt
            san = attempt.decision.move_san if attempt else None
            session.workspace.continue_with_policy_move()
            session.position_analysis = None
            session.hint_move_uci = None
            self._append_timeline(
                session,
                "success",
                "Used Rulebook recommendation",
                "Committed the selected v4 instruction without changing the Rulebook.",
            )
            if san:
                self._append_opening_timeline(session, san)
            return await self._snapshot(session)

    async def accept_attempt_as_interrupt(self, session_id: str) -> WorkspaceSnapshot:
        session = self._session(session_id)
        async with session.lock:
            attempt = session.workspace.attempt
            san = attempt.selected_move.san if attempt else None
            rule = session.workspace.accept_attempt_as_interrupt()
            session.position_analysis = None
            session.hint_move_uci = None
            self._append_timeline(
                session,
                "success",
                "Accepted exact-position move",
                f"Added or replaced {rule.id} as a piece-owned exact-position interrupt.",
            )
            if san:
                self._append_opening_timeline(session, san)
            return await self._snapshot(session)

    async def go_back(self, session_id: str) -> WorkspaceSnapshot:
        session = self._session(session_id)
        async with session.lock:
            try:
                session.workspace.go_back_to_previous_decision()
            except FlowValidationError as exc:
                raise WebApiError(
                    ApiErrorCode.INVALID_NAVIGATION, str(exc), status_code=409
                ) from exc
            session.position_analysis = None
            session.hint_move_uci = None
            self._append_timeline(
                session,
                "system",
                "Moved back",
                "Replayed the retained line and restored Rulebook completion state.",
            )
            return await self._snapshot(session)

    async def restart(self, session_id: str) -> WorkspaceSnapshot:
        session = self._session(session_id)
        async with session.lock:
            session.workspace.restart()
            session.position_analysis = None
            session.hint_move_uci = None
            self._append_timeline(
                session,
                "system",
                "Line restarted",
                "Returned to the Rulebook start position.",
            )
            return await self._snapshot(session)

    async def reload(self, session_id: str) -> WorkspaceSnapshot:
        session = self._session(session_id)
        async with session.lock:
            session.workspace.reload()
            session.position_analysis = None
            session.hint_move_uci = None
            return await self._snapshot(session)

    async def analyse_position(self, session_id: str) -> WorkspaceSnapshot:
        session = self._session(session_id)
        async with session.lock:
            await self._analyse_locked(session)
            return await self._snapshot(session)

    async def update_analysis_profile(
        self, session_id: str, profile_id: str
    ) -> WorkspaceSnapshot:
        session = self._session(session_id)
        async with session.lock:
            session.analysis_profile_id = profile_id
            session.position_analysis = None
            self._append_timeline(
                session,
                "system",
                "Analysis strength changed",
                f"Future analysis uses {_analysis_profile(profile_id).label}.",
            )
            return await self._snapshot(session)

    async def add_opening_tag(
        self,
        session_id: str,
        record_id: int,
    ) -> WorkspaceSnapshot:
        session = self._session(session_id)
        async with session.lock:
            match = self._opening_match(session.workspace, record_id)
            session.workspace.add_opening_tag(OpeningTag(match.eco, match.name))
            self._append_timeline(
                session,
                "success",
                f"Labeled Rulebook {match.name}",
                f"Saved {match.eco} as durable Rulebook metadata.",
            )
            return await self._snapshot(session)

    async def remove_opening_tag(
        self,
        session_id: str,
        record_id: int,
    ) -> WorkspaceSnapshot:
        session = self._session(session_id)
        async with session.lock:
            match = self._opening_match(session.workspace, record_id)
            session.workspace.remove_opening_tag(OpeningTag(match.eco, match.name))
            self._append_timeline(
                session,
                "system",
                f"Removed Rulebook label {match.name}",
                f"Removed {match.eco} from durable Rulebook metadata.",
            )
            return await self._snapshot(session)

    @staticmethod
    def _opening_match(workspace: FlowWorkspace, record_id: int):
        try:
            return workspace.opening_classifier.match_by_id(record_id)
        except OpeningDataError as exc:
            raise WebApiError(
                ApiErrorCode.INVALID_REQUEST,
                f"Unknown opening record id {record_id}.",
            ) from exc

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
            return await self._snapshot(session)

    async def delete_development(
        self, session_id: str, alias: str
    ) -> WorkspaceSnapshot:
        session = self._session(session_id)
        async with session.lock:
            session.workspace.save_development(alias, None)
            return await self._snapshot(session)

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
            return await self._snapshot(session)

    async def delete_interrupt(
        self, session_id: str, alias: str, rule_id: str
    ) -> WorkspaceSnapshot:
        session = self._session(session_id)
        async with session.lock:
            session.workspace.delete_interrupt(alias, rule_id)
            return await self._snapshot(session)

    async def reorder_development(
        self, session_id: str, aliases: tuple[str, ...]
    ) -> WorkspaceSnapshot:
        session = self._session(session_id)
        async with session.lock:
            session.workspace.reorder_development(aliases)
            return await self._snapshot(session)

    async def reorder_interrupts(
        self, session_id: str, references: tuple[str, ...]
    ) -> WorkspaceSnapshot:
        session = self._session(session_id)
        async with session.lock:
            session.workspace.reorder_interrupts(references)
            return await self._snapshot(session)

    def _submit_move_locked(self, session: DevelopmentSession, uci: str) -> None:
        workspace = session.workspace
        session.position_analysis = None
        session.hint_move_uci = None
        move = chess.Move.from_uci(uci)
        if move not in workspace.board.legal_moves:
            raise FlowValidationError(f"{uci!r} is not legal in the current position.")
        san = workspace.board.san(move)
        color = "White" if workspace.board.turn == chess.WHITE else "Black"
        if workspace.is_policy_turn:
            attempt = workspace.submit_policy_uci(uci)
            if attempt.result.value == "correct":
                workspace.complete_correct_move()
                self._append_timeline(
                    session,
                    "move",
                    f"{color} played {san}",
                    f"Matched {attempt.decision.source_id}: "
                    f"{attempt.decision.why or 'Rulebook recommendation.'}",
                )
                self._append_opening_timeline(session, san)
            else:
                if attempt.decision.move_san:
                    message = (
                        f"Expected {attempt.decision.move_san} from "
                        f"{attempt.decision.source_id}."
                    )
                else:
                    frontier = (
                        attempt.decision.frontier_reason.value
                        if attempt.decision.frontier_reason is not None
                        else "a Rulebook frontier"
                    )
                    message = f"Reached {frontier}."
                self._append_timeline(
                    session,
                    "warning",
                    f"{color} attempted {san}",
                    message,
                )
            return
        workspace.submit_opponent_uci(
            uci,
            move_source=OpeningMoveProvenance.MANUAL,
        )
        session.last_opponent_source = "manual"
        self._append_timeline(
            session,
            "move",
            f"{color} played {san}",
            "Manual opponent move.",
        )
        self._append_opening_timeline(session, san)
        if workspace.outcome is None:
            workspace.begin_policy_turn()

    async def _play_next_opponent_locked(
        self,
        session: DevelopmentSession,
    ) -> None:
        workspace = session.workspace
        if workspace.is_policy_turn or workspace.outcome is not None:
            raise CommandFailure(
                "COMMAND_UNAVAILABLE",
                "An automatic opponent reply is not available on this turn.",
            )
        if session.opponent_mode == "manual":
            raise CommandFailure(
                "MANUAL_OPPONENT_MODE",
                "Manual mode requires an opponent move on the board or in SAN.",
            )
        session.position_analysis = None
        session.hint_move_uci = None
        if session.opponent_mode == "stored":
            reply = self._stored_reply(session)
            if reply is None:
                raise CommandFailure(
                    "STORED_REPLY_MISSING",
                    "No stored opponent reply exists for this exact history.",
                )
            san = reply.move_san
            workspace.submit_opponent_san(
                san,
                move_source=OpeningMoveProvenance.RECORDED_BRANCH,
            )
            source = "stored"
            detail = f"Stored reply {reply.id}."
        else:
            move = await self.evaluations.choose_move(workspace.board.copy(stack=False))
            if move not in workspace.board.legal_moves:
                raise WebApiError(
                    ApiErrorCode.ENGINE_ERROR,
                    "The configured engine returned an illegal reply.",
                    status_code=502,
                )
            san = workspace.board.san(move)
            workspace.submit_opponent_uci(
                move.uci(),
                move_source=OpeningMoveProvenance.ENGINE,
            )
            source = "engine"
            detail = "Configured engine reply."
        session.last_opponent_source = source
        color = "White" if not workspace.controlled_color else "Black"
        self._append_timeline(
            session,
            "move",
            f"{color} played {san}",
            detail,
        )
        self._append_opening_timeline(session, san)
        if workspace.outcome is None:
            workspace.begin_policy_turn()

    async def _analyse_locked(self, session: DevelopmentSession) -> None:
        try:
            lines = await self.evaluations.analyse_lines(
                session.workspace.board,
                session.analysis_profile_id,
                count=4,
            )
        except (EngineError, RuntimeError) as exc:
            session.position_analysis = None
            session.evaluation = EvaluationSnapshot(
                status="error",
                message=str(exc),
                engine_name=self.evaluations.last_engine_name
                or self.evaluations.engine_identity,
            )
            self._append_timeline(
                session,
                "error",
                "Engine analysis",
                str(exc),
            )
            return
        profile = _analysis_profile(session.analysis_profile_id)
        result = _analysis_run_snapshot(lines[0], profile.id, profile.depth)
        session.position_analysis = PositionAnalysisSnapshot(
            book_moves=[
                item.san for item in session.workspace.get_book_continuations()
            ],
            engine_moves=[
                EngineLineSnapshot(
                    uci=line.uci,
                    san=line.san,
                    centipawns=line.evaluation_cp,
                    mate_in=line.mate_in,
                    principal_variation=list(line.principal_variation),
                )
                for line in lines
            ],
        )
        session.evaluation = EvaluationSnapshot(
            status=result.status,
            centipawns=result.centipawns,
            mate_in=result.mate_in,
            message=result.message,
            engine_name=result.engine_name,
            profile_id=result.profile_id,
            requested_depth=result.requested_depth,
            actual_depth=result.actual_depth,
            selective_depth=result.selective_depth,
            nodes=result.nodes,
            nps=result.nps,
            time_ms=result.time_ms,
            best_move_uci=result.move_uci,
            best_move_san=result.move_san,
        )
        self._append_timeline(
            session,
            "analysis" if result.status == "ready" else "error",
            "Engine analysis",
            (
                f"Best move {result.move_san or result.move_uci}; "
                f"{_score_text(result.centipawns, result.mate_in)}. "
                f"Compared {len(lines)} engine candidate(s)."
                if result.status == "ready"
                else result.message or "Engine analysis is unavailable."
            ),
        )

    async def _execute_command_locked(
        self,
        session: DevelopmentSession,
        invocation: CommandInvocation,
    ) -> None:
        availability = self._command_availability(session)
        if not self.commands.is_available(invocation.command, availability):
            definition = self.commands.definition(invocation.command)
            raise CommandFailure(
                "COMMAND_UNAVAILABLE",
                f"{definition.slash} is not available in the current position.",
            )
        workspace = session.workspace
        command = invocation.command
        if command is CommandId.PLAY_MOVE:
            if not invocation.move:
                raise CommandFailure("INVALID_COMMAND", "A move is required.")
            move = (
                workspace.board.parse_san(invocation.move)
                if invocation.notation == "san"
                else chess.Move.from_uci(invocation.move)
            )
            self._submit_move_locked(session, move.uci())
            return
        if command is CommandId.RETRY_POLICY:
            workspace.retry_policy_move()
            session.position_analysis = None
            session.hint_move_uci = None
            self._append_timeline(
                session, "system", "Retry", "Restored the attempted position."
            )
            return
        if command is CommandId.CONTINUE_POLICY:
            attempt = workspace.attempt
            san = attempt.decision.move_san if attempt else None
            workspace.continue_with_policy_move()
            session.position_analysis = None
            session.hint_move_uci = None
            self._append_timeline(
                session,
                "success",
                "Used Rulebook recommendation",
                "Committed the selected instruction.",
            )
            if san:
                self._append_opening_timeline(session, san)
            return
        if command is CommandId.ACCEPT_ATTEMPT_HERE:
            attempt = workspace.attempt
            san = attempt.selected_move.san if attempt else None
            rule = workspace.accept_attempt_as_interrupt()
            session.position_analysis = None
            session.hint_move_uci = None
            self._append_timeline(
                session,
                "success",
                "Accepted exact-position move",
                f"Saved piece-owned interrupt {rule.id}.",
            )
            if san:
                self._append_opening_timeline(session, san)
            return
        if command is CommandId.NEXT_OPPONENT:
            await self._play_next_opponent_locked(session)
            return
        if command is CommandId.GO_BACK:
            workspace.go_back_to_previous_decision()
            session.position_analysis = None
            session.hint_move_uci = None
            self._append_timeline(
                session, "system", "Moved back", "Replayed the retained line."
            )
            return
        if command is CommandId.RESTART:
            workspace.restart()
            session.position_analysis = None
            session.hint_move_uci = None
            self._append_timeline(
                session, "system", "Line restarted", "Returned to the start."
            )
            return
        if command is CommandId.ANALYSE_POSITION:
            await self._analyse_locked(session)
            return
        if command is CommandId.HINT_POLICY_MOVE:
            decision = _current_decision(workspace)
            if decision is None or decision.move is None:
                raise CommandFailure(
                    "COMMAND_UNAVAILABLE",
                    "No Rulebook move is available to highlight.",
                )
            session.hint_move_uci = decision.move.uci()
            self._append_timeline(
                session,
                "assistant",
                "Rule Engine hint",
                f"Highlighted {decision.move_san} from {decision.source_id}.",
            )
            return
        message = self._diagnostic_command_text(session, invocation)
        self._append_timeline(session, "assistant", "Rule Engine", message)

    def _diagnostic_command_text(
        self,
        session: DevelopmentSession,
        invocation: CommandInvocation,
    ) -> str:
        workspace = session.workspace
        decision = _current_decision(workspace)
        command = invocation.command
        if command is CommandId.EXPLAIN_DECISION:
            if decision is None:
                return "There is no current Rulebook decision."
            source = decision.source_id or (
                decision.frontier_reason.value
                if decision.frontier_reason is not None
                else "Rulebook decision"
            )
            return f"{source}: {decision.why or decision.trace[-1]}"
        if command is CommandId.TRACE_DECISION:
            return "\n".join(decision.trace) if decision else "No decision trace."
        if command is CommandId.INSPECT_POSITION:
            legal = [workspace.board.san(move) for move in workspace.board.legal_moves]
            return (
                f"FEN: {workspace.board.fen(en_passant='fen')}\n"
                f"History: {' '.join(workspace.history) or 'start'}\n"
                f"Turn: {'White' if workspace.board.turn else 'Black'}"
                f"{' (in check)' if workspace.board.is_check() else ''}\n"
                f"Legal moves ({len(legal)}): {', '.join(legal)}"
            )
        if command is CommandId.INSPECT_OPENING:
            context = workspace.get_current_opening_context()
            match = context.primary_match or context.last_known_match
            if match is None:
                return "No current or last-known named opening."
            exact = "current" if context.primary_match else "last known"
            source = context.move_source.value if context.move_source else "start"
            return (
                f"{match.eco} {match.name} ({exact}). "
                f"Move source: {source}. "
                f"{len(context.book_continuations)} indexed continuation(s)."
            )
        if command is CommandId.LIST_OPENINGS:
            context = workspace.get_current_opening_context()
            matches = ", ".join(
                f"{item.eco} {item.name}" for item in context.current_matches
            )
            return matches or "No exact named opening position."
        if command is CommandId.LIST_DEFENSES:
            values = workspace.get_reachable_defenses()
            return (
                "Book defenses still reachable: " + ", ".join(values)
                if values
                else "No named book defenses are currently reachable."
            )
        if command is CommandId.INSPECT_BOOK:
            context = workspace.get_current_opening_context()
            moves = context.book_continuations
            alignment = (
                "The last move followed the index."
                if context.played_move_in_book
                else (
                    "The last move left the indexed route."
                    if context.played_move_in_book is False
                    else "No move has been committed."
                )
            )
            return (
                f"{alignment}\nBook continuations: "
                + ", ".join(item.san for item in moves)
                if moves
                else f"{alignment}\nNo bundled book continuation exists here."
            )
        if command is CommandId.INSPECT_BOOK_HISTORY:
            return (
                " · ".join(
                    f"{item.ply}. {item.san}: "
                    f"{item.context.primary_match.name if item.context.primary_match else 'unnamed'}"
                    for item in workspace.get_opening_history()
                )
                or "Opening history is empty."
            )
        if command is CommandId.LIST_RULES:
            development = (
                ", ".join(
                    f"{reference}.develop"
                    for reference in workspace.author.rulebook.development_order
                )
                or "none"
            )
            interrupts = ", ".join(workspace.author.rulebook.interrupt_order) or "none"
            return (
                f"Development order: {development}\n" f"Interrupt order: {interrupts}"
            )
        if command is CommandId.INSPECT_RULE:
            reference = invocation.rule_id or ""
            if reference.endswith(".develop"):
                alias = reference.removesuffix(".develop")
                piece = workspace.author.rulebook.piece_by_alias.get(alias)
                if piece and piece.development:
                    return f"{reference}: move to {piece.development.to_square}. {piece.development.why}"
            rule = workspace.author.rulebook.interrupt_by_ref.get(reference)
            if rule:
                return f"{reference}: {rule.why}"
            raise CommandFailure("UNKNOWN_RULE", f"Unknown instruction {reference!r}.")
        if command is CommandId.HINT_POLICY_MOVE:
            return (
                f"Hint: {decision.move_san} ({decision.source_id})."
                if decision and decision.move_san
                else "No move is available to hint."
            )
        if command is CommandId.LIST_COMMANDS:
            return " · ".join(
                item.usage
                for item in self.commands.available(self._command_availability(session))
            )
        return "Command completed."

    def _command_availability(
        self,
        session: DevelopmentSession,
    ) -> CommandAvailability:
        workspace = session.workspace
        phase = _phase(workspace)
        decision = _current_decision(workspace)
        return CommandAvailability(
            phase=phase,  # type: ignore[arg-type]
            engine_available=self.evaluations.engine is not None,
            has_decision=decision is not None,
            has_decision_move=decision is not None and decision.move is not None,
            mismatch=(
                workspace.attempt is not None
                and workspace.attempt.result.value == "mismatch"
            ),
            authorable_attempt=(
                workspace.attempt is not None
                and workspace.attempt.result.value in {"mismatch", "frontier"}
            ),
            can_back=workspace.can_go_back,
            can_restart=workspace.can_restart,
            has_rules=bool(
                workspace.author.rulebook.development_order
                or workspace.author.rulebook.interrupt_order
            ),
            opponent_available=(
                phase == "opponent-ready"
                and session.opponent_mode != "manual"
                and (
                    session.opponent_mode == "stored"
                    and self._stored_reply(session) is not None
                    or session.opponent_mode == "engine"
                    and self.evaluations.engine is not None
                )
            ),
        )

    def _stored_reply(self, session: DevelopmentSession):
        history = tuple(session.workspace.history)
        return next(
            (
                reply
                for reply in session.workspace.author.rulebook.opponent_replies
                if reply.after_san == history
            ),
            None,
        )

    def _append_timeline(
        self,
        session: DevelopmentSession,
        kind: str,
        title: str,
        message: str,
    ) -> None:
        session.timeline.append(
            TimelineEntrySnapshot(
                id=session.next_timeline_id,
                kind=kind,  # type: ignore[arg-type]
                title=title,
                message=message,
            )
        )
        session.next_timeline_id += 1
        if len(session.timeline) > 100:
            del session.timeline[:-100]

    def _append_opening_timeline(
        self,
        session: DevelopmentSession,
        san: str,
    ) -> None:
        context = session.workspace.get_current_opening_context()
        current = context.primary_match
        known = current or context.last_known_match
        if known is not None:
            identity = f"{known.eco} · {known.name}"
        else:
            identity = "No exact named opening"
        source = context.move_source.value if context.move_source else "unknown"
        alignment = (
            "The move follows the bundled opening index."
            if context.played_move_in_book
            else "The line is outside a direct indexed continuation."
        )
        self._append_timeline(
            session,
            "opening",
            f"Opening after {san}",
            f"{identity}. Source: {source}. {alignment}",
        )

    async def _refresh_evaluation(self, session: DevelopmentSession) -> None:
        if self.evaluations.engine is None:
            session.evaluation = EvaluationSnapshot(
                status="off",
                message="Engine is not configured.",
            )
            return
        workspace = session.workspace
        if workspace.outcome is not None:
            return
        current = await self.evaluations.analyse(
            workspace.board,
            session.analysis_profile_id,
        )
        if current.status != "ready":
            session.evaluation = EvaluationSnapshot(
                status=current.status,
                message=current.message,
                engine_name=current.engine_name
                or self.evaluations.last_engine_name
                or self.evaluations.engine_identity,
            )
            return
        previous_board: chess.Board | None = None
        if workspace.attempt is not None:
            previous_board = workspace.attempt.board_before
        elif workspace.history:
            previous_board = replay_san(
                workspace.author.rulebook.start_fen,
                tuple(workspace.history[:-1]),
            )
        previous = (
            await self.evaluations.analyse(
                previous_board,
                session.analysis_profile_id,
            )
            if previous_board is not None
            else None
        )
        previous_cp = (
            previous.centipawns
            if previous is not None and previous.status == "ready"
            else None
        )
        change = (
            current.centipawns - previous_cp
            if current.centipawns is not None and previous_cp is not None
            else None
        )
        session.evaluation = EvaluationSnapshot(
            status="ready",
            centipawns=current.centipawns,
            mate_in=current.mate_in,
            previous_centipawns=previous_cp,
            previous_mate_in=(
                previous.mate_in
                if previous is not None and previous.status == "ready"
                else None
            ),
            change_centipawns=change,
            engine_name=current.engine_name,
            profile_id=current.profile_id,
            requested_depth=current.requested_depth,
            actual_depth=current.actual_depth,
            selective_depth=current.selective_depth,
            nodes=current.nodes,
            nps=current.nps,
            time_ms=current.time_ms,
            best_move_uci=current.move_uci,
            best_move_san=current.move_san,
        )

    def _preview(self, session: DevelopmentSession, build) -> MutationPreviewResponse:
        workspace = session.workspace
        try:
            candidate = build()
            source = workspace.author.store.encode(candidate)
            reparsed = workspace.author.store.decode(
                source, context="candidate Rulebook"
            )
            runtime, board = PolicyRuntime.replay(
                reparsed,
                (
                    workspace.attempt.history_before
                    if workspace.attempt
                    else tuple(workspace.history)
                ),
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

    async def _snapshot(self, session: DevelopmentSession) -> WorkspaceSnapshot:
        await self._refresh_evaluation(session)
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
        development_results = (
            {item.reference: item for item in decision.development_resolutions}
            if decision
            else {}
        )
        interrupt_results = (
            {item.reference: item for item in decision.interrupt_resolutions}
            if decision
            else {}
        )
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
            analysis_settings=AnalysisSettingsSnapshot(
                status=self.evaluations.status,  # type: ignore[arg-type]
                selected_profile_id=session.analysis_profile_id,
                engine_name=self.evaluations.last_engine_name
                or self.evaluations.engine_identity,
                profiles=[
                    AnalysisProfileSnapshot(
                        id=profile.id,
                        label=profile.label,
                        depth=profile.depth or 0,
                        cost_label=profile.cost_label,
                        cost_description=profile.cost_description,
                    )
                    for profile in ANALYSIS_PROFILES
                ],
            ),
            opponent=OpponentSettingsSnapshot(
                mode=session.opponent_mode,  # type: ignore[arg-type]
                stored_reply_available=self._stored_reply(session) is not None,
                engine_available=self.evaluations.engine is not None,
                last_source=session.last_opponent_source,  # type: ignore[arg-type]
            ),
            opening=_opening_summary(workspace),
            opening_history=[
                OpeningHistorySnapshot(
                    ply=entry.ply,
                    san=entry.san,
                    opening_name=(
                        entry.context.primary_match.name
                        if entry.context.primary_match
                        else (
                            entry.context.last_known_match.name
                            if entry.context.last_known_match
                            else None
                        )
                    ),
                    move_source=(
                        entry.context.move_source.value
                        if entry.context.move_source
                        else None
                    ),
                )
                for entry in workspace.get_opening_history()
            ],
            position_analysis=session.position_analysis,
            timeline=list(session.timeline),
            available_commands=[
                AvailableCommandSnapshot(
                    id=definition.id.value,
                    slash=definition.slash,
                    usage=definition.usage,
                    description=definition.description,
                    arguments=[argument.name for argument in definition.arguments],
                )
                for definition in self.commands.available(
                    self._command_availability(session)
                )
            ],
            hint_move_uci=session.hint_move_uci,
            rulebook_source=workspace.author.store.encode(rulebook),
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
    piece = _piece_by_alias(rulebook, payload.alias)
    aliases = {item.id: item.ref for item in rulebook.pieces}
    return DevelopmentInstruction(
        piece=piece.ref,
        to_square=payload.to,
        requires=tuple(payload.requires),
        when=(
            parse_condition(payload.when, aliases=aliases)
            if payload.when is not None
            else None
        ),
        why=payload.why,
    )


def _interrupt_from_request(
    session: DevelopmentSession, payload: InterruptDraftRequest
) -> InterruptRule:
    rulebook = session.workspace.author.rulebook
    piece = _piece_by_alias(rulebook, payload.alias)
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


def _piece_by_alias(rulebook: Rulebook, alias: str) -> PieceScript:
    try:
        return rulebook.piece_by_alias[alias]
    except KeyError as exc:
        raise FlowValidationError(f"Unknown piece alias {alias!r}.") from exc


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


def _phase(workspace: FlowWorkspace) -> str:
    if workspace.outcome is not None:
        return "game-over"
    if workspace.attempt is not None:
        return "policy-result"
    return "policy-ready" if workspace.is_policy_turn else "opponent-ready"


def _analysis_profile(profile_id: str):
    return next(profile for profile in ANALYSIS_PROFILES if profile.id == profile_id)


def _analysis_run_snapshot(
    result: AnalysedMove,
    profile_id: str,
    requested_depth: int | None,
) -> AnalysisRunSnapshot:
    return AnalysisRunSnapshot(
        status="ready",
        centipawns=result.evaluation_cp,
        mate_in=result.mate_in,
        move_uci=result.uci,
        move_san=result.san,
        engine_name=result.engine_name,
        profile_id=result.profile_id or profile_id,
        requested_depth=result.requested_depth or requested_depth,
        actual_depth=result.actual_depth,
        selective_depth=result.selective_depth,
        nodes=result.nodes,
        nps=result.nps,
        time_ms=result.time_ms,
    )


def _score_text(centipawns: int | None, mate_in: int | None) -> str:
    if mate_in is not None:
        return f"{'+' if mate_in >= 0 else '-'}M{abs(mate_in)}"
    if centipawns is None:
        return "no numeric score"
    return f"{centipawns / 100:+.2f} from White's perspective"


def _opening_summary(workspace: FlowWorkspace) -> OpeningSummarySnapshot:
    context = workspace.get_current_opening_context()
    primary = context.primary_match
    tags = {(tag.eco, tag.name) for tag in workspace.author.rulebook.opening_tags}
    return OpeningSummarySnapshot(
        record_id=primary.record_id if primary else None,
        name=primary.name if primary else None,
        eco=primary.eco if primary else None,
        last_known_name=(
            context.last_known_match.name if context.last_known_match else None
        ),
        move_source=context.move_source.value if context.move_source else None,
        book_continuations=[item.san for item in context.book_continuations],
        reachable_defenses=list(context.reachable_defenses),
        is_tagged=(
            (primary.eco, primary.name) in tags if primary is not None else False
        ),
    )


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
                candidates=(
                    [move.uci() for move in evaluation.candidates] if evaluation else []
                ),
                reason=evaluation.reason if evaluation else None,
            )
        )
    reference = f"{alias}.{rule.id}"
    status = (
        result.status.value
        if result
        else "completed" if reference in completed else "trigger-false"
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
    alias_by_id = {ref.original_piece_id: alias for ref, alias in aliases.items()}
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
