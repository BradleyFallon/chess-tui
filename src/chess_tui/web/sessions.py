"""In-memory Development Mode sessions over the shared v3 Python core."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field, replace
from pathlib import Path
import secrets
from typing import Literal, cast

import chess

from ..commands import (
    AssistantReply,
    ClientEffect,
    CommandAvailability,
    CommandFailure,
    CommandId,
    CommandInvocation,
    CommandOutcome,
    CommandRegistry,
)
from ..engine import (
    ANALYSIS_PROFILES,
    DEFAULT_ANALYSIS_PROFILE,
    ENGINE_PROTOTYPE_PROFILE,
    AnalysedMove,
    ChessEngineService,
    EngineError,
    EngineProfile,
    build_white_move_assessment,
    quality_for_loss,
)
from ..flow import (
    AttemptResult,
    DevelopmentAssignment,
    ExactOverride,
    Flow,
    FlowError,
    FlowStorageError,
    FlowStore,
    FlowWorkspace,
    OpeningTag,
    PolicyMoveAttempt,
    MoveRule,
    Structure,
    normalized_position_key,
)
from ..flow.position import replay_san
from ..opening import (
    OpeningContext,
    OpeningHistoryEntry,
    OpeningMatch,
    OpeningMoveProvenance,
    OpeningDataError,
    OpeningSourceError,
)
from ..policy import (
    MoveAction,
    StartingPieceRef,
    condition_to_data,
    parse_condition,
)
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
    AnalysisProfileSnapshot,
    AnalysisRunSnapshot,
    AnalysisSettingsSnapshot,
    AvailableCommandSnapshot,
    AttemptSnapshot,
    BookContinuationSnapshot,
    BookDetailsAttachment,
    BookHistoryAttachment,
    BookMoveSnapshot,
    ChatAttachment,
    ChatMessageSnapshot,
    CommandListAttachment,
    CommandResponse,
    ConditionSnapshot,
    DefenseListAttachment,
    DecisionSnapshot,
    DecisionExplanationAttachment,
    DecisionTraceAttachment,
    DevelopmentOrderRequest,
    DevelopmentRuleDraftRequest,
    DevelopmentRuleSnapshot,
    DevelopmentRuleValidationResponse,
    EngineHealth,
    EngineMoveSnapshot,
    EngineReviewSnapshot,
    EvaluationSnapshot,
    FlowSnapshot,
    FlowSourceResponse,
    GameOverSnapshot,
    HighlightMoveEffect,
    LegalMoveSnapshot,
    NavigationSnapshot,
    OpeningContextAttachment,
    OpeningContextSnapshot,
    OpeningHistoryItemSnapshot,
    OpeningListAttachment,
    OpeningMatchSnapshot,
    OpeningTagSnapshot,
    OverrideRuntimeSnapshot,
    PolicyReferenceSnapshot,
    PolicyOrderRequest,
    PositionAnalysisAttachment,
    PositionDetailsAttachment,
    PositionSnapshot,
    PositionAnalysisSnapshot,
    RuleDetailsAttachment,
    RuleGroupsSnapshot,
    RuleListAttachment,
    RuleRuntimeSnapshot,
    StartingPieceSnapshot,
    StructureOrderRequest,
    StructureRuntimeSnapshot,
    UpdateOverrideRequest,
    UpdateRuleRequest,
    UpdateStructureRequest,
    ValidationErrorAttachment,
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
    chat: list[ChatMessageSnapshot] = field(default_factory=list)
    next_activity_id: int = 1
    next_message_id: int = 1
    next_sequence: int = 1
    analysis_profile_id: str = DEFAULT_ANALYSIS_PROFILE.id


class EvaluationCache:
    def __init__(
        self,
        engine: ChessEngineService | None,
        *,
        engine_identity: str = "engine-off",
    ) -> None:
        self.engine = engine
        self.engine_identity = engine_identity
        self._cache: dict[tuple[str, str, str], tuple[AnalysedMove, ...]] = {}
        self._lock = asyncio.Lock()
        self._status = "off" if engine is None else "configured"
        self.last_error: str | None = None
        self.last_engine_name: str | None = None

    @property
    def health(self) -> EngineHealth:
        return EngineHealth(status=self._status)  # type: ignore[arg-type]

    async def analyse(self, board: chess.Board, profile: EngineProfile) -> AnalysedMove:
        return (await self.analyse_lines(board, count=1, profile=profile))[0]

    async def analyse_lines(
        self, board: chess.Board, *, count: int, profile: EngineProfile
    ) -> tuple[AnalysedMove, ...]:
        if self.engine is None:
            raise RuntimeError("Engine analysis is disabled.")
        legal_count = board.legal_moves.count()
        if legal_count == 0:
            raise RuntimeError("The position has no legal moves to analyse.")
        requested = min(count, legal_count)
        key = (normalized_position_key(board), profile.id, self.engine_identity)
        async with self._lock:
            cached = self._cache.get(key, ())
            if len(cached) >= requested:
                return cached[:requested]
            try:
                lines = await self.engine.analyse(
                    board, count=requested, profile=profile
                )
                if not lines:
                    raise RuntimeError("Engine returned no analysis rows.")
            except EngineError as error:
                self._status = "error"
                self.last_error = str(error)
                raise
            self._cache[key] = lines
            self._status = "ready"
            self.last_error = None
            self.last_engine_name = lines[0].engine_name
            return lines


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
        self.commands = CommandRegistry()
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

    async def submit_chat(self, session_id: str, text: str) -> CommandResponse:
        session = self._session(session_id)
        async with session.lock:
            self._append_chat(session, "user", text.strip())
            try:
                invocation = self.commands.parse_chat(text)
                outcome = await self._execute_locked(session, invocation)
            except FlowStorageError:
                raise
            except (CommandFailure, WebApiError, FlowError, ValueError) as error:
                code = (
                    error.code.value
                    if isinstance(error, WebApiError)
                    else (
                        error.code
                        if isinstance(error, CommandFailure)
                        else ApiErrorCode.INVALID_REQUEST.value
                    )
                )
                details = (
                    error.details
                    if isinstance(error, (WebApiError, CommandFailure))
                    else {}
                )
                self._append_chat(
                    session,
                    "assistant",
                    str(error),
                    ValidationErrorAttachment(code=code, details=details),
                )
                return CommandResponse(workspace=await self._snapshot(session))
            self._record_outcome(session, outcome, role="assistant")
            return CommandResponse(
                workspace=await self._snapshot(session),
                effects=_effect_snapshots(outcome.effects),
            )

    async def execute_command(
        self, session_id: str, invocation: CommandInvocation
    ) -> CommandResponse:
        session = self._session(session_id)
        async with session.lock:
            outcome = await self._execute_locked(session, invocation)
            self._record_outcome(
                session,
                outcome,
                role="tool" if invocation.source == "tool" else "assistant",
            )
            return CommandResponse(
                workspace=await self._snapshot(session),
                effects=_effect_snapshots(outcome.effects),
            )

    async def _execute_locked(
        self, session: DevelopmentSession, invocation: CommandInvocation
    ) -> CommandOutcome:
        workspace = session.workspace
        availability = self._command_availability(workspace)
        if not self.commands.is_available(invocation.command, availability):
            definition = self.commands.definition(invocation.command)
            raise CommandFailure(
                "COMMAND_UNAVAILABLE",
                f"{definition.slash} is not available in the current position.",
            )

        command = invocation.command
        if command is CommandId.PLAY_MOVE:
            if not invocation.move or invocation.notation not in {"san", "uci"}:
                raise CommandFailure(
                    "INVALID_COMMAND", "play_move requires a SAN or UCI move."
                )
            if invocation.notation == "uci":
                move = self._legal_move(workspace.board, invocation.move)
            else:
                try:
                    move = workspace.board.parse_san(invocation.move.strip())
                except ValueError as error:
                    raise CommandFailure(
                        "INVALID_MOVE",
                        f"{invocation.move.strip()!r} is not legal SAN in the current position.",
                    ) from error
            await self._submit_legal_move(
                session, move, typed=invocation.source == "chat"
            )
            return CommandOutcome()

        if command is CommandId.RETRY_POLICY:
            side = workspace.author.flow.side.capitalize()
            workspace.retry_policy_move()
            self._append_activity(
                session,
                "info",
                f"Retry {side}'s move",
                "The position was restored. Try again or ask for a hint.",
            )
            return CommandOutcome()

        if command is CommandId.CONTINUE_POLICY:
            attempt = workspace.attempt
            if attempt is None or attempt.result is not AttemptResult.MISMATCH:
                raise CommandFailure(
                    "COMMAND_UNAVAILABLE",
                    "Only a mismatching policy move can continue with the selected rule.",
                )
            expected = attempt.decision.move_san or "the selected move"
            workspace.continue_with_policy_move()
            self._append_activity(
                session,
                "success",
                f"Continued with {expected}",
                attempt.decision.note or "The selected policy rule was kept unchanged.",
                _latest_opening_attachment(workspace),
            )
            return CommandOutcome()

        if command is CommandId.ADD_RULE_FOR_MISMATCH:
            attempt = workspace.attempt
            if attempt is None or attempt.result is not AttemptResult.MISMATCH:
                raise CommandFailure(
                    "COMMAND_UNAVAILABLE",
                    "A rule can only be added for a pending mismatching move.",
                )
            played_san = attempt.selected_move.san
            override = workspace.allow_mismatch_as_override()
            self._append_activity(
                session,
                "success",
                f"Added rule {override.id}",
                f"{played_san} is now the exact-position policy move here and was accepted.",
                _latest_opening_attachment(workspace),
            )
            return CommandOutcome()

        if command is CommandId.NEXT_OPPONENT:
            await self._play_next_opponent_locked(session)
            return CommandOutcome()

        if command is CommandId.GO_BACK:
            workspace.go_back_to_previous_decision()
            self._append_activity(
                session,
                "info",
                "Moved back",
                "Replayed the retained line and restored policy lifecycle state.",
            )
            return CommandOutcome()

        if command is CommandId.RESTART:
            self._restart_locked(session)
            return CommandOutcome()

        if command is CommandId.HINT_POLICY_MOVE:
            decision = _current_decision(workspace, _phase(workspace))
            if decision is None or decision.move is None:
                raise CommandFailure(
                    "COMMAND_UNAVAILABLE", "No policy move is available to highlight."
                )
            return CommandOutcome(
                effects=(ClientEffect("highlight-move", decision.move.uci()),)
            )

        if command is CommandId.ANALYSE_POSITION:
            analysis = await self._analyse_position_locked(session)
            self._append_activity(
                session,
                "info",
                "Position analysis completed",
                "Local book and Stockfish candidates are ready.",
            )
            return CommandOutcome(
                reply=AssistantReply(
                    "Here are the current book and engine candidates.",
                    "position-analysis",
                    PositionAnalysisAttachment(analysis=analysis),
                )
            )

        decision = _current_decision(workspace, _phase(workspace))
        groups = _rule_groups(workspace, decision)
        if command is CommandId.EXPLAIN_DECISION:
            attachment = _decision_explanation(decision)
            return CommandOutcome(
                reply=AssistantReply(
                    _decision_explanation_text(attachment),
                    "decision-explanation",
                    attachment,
                )
            )
        if command is CommandId.INSPECT_RULE:
            if not invocation.rule_id:
                raise CommandFailure("INVALID_COMMAND", "Usage: /rule <rule-id>.")
            item = _find_policy_item(groups, invocation.rule_id)
            if item is None:
                raise CommandFailure(
                    "UNKNOWN_RULE", f"Unknown rule or override {invocation.rule_id!r}."
                )
            return CommandOutcome(
                reply=AssistantReply(
                    f"Current details for {invocation.rule_id}.",
                    "rule-details",
                    RuleDetailsAttachment(
                        rule=item,
                        provenance=["policy-runtime", "user-authored-note"],
                    ),
                )
            )
        if command is CommandId.LIST_RULES:
            return CommandOutcome(
                reply=AssistantReply(
                    "Rules grouped by their current policy status.",
                    "rule-list",
                    RuleListAttachment(groups=groups),
                )
            )
        if command is CommandId.TRACE_DECISION:
            if decision is None:
                raise CommandFailure(
                    "COMMAND_UNAVAILABLE", "No policy decision trace is available."
                )
            return CommandOutcome(
                reply=AssistantReply(
                    "Deterministic policy trace.",
                    "decision-trace",
                    DecisionTraceAttachment(entries=list(decision.trace)),
                )
            )
        if command is CommandId.INSPECT_POSITION:
            return CommandOutcome(
                reply=AssistantReply(
                    "Current position details.",
                    "position-details",
                    _position_details(workspace),
                )
            )
        if command is CommandId.INSPECT_OPENING:
            context = workspace.get_current_opening_context()
            return CommandOutcome(
                reply=AssistantReply(
                    _opening_context_text(context),
                    "opening-context",
                    OpeningContextAttachment(
                        entry=(
                            _opening_history_item(workspace.opening_history[-1])
                            if workspace.opening_history
                            else None
                        ),
                        context=_opening_context_snapshot(context),
                        presentation="current",
                    ),
                )
            )
        if command is CommandId.LIST_OPENINGS:
            context = workspace.get_current_opening_context()
            return CommandOutcome(
                reply=AssistantReply(
                    "Named opening matches for the current normalized position.",
                    "opening-list",
                    OpeningListAttachment(
                        primary_match=(
                            _opening_match_snapshot(context.primary_match)
                            if context.primary_match
                            else None
                        ),
                        matches=[
                            _opening_match_snapshot(match)
                            for match in context.current_matches
                        ],
                    ),
                )
            )
        if command is CommandId.LIST_DEFENSES:
            return CommandOutcome(
                reply=AssistantReply(
                    "Entered defenses and book defenses still reachable.",
                    "defense-list",
                    DefenseListAttachment(
                        reachable=list(workspace.get_reachable_defenses()),
                        entered=_entered_defenses(workspace),
                    ),
                )
            )
        if command is CommandId.INSPECT_BOOK:
            context = workspace.get_current_opening_context()
            return CommandOutcome(
                reply=AssistantReply(
                    "Opening-index alignment and current continuations.",
                    "book-details",
                    BookDetailsAttachment(
                        played_move_in_book=context.played_move_in_book,
                        continuations=[
                            _book_continuation_snapshot(item)
                            for item in workspace.get_book_continuations()
                        ],
                    ),
                )
            )
        if command is CommandId.INSPECT_BOOK_HISTORY:
            transition = workspace.find_book_policy_transition()
            return CommandOutcome(
                reply=AssistantReply(
                    "Opening transitions along the current line.",
                    "book-history",
                    BookHistoryAttachment(
                        entries=[
                            _opening_history_item(entry)
                            for entry in workspace.get_opening_history()
                        ],
                        first_policy_without_book_ply=(
                            transition.ply if transition else None
                        ),
                    ),
                )
            )
        if command is CommandId.LIST_COMMANDS:
            return CommandOutcome(
                reply=AssistantReply(
                    "Commands available in the current position.",
                    "command-list",
                    CommandListAttachment(
                        commands=self._available_command_snapshots(workspace)
                    ),
                )
            )
        raise CommandFailure("UNKNOWN_COMMAND", f"Unsupported command {command.value}.")

    async def _play_next_opponent_locked(self, session: DevelopmentSession) -> None:
        workspace = session.workspace
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
        workspace.submit_opponent_uci(
            move.uci(), move_source=OpeningMoveProvenance.ENGINE
        )
        self._append_activity(
            session,
            "move",
            f"{color} played {san}",
            "The engine selected this reply after you chose Next.",
            _latest_opening_attachment(workspace),
        )
        if workspace.outcome is None:
            workspace.begin_policy_turn()

    async def _analyse_position_locked(
        self, session: DevelopmentSession
    ) -> PositionAnalysisSnapshot:
        workspace = session.workspace
        board = workspace.board.copy(stack=False)
        profile = _analysis_profile(session.analysis_profile_id)
        try:
            book_moves = await self._book_moves(workspace, board)
            engine_lines = await self.evaluations.analyse_lines(
                board, count=4, profile=profile
            )
        except OpeningSourceError as error:
            raise WebApiError(
                ApiErrorCode.INVALID_REQUEST,
                f"The local opening book could not analyse this position: {error}",
                status_code=500,
            ) from error
        except (EngineError, RuntimeError) as error:
            raise WebApiError(
                ApiErrorCode.ENGINE_ERROR,
                f"The chess engine could not analyse this position: {error}",
                status_code=502,
            ) from error
        return PositionAnalysisSnapshot(
            book_moves=book_moves,
            engine_moves=[
                EngineMoveSnapshot(
                    uci=line.uci,
                    san=line.san,
                    evaluation_cp=line.evaluation_cp,
                    mate_in=line.mate_in,
                    principal_variation=list(line.principal_variation),
                )
                for line in engine_lines
            ],
            engine=_analysis_run(engine_lines[0], lines=len(engine_lines)),
        )

    def _command_availability(self, workspace: FlowWorkspace) -> CommandAvailability:
        phase = _phase(workspace)
        decision = _current_decision(workspace, phase)
        return CommandAvailability(
            phase=phase,  # type: ignore[arg-type]
            engine_available=self.evaluations.engine is not None,
            has_decision=decision is not None,
            has_decision_move=decision is not None and decision.move is not None,
            mismatch=(
                workspace.attempt is not None
                and workspace.attempt.result is AttemptResult.MISMATCH
            ),
            can_back=workspace.can_go_back,
            can_restart=workspace.can_restart,
            has_rules=bool(
                workspace.author.flow.policy_items or workspace.author.flow.overrides
            ),
        )

    def _available_command_snapshots(
        self, workspace: FlowWorkspace
    ) -> list[AvailableCommandSnapshot]:
        return [
            AvailableCommandSnapshot(
                id=item.id.value,
                slash=item.slash,
                usage=item.usage,
                description=item.description,
                arguments=[
                    {
                        "name": argument.name,
                        "description": argument.description,
                        "required": argument.required,
                    }
                    for argument in item.arguments
                ],
            )
            for item in self.commands.available(self._command_availability(workspace))
        ]

    def _record_outcome(
        self,
        session: DevelopmentSession,
        outcome: CommandOutcome,
        *,
        role: Literal["assistant", "tool"],
    ) -> None:
        for activity in outcome.activity:
            self._append_activity(
                session,
                activity.kind,
                activity.title,
                activity.message,
            )
        if outcome.reply is not None:
            self._append_chat(
                session,
                role,
                outcome.reply.text,
                cast(ChatAttachment | None, outcome.reply.attachment),
            )

    def _restart_locked(self, session: DevelopmentSession) -> None:
        session.workspace.restart()
        session.activity.clear()
        session.next_activity_id = 1
        self._append_activity(
            session,
            "info",
            "Line restarted",
            "Returned to the beginning without changing saved rules or branches.",
        )

    async def submit_move(self, session_id: str, uci: str) -> WorkspaceSnapshot:
        return await self._compat_command(
            session_id,
            CommandInvocation(CommandId.PLAY_MOVE, "ui", notation="uci", move=uci),
        )

    async def submit_san_move(self, session_id: str, san: str) -> WorkspaceSnapshot:
        return await self._compat_command(
            session_id,
            CommandInvocation(CommandId.PLAY_MOVE, "ui", notation="san", move=san),
        )

    async def retry_policy(self, session_id: str) -> WorkspaceSnapshot:
        return await self._compat_command(
            session_id, CommandInvocation(CommandId.RETRY_POLICY, "ui")
        )

    async def continue_policy(self, session_id: str) -> WorkspaceSnapshot:
        return await self._compat_command(
            session_id, CommandInvocation(CommandId.CONTINUE_POLICY, "ui")
        )

    async def add_rule_for_mismatch(self, session_id: str) -> WorkspaceSnapshot:
        return await self._compat_command(
            session_id,
            CommandInvocation(CommandId.ADD_RULE_FOR_MISMATCH, "ui"),
        )

    async def play_next_opponent(self, session_id: str) -> WorkspaceSnapshot:
        if self.evaluations.engine is None:
            raise WebApiError(
                ApiErrorCode.ENGINE_ERROR,
                "The opponent's next move requires a configured chess engine.",
                status_code=503,
            )
        return await self._compat_command(
            session_id, CommandInvocation(CommandId.NEXT_OPPONENT, "ui")
        )

    async def analyse_position(self, session_id: str) -> WorkspaceSnapshot:
        if self.evaluations.engine is None:
            raise WebApiError(
                ApiErrorCode.ENGINE_ERROR,
                "Position analysis requires a configured chess engine.",
                status_code=503,
            )
        return await self._compat_command(
            session_id, CommandInvocation(CommandId.ANALYSE_POSITION, "ui")
        )

    async def update_analysis_profile(
        self, session_id: str, profile_id: str
    ) -> WorkspaceSnapshot:
        session = self._session(session_id)
        profile = _analysis_profile(profile_id)
        async with session.lock:
            session.analysis_profile_id = profile.id
            self._append_activity(
                session,
                "info",
                f"Analysis set to {profile.label}",
                f"{profile.cost_description} No API fee is charged.",
            )
            return await self._snapshot(session)

    async def _book_moves(
        self, workspace: FlowWorkspace, board: chess.Board
    ) -> list[BookMoveSnapshot]:
        suggestions: list[BookMoveSnapshot] = []
        seen: set[str] = set()
        for move in workspace.opening_classifier.book_continuations(board):
            suggestions.append(
                BookMoveSnapshot(
                    uci=move.uci,
                    san=move.san,
                    source="opening-index",
                    opening_names=list(move.opening_names),
                    defense_names=list(move.defense_names),
                )
            )
            seen.add(move.uci)

        if workspace.attempt is None and workspace.is_policy_turn:
            decision = workspace.policy_turn or workspace.begin_policy_turn()
            if decision.decision.move is not None:
                move = decision.decision.move
                existing_index = next(
                    (
                        index
                        for index, item in enumerate(suggestions)
                        if item.uci == move.uci()
                    ),
                    None,
                )
                if existing_index is not None:
                    existing = suggestions.pop(existing_index)
                    suggestions.insert(
                        0,
                        existing.model_copy(update={"source": "book-and-policy"}),
                    )
                else:
                    suggestions.append(
                        BookMoveSnapshot(
                            uci=move.uci(),
                            san=decision.decision.move_san or board.san(move),
                            source="policy",
                        )
                    )
                    seen.add(move.uci())

        visible_history = tuple(workspace.history)
        if workspace.attempt is not None:
            visible_history += (workspace.attempt.selected_move.san,)
        for reply in workspace.author.flow.opponent_replies:
            if reply.after_san != visible_history:
                continue
            try:
                move = board.parse_san(reply.move_san)
            except ValueError:
                continue
            if move.uci() in seen:
                continue
            suggestions.append(
                BookMoveSnapshot(
                    uci=move.uci(),
                    san=board.san(move),
                    source="opponent-branch",
                )
            )
            seen.add(move.uci())
        return suggestions[:6]

    async def update_rule(
        self, session_id: str, rule_id: str, payload: UpdateRuleRequest
    ) -> WorkspaceSnapshot:
        session = self._session(session_id)
        async with session.lock:
            workspace = session.workspace
            opening_ply_before = len(workspace.opening_history)
            existing_rule = next(
                (
                    rule
                    for rule in (
                        *workspace.author.flow.responses,
                        *workspace.author.flow.continuations,
                    )
                    if rule.id == rule_id
                ),
                None,
            )
            if existing_rule is None:
                raise WebApiError(
                    ApiErrorCode.INVALID_REQUEST, f"Unknown rule id {rule_id!r}."
                )
            try:
                replacement = MoveRule(
                    id=rule_id,
                    note=_clean_note(payload.note),
                    move=MoveAction(
                        StartingPieceRef.parse(payload.move.piece).original_piece_id,
                        payload.move.to,
                    ),
                    structures=tuple(payload.structures),
                    unlock_when=(
                        parse_condition(payload.unlock_when, context="unlockWhen")
                        if payload.unlock_when is not None
                        else None
                    ),
                    when=(
                        parse_condition(payload.when, context="when")
                        if payload.when is not None
                        else None
                    ),
                    expire_when=(
                        parse_condition(payload.expire_when, context="expireWhen")
                        if payload.expire_when is not None
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
                (
                    _latest_opening_attachment(workspace)
                    if len(workspace.opening_history) > opening_ply_before
                    else None
                ),
            )
            return await self._snapshot(session)

    async def validate_development_rule(
        self, session_id: str, payload: DevelopmentRuleDraftRequest
    ) -> DevelopmentRuleValidationResponse:
        session = self._session(session_id)
        async with session.lock:
            workspace = session.workspace
            try:
                rule, candidate = _development_candidate(workspace, payload)
                source = workspace.author.store.encode(candidate)
                reparsed = workspace.author.store.decode(
                    source, context="development rule preview"
                )
                history = (
                    workspace.attempt.history_before
                    if workspace.attempt is not None
                    else tuple(workspace.history)
                )
                from ..policy.runtime import PolicyRuntime

                PolicyRuntime.replay(reparsed, history)
            except (TypeError, ValueError, FlowError) as error:
                return DevelopmentRuleValidationResponse(
                    valid=False,
                    rule_id=payload.id
                    or _development_rule_id(payload.piece, tuple(payload.structures)),
                    piece=payload.piece,
                    target=payload.target,
                    order=0,
                    errors=[str(error)],
                )
            return DevelopmentRuleValidationResponse(
                valid=True,
                rule_id=rule.id,
                piece=str(rule.piece),
                target=rule.target,
                order=(
                    next(
                        index
                        for index, item in enumerate(
                            workspace.author.flow.development, start=1
                        )
                        if item.id == rule.id
                    )
                    if any(
                        item.id == rule.id for item in workspace.author.flow.development
                    )
                    else len(workspace.author.flow.development) + 1
                ),
            )

    async def apply_development_rule(
        self, session_id: str, payload: DevelopmentRuleDraftRequest
    ) -> WorkspaceSnapshot:
        session = self._session(session_id)
        async with session.lock:
            workspace = session.workspace
            try:
                rule, _candidate = _development_candidate(workspace, payload)
                workspace.save_development_rule(rule)
            except (TypeError, ValueError, FlowError) as error:
                if isinstance(error, FlowError):
                    raise
                raise WebApiError(
                    ApiErrorCode.FLOW_VALIDATION_ERROR,
                    str(error),
                    status_code=422,
                ) from error
            self._append_activity(
                session,
                "info",
                f"Applied development rule {rule.id}",
                "The flow was validated, saved atomically, and replayed.",
            )
            return await self._snapshot(session)

    async def delete_development_rule(
        self, session_id: str, rule_id: str
    ) -> WorkspaceSnapshot:
        session = self._session(session_id)
        async with session.lock:
            try:
                session.workspace.delete_development_rule(rule_id)
            except (ValueError, FlowError) as error:
                if isinstance(error, FlowError):
                    raise
                raise WebApiError(
                    ApiErrorCode.FLOW_VALIDATION_ERROR,
                    str(error),
                    status_code=422,
                ) from error
            self._append_activity(
                session,
                "info",
                f"Deleted development rule {rule_id}",
                "The flow was validated, saved atomically, and replayed.",
            )
            return await self._snapshot(session)

    async def reorder_development_rules(
        self, session_id: str, payload: DevelopmentOrderRequest
    ) -> WorkspaceSnapshot:
        session = self._session(session_id)
        async with session.lock:
            try:
                session.workspace.reorder_development_rules(tuple(payload.rule_ids))
            except (ValueError, FlowError) as error:
                if isinstance(error, FlowError):
                    raise
                raise WebApiError(
                    ApiErrorCode.FLOW_VALIDATION_ERROR,
                    str(error),
                    status_code=422,
                ) from error
            self._append_activity(
                session,
                "info",
                "Updated development order",
                "Authored order was saved atomically and replayed.",
            )
            return await self._snapshot(session)

    async def reorder_policy_section(
        self,
        session_id: str,
        section: Literal["response", "development", "continuation"],
        payload: PolicyOrderRequest,
    ) -> WorkspaceSnapshot:
        session = self._session(session_id)
        async with session.lock:
            try:
                session.workspace.reorder_policy_section(
                    section, tuple(payload.item_ids)
                )
            except (ValueError, FlowError) as error:
                if isinstance(error, FlowError):
                    raise
                raise WebApiError(
                    ApiErrorCode.FLOW_VALIDATION_ERROR,
                    str(error),
                    status_code=422,
                ) from error
            self._append_activity(
                session,
                "info",
                f"Updated {section} order",
                "Authored policy order was saved atomically and replayed.",
            )
            return await self._snapshot(session)

    async def update_structure(
        self,
        session_id: str,
        structure_id: str,
        payload: UpdateStructureRequest,
    ) -> WorkspaceSnapshot:
        session = self._session(session_id)
        async with session.lock:
            workspace = session.workspace
            try:
                replacement = Structure(
                    id=structure_id,
                    name=payload.name.strip(),
                    available_when=parse_condition(
                        payload.available_when,
                        context="availableWhen",
                    ),
                    selected_when=parse_condition(
                        payload.selected_when,
                        context="selectedWhen",
                    ),
                    note=_clean_note(payload.note),
                )
                workspace.update_structure(replacement)
            except (TypeError, ValueError, FlowError) as error:
                if isinstance(error, FlowError):
                    raise
                raise WebApiError(
                    ApiErrorCode.FLOW_VALIDATION_ERROR,
                    str(error),
                    status_code=422,
                ) from error
            self._append_activity(
                session,
                "info",
                f"Updated structure {structure_id}",
                "The complete flow was validated, saved, and replayed.",
            )
            return await self._snapshot(session)

    async def reorder_structures(
        self,
        session_id: str,
        payload: StructureOrderRequest,
    ) -> WorkspaceSnapshot:
        session = self._session(session_id)
        async with session.lock:
            try:
                session.workspace.reorder_structures(tuple(payload.structure_ids))
            except (ValueError, FlowError) as error:
                if isinstance(error, FlowError):
                    raise
                raise WebApiError(
                    ApiErrorCode.FLOW_VALIDATION_ERROR,
                    str(error),
                    status_code=422,
                ) from error
            self._append_activity(
                session,
                "info",
                "Updated structure order",
                "Structure selection order was saved and replayed.",
            )
            return await self._snapshot(session)

    async def update_override(
        self, session_id: str, override_id: str, payload: UpdateOverrideRequest
    ) -> WorkspaceSnapshot:
        session = self._session(session_id)
        async with session.lock:
            workspace = session.workspace
            opening_ply_before = len(workspace.opening_history)
            if all(item.id != override_id for item in workspace.author.flow.overrides):
                raise WebApiError(
                    ApiErrorCode.INVALID_REQUEST,
                    f"Unknown override id {override_id!r}.",
                )
            try:
                replacement = ExactOverride(
                    id=override_id,
                    after_san=tuple(payload.after_san),
                    note=_clean_note(payload.note),
                    move=MoveAction(
                        StartingPieceRef.parse(payload.move.piece).original_piece_id,
                        payload.move.to,
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
                (
                    _latest_opening_attachment(workspace)
                    if len(workspace.opening_history) > opening_ply_before
                    else None
                ),
            )
            return await self._snapshot(session)

    async def add_opening_tag(
        self, session_id: str, record_id: int
    ) -> WorkspaceSnapshot:
        session = self._session(session_id)
        async with session.lock:
            workspace = session.workspace
            match = self._opening_match(workspace, record_id)
            tag = OpeningTag(match.eco, match.name)
            workspace.add_opening_tag(tag)
            self._append_activity(
                session,
                "success",
                f"Labeled flow {match.name}",
                f"Saved {match.eco} as durable flow metadata.",
            )
            return await self._snapshot(session)

    async def remove_opening_tag(
        self, session_id: str, record_id: int
    ) -> WorkspaceSnapshot:
        session = self._session(session_id)
        async with session.lock:
            workspace = session.workspace
            match = self._opening_match(workspace, record_id)
            tag = OpeningTag(match.eco, match.name)
            workspace.remove_opening_tag(tag)
            self._append_activity(
                session,
                "info",
                f"Removed flow label {match.name}",
                f"Removed {match.eco} from the durable flow metadata.",
            )
            return await self._snapshot(session)

    @staticmethod
    def _opening_match(workspace: FlowWorkspace, record_id: int) -> OpeningMatch:
        try:
            return workspace.opening_classifier.match_by_id(record_id)
        except OpeningDataError as error:
            raise WebApiError(
                ApiErrorCode.INVALID_REQUEST,
                f"Unknown opening record id {record_id}.",
            ) from error

    async def go_back(self, session_id: str) -> WorkspaceSnapshot:
        return await self._compat_command(
            session_id, CommandInvocation(CommandId.GO_BACK, "ui")
        )

    async def restart(self, session_id: str) -> WorkspaceSnapshot:
        session = self._session(session_id)
        async with session.lock:
            self._restart_locked(session)
            return await self._snapshot(session)

    async def _compat_command(
        self, session_id: str, invocation: CommandInvocation
    ) -> WorkspaceSnapshot:
        try:
            return (await self.execute_command(session_id, invocation)).workspace
        except CommandFailure as error:
            raise WebApiError(
                ApiErrorCode.INVALID_REQUEST,
                str(error),
                details=error.details,
            ) from error

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
            if attempt.result is AttemptResult.CORRECT:
                workspace.complete_correct_move()
            self._record_policy_attempt(session, attempt)
        else:
            source = OpeningMoveProvenance.MANUAL
            if not typed:
                visible_history = tuple(workspace.history)
                recorded = any(
                    reply.after_san == visible_history and reply.move_san == san
                    for reply in workspace.author.flow.opponent_replies
                )
                if recorded:
                    source = OpeningMoveProvenance.RECORDED_BRANCH
                elif workspace.opening_classifier.compare_move_to_book(
                    workspace.board, move
                ):
                    source = OpeningMoveProvenance.BOOK
            workspace.submit_opponent_uci(move.uci(), move_source=source)
            reason = (
                "This reply was entered in the move composer."
                if typed
                else "This is the selected opponent reply for the current line."
            )
            self._append_activity(
                session,
                "move",
                f"{color} played {san}",
                reason,
                _latest_opening_attachment(workspace),
            )
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
            (
                _latest_opening_attachment(session.workspace)
                if attempt.result is AttemptResult.CORRECT
                else None
            ),
        )

    async def _snapshot(self, session: DevelopmentSession) -> WorkspaceSnapshot:
        workspace = session.workspace
        phase = _phase(workspace)
        decision = _current_decision(workspace, phase)
        attempt = await self._attempt(session)
        evaluation, evaluation_error = await self._evaluation(session)
        errors = []
        if evaluation_error:
            from .api_models import ApiErrorItem

            errors.append(
                ApiErrorItem(code=ApiErrorCode.ENGINE_ERROR, message=evaluation_error)
            )
        visible_history = list(workspace.history)
        if workspace.attempt is not None:
            visible_history.append(workspace.attempt.selected_move.san)
        rule_groups = _rule_groups(workspace, decision)
        return WorkspaceSnapshot(
            session_id=session.id,
            phase=phase,  # type: ignore[arg-type]
            flow=FlowSnapshot(
                name=workspace.author.flow.name,
                version=workspace.author.flow.version,
                path=self._display_path(session.flow_path),
                side=workspace.author.flow.side,
                opening_tags=[
                    OpeningTagSnapshot(
                        record_id=(
                            match.record_id
                            if (
                                match := workspace.opening_classifier.match_for_identity(
                                    tag.eco, tag.name
                                )
                            )
                            is not None
                            else None
                        ),
                        eco=tag.eco,
                        name=tag.name,
                    )
                    for tag in workspace.author.flow.opening_tags
                ],
                warnings=list(workspace.author.store.warnings(workspace.author.flow)),
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
            rules=rule_groups,
            starting_pieces=_starting_piece_snapshots(workspace, rule_groups),
            opening=_opening_context_snapshot(workspace.get_current_opening_context()),
            opening_history=[
                _opening_history_item(entry)
                for entry in workspace.get_opening_history()
            ],
            evaluation=evaluation,
            analysis_settings=self._analysis_settings(session),
            navigation=NavigationSnapshot(
                can_back=workspace.can_go_back, can_restart=workspace.can_restart
            ),
            activity=list(session.activity),
            chat=list(session.chat),
            available_commands=self._available_command_snapshots(workspace),
            errors=errors,
        )

    async def _evaluation(
        self, session: DevelopmentSession
    ) -> tuple[EvaluationSnapshot, str | None]:
        workspace = session.workspace
        profile = _analysis_profile(session.analysis_profile_id)
        if self.evaluations.engine is None:
            return EvaluationSnapshot(status="engine-off"), None
        outcome = workspace.outcome
        try:
            if outcome is not None:
                current = _terminal_analysis(outcome)
            else:
                current = await self.evaluations.analyse(workspace.board, profile)
            previous_board: chess.Board | None = None
            if workspace.attempt is not None:
                previous_board = workspace.attempt.board_before
            elif workspace.history:
                previous_board = replay_san(
                    workspace.author.flow.start_fen, tuple(workspace.history[:-1])
                )
            previous = (
                await self.evaluations.analyse(previous_board, profile)
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
                analysis=(
                    _analysis_run(current) if current.engine_name is not None else None
                ),
            ),
            None,
        )

    def _analysis_settings(
        self, session: DevelopmentSession
    ) -> AnalysisSettingsSnapshot:
        return AnalysisSettingsSnapshot(
            status=self.evaluations.health.status,
            engine_name=self.evaluations.last_engine_name
            or _configured_engine_name(self.evaluations.engine_identity),
            selected_profile_id=session.analysis_profile_id,
            profiles=[
                AnalysisProfileSnapshot(
                    id=profile.id,
                    label=profile.label,
                    depth=cast(int, profile.depth),
                    cost_label=profile.cost_label,
                    cost_description=profile.cost_description,
                )
                for profile in ANALYSIS_PROFILES
            ],
        )

    async def _attempt(self, session: DevelopmentSession) -> AttemptSnapshot | None:
        workspace = session.workspace
        attempt = workspace.attempt
        if attempt is None:
            return None
        review = (
            await self._engine_review(session)
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

    async def _engine_review(self, session: DevelopmentSession) -> EngineReviewSnapshot:
        workspace = session.workspace
        profile = _analysis_profile(session.analysis_profile_id)
        if self.evaluations.engine is None:
            return EngineReviewSnapshot(status="engine-off")
        attempt = workspace.attempt
        assert attempt is not None
        try:
            before = await self.evaluations.analyse(attempt.board_before, profile)
            after = (
                _terminal_analysis(workspace.outcome)
                if workspace.outcome
                else await self.evaluations.analyse(workspace.board, profile)
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
        attachment: OpeningContextAttachment | None = None,
    ) -> None:
        def append(
            event_kind: Literal["info", "move", "success", "warning", "commentary"],
            event_title: str,
            event_message: str,
            event_attachment: OpeningContextAttachment | None = None,
        ) -> None:
            session.activity.append(
                ActivitySnapshot(
                    id=session.next_activity_id,
                    sequence=session.next_sequence,
                    kind=event_kind,
                    title=event_title,
                    message=event_message,
                    attachment=event_attachment,
                )
            )
            session.next_activity_id += 1
            session.next_sequence += 1

        append(kind, title, message)
        if attachment is not None:
            append(
                "commentary",
                _opening_commentary_title(attachment),
                _opening_commentary_text(attachment),
                attachment,
            )
        if len(session.activity) > 100:
            del session.activity[:-100]

    @staticmethod
    def _append_chat(
        session: DevelopmentSession,
        role: Literal["user", "assistant", "system", "tool"],
        text: str,
        attachment: ChatAttachment | None = None,
    ) -> None:
        session.chat.append(
            ChatMessageSnapshot(
                id=f"message-{session.next_message_id}",
                sequence=session.next_sequence,
                role=role,
                text=text,
                attachment=attachment,
            )
        )
        session.next_message_id += 1
        session.next_sequence += 1
        if len(session.chat) > 100:
            del session.chat[:-100]

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


def _development_candidate(
    workspace: FlowWorkspace, payload: DevelopmentRuleDraftRequest
) -> tuple[DevelopmentAssignment, Flow]:
    piece = StartingPieceRef.parse(payload.piece)
    ready_when = (
        parse_condition(payload.ready_when, context="readyWhen")
        if payload.ready_when is not None
        else None
    )
    existing = None
    if payload.id is not None:
        existing = next(
            (
                rule
                for rule in workspace.author.flow.development
                if rule.id == payload.id
            ),
            None,
        )
        if existing is None:
            raise ValueError(f"Unknown development rule id {payload.id!r}.")
    else:
        existing = next(
            (
                rule
                for rule in workspace.author.flow.development
                if rule.piece == piece and rule.structures == tuple(payload.structures)
            ),
            None,
        )
    if existing is not None:
        rule = replace(
            existing,
            piece=piece,
            target=payload.target,
            structures=tuple(payload.structures),
            note=_clean_note(payload.note),
            ready_when=ready_when,
        )
        return rule, workspace.author.candidate_with_rule(rule)

    rule = DevelopmentAssignment(
        id=payload.id or _development_rule_id(str(piece), tuple(payload.structures)),
        piece=piece,
        target=payload.target,
        structures=tuple(payload.structures),
        note=_clean_note(payload.note),
        ready_when=ready_when,
    )
    return rule, workspace.author.candidate_with_added_development_rule(rule)


def _development_rule_id(piece: str, structures: tuple[str, ...] = ()) -> str:
    normalized = piece.removeprefix("piece:").replace(":", "-")
    suffix = f"-{'-'.join(structures)}" if structures else ""
    return f"develop-{normalized}{suffix}"


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
        note=decision.note,
        trace=list(decision.trace),
    )


def _policy_reference(
    item: RuleResolution | OverrideResolution,
) -> PolicyReferenceSnapshot:
    if isinstance(item, RuleResolution):
        return PolicyReferenceSnapshot(
            kind="rule",
            id=item.rule.id,
            move_san=item.move_san,
            note=item.rule.note,
            reason=item.reason,
        )
    return PolicyReferenceSnapshot(
        kind="exact-override",
        id=item.override.id,
        move_san=item.move_san,
        note=item.override.note,
        reason=item.reason,
    )


def _decision_explanation(
    decision: PolicyDecision | None,
) -> DecisionExplanationAttachment:
    if decision is None:
        return DecisionExplanationAttachment(
            selected=None,
            condition_reasons=["No controlled-side policy decision is active."],
            provenance=["policy-runtime"],
        )
    selected_rule = next(
        (item for item in decision.rule_resolutions if item.selected), None
    )
    selected_override = next(
        (item for item in decision.override_resolutions if item.selected), None
    )
    selected_item = selected_override or selected_rule
    reasons: list[str] = []
    if selected_rule is not None:
        for condition in (
            selected_rule.unlock,
            selected_rule.live_condition,
            selected_rule.expiration,
        ):
            if condition is not None:
                reasons.append(condition.explanation)
        if selected_rule.rule.note:
            reasons.append(selected_rule.rule.note)
    elif selected_override is not None:
        reasons.append(selected_override.reason)
        if selected_override.override.note:
            reasons.append(selected_override.override.note)
    else:
        reasons.append("No active legal policy action resolved in this position.")
    return DecisionExplanationAttachment(
        selected=_policy_reference(selected_item) if selected_item else None,
        waiting=[
            _policy_reference(item)
            for item in decision.rule_resolutions
            if item.status is EffectiveRuleStatus.WAITING
        ],
        applicable_later=[
            _policy_reference(item)
            for item in decision.rule_resolutions
            if item.status is EffectiveRuleStatus.APPLICABLE
        ],
        unavailable=[
            _policy_reference(item)
            for item in decision.rule_resolutions
            if item.status
            in {
                EffectiveRuleStatus.LOCKED,
                EffectiveRuleStatus.INACTIVE,
                EffectiveRuleStatus.OUT_OF_SCOPE,
            }
        ],
        condition_reasons=reasons,
        provenance=["policy-trace", "condition-evaluator", "user-authored-note"],
    )


def _decision_explanation_text(
    attachment: DecisionExplanationAttachment,
) -> str:
    if attachment.selected is None:
        return "No policy rule or exact override is selected in this position."
    selected = attachment.selected
    return f"Selected {selected.kind} {selected.id} by authored policy order."


def _find_policy_item(
    groups: RuleGroupsSnapshot, item_id: str
) -> RuleRuntimeSnapshot | OverrideRuntimeSnapshot | None:
    items: list[RuleRuntimeSnapshot | OverrideRuntimeSnapshot] = [
        *groups.responses,
        *groups.development,
        *groups.continuations,
        *groups.overrides,
    ]
    if groups.selected is not None:
        items.insert(0, groups.selected)
    return next((item for item in items if item.id == item_id), None)


def _position_details(workspace: FlowWorkspace) -> PositionDetailsAttachment:
    history = list(workspace.history)
    if workspace.attempt is not None:
        history.append(workspace.attempt.selected_move.san)
    return PositionDetailsAttachment(
        fen=workspace.board.fen(en_passant="fen"),
        history_san=history,
        turn="white" if workspace.board.turn == chess.WHITE else "black",
        ply=len(history),
        in_check=workspace.board.is_check(),
        last_move_uci=(
            workspace.controller.interaction.last_move.uci
            if workspace.controller.interaction.last_move
            else None
        ),
        legal_moves=[
            LegalMoveSnapshot(uci=move.uci(), san=workspace.board.san(move))
            for move in workspace.board.legal_moves
        ],
        game_over=_game_over(workspace.outcome),
    )


def _effect_snapshots(
    effects: tuple[ClientEffect, ...],
) -> list[HighlightMoveEffect]:
    return [HighlightMoveEffect(uci=effect.uci) for effect in effects]


def _rule_groups(
    workspace: FlowWorkspace, decision: PolicyDecision | None
) -> RuleGroupsSnapshot:
    if decision is not None:
        order_by_id = {
            item.id: order
            for authored in (
                workspace.author.flow.responses,
                workspace.author.flow.development,
                workspace.author.flow.continuations,
            )
            for order, item in enumerate(authored, start=1)
        }
        rules = [
            _rule_snapshot(item, order_by_id[item.rule.id])
            for item in decision.rule_resolutions
        ]
        overrides = [_override_snapshot(item) for item in decision.override_resolutions]
    else:
        rules = _passive_rule_snapshots(workspace)
        overrides = [
            OverrideRuntimeSnapshot(
                id=item.id,
                after_san=list(item.after_san),
                piece=str(StartingPieceRef.from_original(item.move.piece)),
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
        responses=[item for item in rules if item.section == "response"],
        development=[item for item in rules if item.section == "development"],
        continuations=[item for item in rules if item.section == "continuation"],
        overrides=overrides,
        structures=_structure_snapshots(workspace, decision),
    )


def _starting_piece_snapshots(
    workspace: FlowWorkspace, groups: RuleGroupsSnapshot
) -> list[StartingPieceSnapshot]:
    rule_snapshots: dict[str, RuleRuntimeSnapshot] = {}
    if isinstance(groups.selected, RuleRuntimeSnapshot):
        rule_snapshots[groups.selected.id] = groups.selected
    for group in (groups.responses, groups.development, groups.continuations):
        rule_snapshots.update((item.id, item) for item in group)

    development_rules = workspace.author.flow.development
    order_by_id = {
        rule.id: order for order, rule in enumerate(development_rules, start=1)
    }
    development_by_piece: dict[StartingPieceRef, list[DevelopmentAssignment]] = {}
    for rule in development_rules:
        development_by_piece.setdefault(rule.piece, []).append(rule)
    controlled_color = workspace.author.flow.side
    result: list[StartingPieceSnapshot] = []
    for tracked in sorted(
        workspace.runtime.tracker.pieces,
        key=lambda item: item.id.start_square,
    ):
        if tracked.id.color != controlled_color:
            continue
        try:
            ref = StartingPieceRef.from_original(tracked.id)
        except ValueError:
            continue
        development_snapshots: list[DevelopmentRuleSnapshot] = []
        for development_rule in development_by_piece.get(ref, []):
            runtime = rule_snapshots[development_rule.id]
            status_map = {
                "applicable": "applicable",
                "selected": "selected",
                "waiting": "waiting",
                "inactive": "inactive",
                "locked": "inactive",
                "out-of-scope": "out-of-scope",
                "retired": ("captured" if tracked.captured else "developed"),
            }
            development_snapshots.append(
                DevelopmentRuleSnapshot(
                    id=development_rule.id,
                    target=development_rule.target,
                    order=order_by_id[development_rule.id],
                    structures=list(development_rule.structures),
                    status=status_map[runtime.status],  # type: ignore[arg-type]
                    ready_when=runtime.when,
                    note=development_rule.note,
                    reason=runtime.reason,
                )
            )
        if tracked.captured:
            state = (
                "captured-developed" if tracked.has_moved else "captured-undeveloped"
            )
        else:
            state = "developed" if tracked.has_moved else "undeveloped"
        result.append(
            StartingPieceSnapshot(
                ref=str(ref),
                original_piece_id=str(tracked.id),
                color=ref.color,
                piece_type=ref.piece_type,
                qualifier=ref.qualifier,
                label=ref.label,
                starting_square=tracked.id.start_square,
                current_square=(
                    chess.square_name(tracked.current_square)
                    if tracked.current_square is not None
                    else None
                ),
                state=state,  # type: ignore[arg-type]
                first_moved_ply=tracked.first_moved_ply,
                captured_ply=tracked.captured_ply,
                development_rules=development_snapshots,
            )
        )
    return result


def _rule_snapshot(item: RuleResolution, order: int) -> RuleRuntimeSnapshot:
    if isinstance(item.rule, DevelopmentAssignment):
        unlock_condition = None
        live_condition = item.rule.ready_when
        expire_condition = None
    else:
        unlock_condition = item.rule.unlock_when
        live_condition = item.rule.when
        expire_condition = item.rule.expire_when
    return RuleRuntimeSnapshot(
        id=item.rule.id,
        section=item.section,
        order=order,
        structures=list(item.rule.structures),
        piece=str(StartingPieceRef.from_original(item.rule.move.piece)),
        destination=item.rule.move.to_square,
        move_uci=item.move.uci() if item.move else None,
        move_san=item.move_san,
        legal=item.legal,
        lifecycle=item.lifecycle.value,
        status=item.status.value,
        selected=item.selected,
        shadowed=item.shadowed,
        note=item.rule.note,
        unlock_when=_condition_snapshot(unlock_condition, item.unlock),
        when=_condition_snapshot(live_condition, item.live_condition),
        expire_when=_condition_snapshot(expire_condition, item.expiration),
        unlocked_at_ply=item.unlocked_at_ply,
        retired_at_ply=item.retired_at_ply,
        reason=item.reason,
    )


def _override_snapshot(item: OverrideResolution) -> OverrideRuntimeSnapshot:
    return OverrideRuntimeSnapshot(
        id=item.override.id,
        after_san=list(item.override.after_san),
        piece=str(StartingPieceRef.from_original(item.override.move.piece)),
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
        workspace.board,
        workspace.runtime.tracker,
        workspace.runtime.conditions,
        workspace.runtime.last_move,
    )
    snapshots: list[RuleRuntimeSnapshot] = []
    sections = (
        ("response", workspace.author.flow.responses),
        ("development", workspace.author.flow.development),
        ("continuation", workspace.author.flow.continuations),
    )
    for section, rules in sections:
        for order, rule in enumerate(rules, start=1):
            in_scope, scope_reason = workspace.runtime._scope(
                rule.structures, evaluator
            )
            if isinstance(rule, DevelopmentAssignment):
                tracked = workspace.runtime.tracker.get(rule.piece.original_piece_id)
                live = (
                    evaluator.evaluate(rule.ready_when)
                    if rule.ready_when is not None
                    else None
                )
                lifecycle = (
                    "retired" if tracked.has_moved or tracked.captured else "unlocked"
                )
                if not in_scope:
                    status = EffectiveRuleStatus.OUT_OF_SCOPE
                    reason = scope_reason
                elif tracked.has_moved or tracked.captured:
                    status = EffectiveRuleStatus.RETIRED
                    reason = (
                        f"{rule.piece.label} was captured."
                        if tracked.captured
                        else f"{rule.piece.label} already moved."
                    )
                elif live is not None and not live.value:
                    status = EffectiveRuleStatus.INACTIVE
                    reason = live.explanation
                else:
                    status = EffectiveRuleStatus.WAITING
                    reason = "Legality will be checked on the controlled side's turn."
                unlock = expiration = None
                unlocked_at_ply = 0
                retired_at_ply = (
                    tracked.captured_ply
                    if tracked.captured
                    else tracked.first_moved_ply
                )
            else:
                state = workspace.runtime.rule_states[rule.id]
                unlock = (
                    evaluator.evaluate(rule.unlock_when)
                    if rule.unlock_when is not None
                    else None
                )
                live = evaluator.evaluate(rule.when) if rule.when is not None else None
                expiration = (
                    evaluator.evaluate(rule.expire_when)
                    if rule.expire_when is not None
                    else None
                )
                lifecycle = state.lifecycle.value
                unlocked_at_ply = state.unlocked_at_ply
                retired_at_ply = state.retired_at_ply
                if not in_scope:
                    status = EffectiveRuleStatus.OUT_OF_SCOPE
                    reason = scope_reason
                elif state.retired:
                    status = EffectiveRuleStatus.RETIRED
                    reason = state.retirement_reason or "Rule retired."
                elif not state.unlocked:
                    status = EffectiveRuleStatus.LOCKED
                    reason = (
                        unlock.explanation
                        if unlock is not None
                        else "Unlock condition is pending."
                    )
                elif live is not None and not live.value:
                    status = EffectiveRuleStatus.INACTIVE
                    reason = live.explanation
                else:
                    status = EffectiveRuleStatus.WAITING
                    reason = "Legality will be checked on the controlled side's turn."
            snapshots.append(
                RuleRuntimeSnapshot(
                    id=rule.id,
                    section=section,  # type: ignore[arg-type]
                    order=order,
                    structures=list(rule.structures),
                    piece=str(StartingPieceRef.from_original(rule.move.piece)),
                    destination=rule.move.to_square,
                    move_uci=None,
                    move_san=None,
                    legal=False,
                    lifecycle=lifecycle,  # type: ignore[arg-type]
                    status=status.value,
                    selected=False,
                    shadowed=False,
                    note=rule.note,
                    unlock_when=_condition_snapshot(
                        rule.unlock_when if isinstance(rule, MoveRule) else None,
                        unlock,
                    ),
                    when=_condition_snapshot(
                        (rule.when if isinstance(rule, MoveRule) else rule.ready_when),
                        live,
                    ),
                    expire_when=_condition_snapshot(
                        rule.expire_when if isinstance(rule, MoveRule) else None,
                        expiration,
                    ),
                    unlocked_at_ply=unlocked_at_ply,
                    retired_at_ply=retired_at_ply,
                    reason=reason,
                )
            )
    return snapshots


def _structure_snapshots(
    workspace: FlowWorkspace, decision: PolicyDecision | None
) -> list[StructureRuntimeSnapshot]:
    if decision is not None:
        resolutions = decision.structure_resolutions
    else:
        evaluator = ConditionEvaluator(
            workspace.board,
            workspace.runtime.tracker,
            workspace.runtime.conditions,
            workspace.runtime.last_move,
        )
        resolutions = workspace.runtime._resolve_structures(evaluator)
    return [
        StructureRuntimeSnapshot(
            id=item.structure.id,
            name=item.structure.name,
            status=item.status.value,
            available_when=ConditionSnapshot(
                expression=condition_to_data(item.structure.available_when),
                value=item.available.value,
                explanation=item.available.explanation,
            ),
            selected_when=ConditionSnapshot(
                expression=condition_to_data(item.structure.selected_when),
                value=item.selected.value,
                explanation=item.selected.explanation,
            ),
            selected_at_ply=item.selected_at_ply,
            note=item.structure.note,
            reason=item.reason,
        )
        for item in resolutions
    ]


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


def _analysis_profile(profile_id: str) -> EngineProfile:
    for profile in ANALYSIS_PROFILES:
        if profile.id == profile_id:
            return profile
    raise WebApiError(
        ApiErrorCode.INVALID_REQUEST,
        f"Unknown analysis profile {profile_id!r}.",
        status_code=422,
    )


def _analysis_run(line: AnalysedMove, *, lines: int = 1) -> AnalysisRunSnapshot:
    return AnalysisRunSnapshot(
        engine_name=line.engine_name or "Configured UCI engine",
        profile_id=line.profile_id or DEFAULT_ANALYSIS_PROFILE.id,
        requested_depth=line.requested_depth,
        actual_depth=line.actual_depth,
        selective_depth=line.selective_depth,
        nodes=line.nodes,
        nps=line.nps,
        time_ms=line.time_ms,
        lines=lines,
    )


def _configured_engine_name(identity: str) -> str | None:
    if identity == "engine-off":
        return None
    if identity.startswith("stockfish:"):
        return "Stockfish (configured)"
    if identity.startswith("injected:"):
        return identity.removeprefix("injected:")
    return identity


def _opening_match_snapshot(match: OpeningMatch) -> OpeningMatchSnapshot:
    return OpeningMatchSnapshot(
        record_id=match.record_id,
        eco=match.eco,
        name=match.name,
        family=match.family,
        variation=match.variation,
        line_depth=match.line_depth,
    )


def _book_continuation_snapshot(
    continuation: object,
) -> BookContinuationSnapshot:
    from ..opening import BookContinuation

    assert isinstance(continuation, BookContinuation)
    return BookContinuationSnapshot(
        uci=continuation.uci,
        san=continuation.san,
        opening_names=list(continuation.opening_names),
        defense_names=list(continuation.defense_names),
    )


def _opening_context_snapshot(context: OpeningContext) -> OpeningContextSnapshot:
    return OpeningContextSnapshot(
        primary_match=(
            _opening_match_snapshot(context.primary_match)
            if context.primary_match
            else None
        ),
        current_matches=[
            _opening_match_snapshot(match) for match in context.current_matches
        ],
        last_known_match=(
            _opening_match_snapshot(context.last_known_match)
            if context.last_known_match
            else None
        ),
        entered=[_opening_match_snapshot(match) for match in context.entered],
        maintained=[_opening_match_snapshot(match) for match in context.maintained],
        exited=[_opening_match_snapshot(match) for match in context.exited],
        played_move_in_book=context.played_move_in_book,
        book_continuations=[
            _book_continuation_snapshot(item) for item in context.book_continuations
        ],
        reachable_defenses=list(context.reachable_defenses),
        move_source=(
            context.move_source.value if context.move_source is not None else None
        ),  # type: ignore[arg-type]
        policy_rule_id=context.policy_rule_id,
        exact_override_id=context.exact_override_id,
        recorded_reply_id=context.recorded_reply_id,
    )


def _opening_history_item(entry: OpeningHistoryEntry) -> OpeningHistoryItemSnapshot:
    return OpeningHistoryItemSnapshot(
        ply=entry.ply,
        san=entry.san,
        uci=entry.uci,
        position_key=entry.position_key,
        context=_opening_context_snapshot(entry.context),
    )


def _latest_opening_attachment(
    workspace: FlowWorkspace,
) -> OpeningContextAttachment | None:
    if not workspace.opening_history:
        return None
    entry = workspace.opening_history[-1]
    context = entry.context
    transition = bool(context.entered or context.exited)
    if context.played_move_in_book is False and context.move_source in {
        OpeningMoveProvenance.POLICY_ONLY,
        OpeningMoveProvenance.EXACT_OVERRIDE,
    }:
        transition = True
    return OpeningContextAttachment(
        entry=_opening_history_item(entry),
        context=_opening_context_snapshot(context),
        presentation="transition" if transition else "compact",
    )


def _opening_context_text(context: OpeningContext) -> str:
    if context.primary_match is not None:
        return f"Current opening: {context.primary_match.name} ({context.primary_match.eco})."
    if context.last_known_match is not None:
        return (
            "No exact named opening position. Last known opening: "
            f"{context.last_known_match.name} ({context.last_known_match.eco})."
        )
    return "No exact named opening position has been reached on this line."


def _opening_commentary_title(attachment: OpeningContextAttachment) -> str:
    entry = attachment.entry
    if entry is None:
        return "Opening commentary"
    move_number = (entry.ply + 1) // 2
    move_label = (
        f"{move_number}.{entry.san}"
        if entry.ply % 2
        else f"{move_number}...{entry.san}"
    )
    return f"Opening after {move_label}"


def _opening_commentary_text(attachment: OpeningContextAttachment) -> str:
    context = attachment.context
    if context.primary_match is not None:
        return f"{_opening_display_name(context.primary_match)}."
    if context.last_known_match is not None:
        return (
            "No exact named opening position. Last known: "
            f"{_opening_display_name(context.last_known_match)}."
        )
    return "No exact named opening position is known on this line."


def _opening_display_name(match: OpeningMatchSnapshot) -> str:
    return match.variation or match.name


def _entered_defenses(workspace: FlowWorkspace) -> list[str]:
    return sorted(
        {
            match.family
            for entry in workspace.get_opening_history()
            for match in entry.context.current_matches
            if "Defense" in match.family
        }
    )


def _clean_note(note: str | None) -> str | None:
    return note.strip() if note and note.strip() else None


def _is_relative_to(path: Path, directory: Path) -> bool:
    try:
        path.relative_to(directory)
        return True
    except ValueError:
        return False
