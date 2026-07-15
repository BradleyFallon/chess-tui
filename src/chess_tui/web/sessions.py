"""In-memory Development Mode sessions over the shared Python flow core."""

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
)
from ..flow import (
    AttemptResult,
    FlowError,
    FlowStore,
    FlowWorkspace,
    WhiteMoveAttempt,
    normalized_position_key,
)
from ..flow.position import replay_san
from .api_models import (
    ActivitySnapshot,
    ApiErrorItem,
    AttemptSnapshot,
    DecisionSnapshot,
    EngineHealth,
    EngineReviewSnapshot,
    EvaluationSnapshot,
    FlowSnapshot,
    GameOverSnapshot,
    NavigationSnapshot,
    PositionSnapshot,
    RuleGroupsSnapshot,
    RuleSummary,
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
        key = (
            normalized_position_key(board),
            self.profile_id,
            self.engine_identity,
        )
        async with self._lock:
            cached = self._cache.get(key)
            if cached is not None:
                return cached
            try:
                lines = await self.engine.analyse(board, count=1)
                if not lines:
                    raise RuntimeError("Engine returned no analysis rows.")
            except EngineError as error:
                self._status = "error"
                self.last_error = str(error)
                raise
            line = lines[0]
            self._cache[key] = line
            self._status = "ready"
            self.last_error = None
            return line


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
            startup_flow_path.resolve() if startup_flow_path is not None else None
        )
        self.evaluations = EvaluationCache(
            engine,
            engine_identity=engine_identity,
        )
        self.sessions: dict[str, DevelopmentSession] = {}

    async def create_session(
        self, requested_flow_path: str | None
    ) -> WorkspaceSnapshot:
        path = self._resolve_flow_path(requested_flow_path)
        workspace = FlowWorkspace(path)
        workspace.restart()
        session = DevelopmentSession(secrets.token_urlsafe(18), path, workspace)
        self._append_activity(
            session,
            "info",
            "Development session ready",
            f"Loaded {workspace.author.flow.name}. White moves follow the saved flow rules.",
        )
        self.sessions[session.id] = session
        async with session.lock:
            return await self._snapshot(session)

    async def get_snapshot(self, session_id: str) -> WorkspaceSnapshot:
        session = self._session(session_id)
        async with session.lock:
            return await self._snapshot(session)

    async def submit_move(self, session_id: str, uci: str) -> WorkspaceSnapshot:
        session = self._session(session_id)
        async with session.lock:
            workspace = session.workspace
            if workspace.attempt is not None:
                raise WebApiError(
                    ApiErrorCode.INVALID_REQUEST,
                    "Resolve the current White result before playing another move.",
                )
            move = self._legal_move(workspace.board, uci)
            if workspace.board.turn is chess.WHITE:
                attempt = workspace.submit_white_uci(move.uci())
                self._record_white_attempt(session, attempt)
            else:
                move_san = workspace.board.san(move)
                workspace.submit_black_uci(move.uci())
                self._append_activity(
                    session,
                    "move",
                    f"Black played {move_san}",
                    "This is the selected Black reply for the current flow line.",
                )
                if workspace.outcome is None:
                    workspace.begin_white_turn()
            return await self._snapshot(session)

    async def retry_white(self, session_id: str) -> WorkspaceSnapshot:
        session = self._session(session_id)
        async with session.lock:
            if session.workspace.attempt is None:
                raise WebApiError(
                    ApiErrorCode.INVALID_REQUEST,
                    "No White result is available to retry.",
                )
            session.workspace.retry_white_move()
            self._append_activity(
                session,
                "info",
                "Retry White’s move",
                "The position was restored. Try the White move again or ask for a hint.",
            )
            return await self._snapshot(session)

    async def play_next_black(self, session_id: str) -> WorkspaceSnapshot:
        session = self._session(session_id)
        async with session.lock:
            workspace = session.workspace
            if (
                workspace.attempt is not None
                or workspace.outcome is not None
                or workspace.board.turn is not chess.BLACK
            ):
                raise WebApiError(
                    ApiErrorCode.INVALID_REQUEST,
                    "Next is only available while Black is ready to move.",
                )
            engine = self.evaluations.engine
            if engine is None:
                raise WebApiError(
                    ApiErrorCode.ENGINE_ERROR,
                    "Black’s next move requires a configured chess engine.",
                    status_code=503,
                )
            try:
                move = await engine.choose_move(
                    workspace.board.copy(stack=False),
                    ENGINE_PROTOTYPE_PROFILE,
                )
            except EngineError as error:
                raise WebApiError(
                    ApiErrorCode.ENGINE_ERROR,
                    f"The chess engine could not choose Black’s move: {error}",
                    status_code=502,
                ) from error
            if move not in workspace.board.legal_moves:
                raise WebApiError(
                    ApiErrorCode.ENGINE_ERROR,
                    "The chess engine returned an illegal Black move.",
                    status_code=502,
                )
            move_san = workspace.board.san(move)
            workspace.submit_black_uci(move.uci())
            self._append_activity(
                session,
                "move",
                f"Black played {move_san}",
                "The engine selected this reply after you chose Next.",
            )
            if workspace.outcome is None:
                workspace.begin_white_turn()
            return await self._snapshot(session)

    async def keep_white(self, session_id: str) -> WorkspaceSnapshot:
        session = self._session(session_id)
        async with session.lock:
            attempt = session.workspace.attempt
            if attempt is None or attempt.result not in {
                AttemptResult.MISMATCH_DEFAULT,
                AttemptResult.MISMATCH_EXCEPTION,
            }:
                raise WebApiError(
                    ApiErrorCode.INVALID_REQUEST,
                    "Only a mismatching saved rule can be continued.",
                )
            recommendation = attempt.recommendation
            if recommendation is None:
                raise WebApiError(
                    ApiErrorCode.INVALID_REQUEST,
                    "The mismatching move does not have a saved rule to keep.",
                )
            expected_san = recommendation.move_san
            session.workspace.keep_saved_rule()
            self._append_activity(
                session,
                "success",
                f"Continued with {expected_san}",
                "The saved rule was kept unchanged and its expected move was played.",
            )
            return await self._snapshot(session)

    async def continue_white(self, session_id: str) -> WorkspaceSnapshot:
        session = self._session(session_id)
        async with session.lock:
            attempt = session.workspace.attempt
            if attempt is None or attempt.result is not AttemptResult.CORRECT:
                raise WebApiError(
                    ApiErrorCode.INVALID_REQUEST,
                    "Only a correct White result can be continued.",
                )
            session.workspace.complete_correct_move()
            self._append_activity(
                session,
                "info",
                "White move accepted",
                "Choose Black’s reply to continue the flow line.",
            )
            return await self._snapshot(session)

    async def go_back(self, session_id: str) -> WorkspaceSnapshot:
        session = self._session(session_id)
        async with session.lock:
            if not session.workspace.can_go_back:
                raise WebApiError(
                    ApiErrorCode.INVALID_NAVIGATION,
                    "There is no earlier White decision.",
                )
            session.workspace.go_back_to_previous_decision()
            self._append_activity(
                session,
                "info",
                "Moved back",
                "Returned to the previous White decision without changing any saved rules.",
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
                "Returned to the beginning of the flow without changing any saved rules.",
            )
            return await self._snapshot(session)

    def _record_white_attempt(
        self, session: DevelopmentSession, attempt: WhiteMoveAttempt
    ) -> None:
        recommendation = attempt.recommendation
        if attempt.result is AttemptResult.CORRECT:
            reason = (
                recommendation.note
                if recommendation is not None and recommendation.note
                else (
                    f"It matches the saved {recommendation.source} rule."
                    if recommendation is not None
                    else "It matches the saved rule."
                )
            )
            kind = "success"
            message = f"Correct. {reason}"
        elif attempt.result in {
            AttemptResult.MISMATCH_DEFAULT,
            AttemptResult.MISMATCH_EXCEPTION,
        }:
            expected = recommendation.move_san if recommendation else "the saved move"
            note = (
                f" {recommendation.note}"
                if recommendation is not None and recommendation.note
                else ""
            )
            kind = "warning"
            message = (
                f"Incorrect for this flow. The saved rule expects {expected}.{note} "
                "Retry, keep the saved rule, or edit the rule outside this web view."
            )
        elif attempt.result is AttemptResult.FRONTIER:
            kind = "warning"
            message = (
                "There is no saved rule for this position. Retry or edit the flow in "
                "the TUI or TOML file."
            )
        else:
            kind = "warning"
            message = (
                "The saved rule is unavailable in this position. Retry or edit the "
                "flow in the TUI or TOML file."
            )
        self._append_activity(
            session,
            kind,
            f"White played {attempt.selected_move.san}",
            message,
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
                id=session.next_activity_id,
                kind=kind,
                title=title,
                message=message,
            )
        )
        session.next_activity_id += 1
        if len(session.activity) > 100:
            del session.activity[:-100]

    def _session(self, session_id: str) -> DevelopmentSession:
        session = self.sessions.get(session_id)
        if session is None:
            raise WebApiError(
                ApiErrorCode.SESSION_NOT_FOUND,
                "Development session was not found.",
                status_code=404,
            )
        return session

    def _resolve_flow_path(self, requested: str | None) -> Path:
        if requested is None:
            candidate = self.startup_flow_path or self._most_recent_flow()
        else:
            raw = Path(requested).expanduser()
            candidate = raw if raw.is_absolute() else self.project_root / raw
            candidate = candidate.resolve()
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
                ApiErrorCode.FLOW_VALIDATION_ERROR,
                str(error),
                status_code=422,
            ) from error
        return candidate

    def _most_recent_flow(self) -> Path:
        candidates = tuple(self.allowed_flow_directory.glob("*.toml"))
        if not candidates:
            raise WebApiError(
                ApiErrorCode.FLOW_VALIDATION_ERROR,
                "No flow files are available.",
                status_code=422,
            )
        return max(candidates, key=lambda path: (path.stat().st_mtime_ns, path.name))

    @staticmethod
    def _legal_move(board: chess.Board, uci: str) -> chess.Move:
        try:
            move = chess.Move.from_uci(uci)
        except ValueError as error:
            raise WebApiError(
                ApiErrorCode.INVALID_MOVE,
                f"Move {uci} is not valid UCI notation.",
            ) from error
        if move not in board.legal_moves:
            raise WebApiError(
                ApiErrorCode.INVALID_MOVE,
                f"Move {uci} is not legal in the current position.",
            )
        return move

    async def _snapshot(self, session: DevelopmentSession) -> WorkspaceSnapshot:
        workspace = session.workspace
        phase = _phase(workspace)
        decision = _decision(workspace, phase)
        evaluation, evaluation_error = await self._evaluation(workspace)
        attempt = await self._attempt(workspace)
        errors = []
        if evaluation_error is not None:
            errors.append(
                ApiErrorItem(
                    code=ApiErrorCode.ENGINE_ERROR,
                    message=evaluation_error,
                )
            )
        interaction = workspace.controller.interaction
        legal_moves = (
            [move.uci() for move in workspace.board.legal_moves]
            if phase in {"white-ready", "black-ready"}
            else []
        )
        return WorkspaceSnapshot(
            session_id=session.id,
            phase=phase,  # type: ignore[arg-type]
            flow=FlowSnapshot(
                name=workspace.author.flow.name,
                version=workspace.author.flow.version,
                path=self._display_path(session.flow_path),
            ),
            position=PositionSnapshot(
                fen=workspace.board.fen(en_passant="fen"),
                history_san=list(workspace.history),
                turn="white" if workspace.board.turn is chess.WHITE else "black",
                ply=len(workspace.history),
                last_move_uci=(
                    interaction.last_move.uci
                    if interaction.last_move is not None
                    else None
                ),
                legal_moves_uci=legal_moves,
                game_over=_game_over(workspace.outcome),
            ),
            decision=decision,
            attempt=attempt,
            rules=_rules(decision),
            evaluation=evaluation,
            navigation=NavigationSnapshot(
                can_back=workspace.can_go_back,
                can_restart=workspace.can_restart,
            ),
            activity=session.activity,
            errors=errors,
        )

    async def _evaluation(
        self,
        workspace: FlowWorkspace,
    ) -> tuple[EvaluationSnapshot, str | None]:
        if workspace.outcome is not None and self.evaluations.engine is None:
            return EvaluationSnapshot(status="game-over"), None
        if self.evaluations.engine is None:
            return EvaluationSnapshot(status="engine-off"), None
        previous: AnalysedMove | None = None
        try:
            if workspace.history:
                previous_board = replay_san(
                    workspace.author.flow.start_fen,
                    tuple(workspace.history[:-1]),
                )
                if previous_board.outcome(claim_draw=False) is None:
                    previous = await self.evaluations.analyse(previous_board)
            if workspace.outcome is not None:
                return (
                    EvaluationSnapshot(
                        status="game-over",
                        previous_centipawns=(
                            previous.evaluation_cp if previous is not None else None
                        ),
                        previous_mate_in=(
                            previous.mate_in if previous is not None else None
                        ),
                    ),
                    None,
                )
            current = await self.evaluations.analyse(workspace.board)
        except (EngineError, RuntimeError) as error:
            return EvaluationSnapshot(status="error", error_message=str(error)), str(
                error
            )
        change = None
        if (
            current.evaluation_cp is not None
            and previous is not None
            and previous.evaluation_cp is not None
        ):
            change = current.evaluation_cp - previous.evaluation_cp
        return (
            EvaluationSnapshot(
                status="ready",
                centipawns=current.evaluation_cp,
                mate_in=current.mate_in,
                previous_centipawns=(
                    previous.evaluation_cp if previous is not None else None
                ),
                previous_mate_in=previous.mate_in if previous is not None else None,
                change_centipawns=change,
            ),
            None,
        )

    async def _attempt(self, workspace: FlowWorkspace) -> AttemptSnapshot | None:
        attempt = workspace.attempt
        if attempt is None:
            return None
        recommendation = attempt.recommendation
        expected_uci = None
        if recommendation is not None:
            try:
                expected_uci = attempt.board_before.parse_san(
                    recommendation.move_san
                ).uci()
            except ValueError:
                expected_uci = None
        review = None
        if attempt.result in {
            AttemptResult.MISMATCH_DEFAULT,
            AttemptResult.MISMATCH_EXCEPTION,
        }:
            review = await self._engine_review(workspace)
        return AttemptSnapshot(
            result=attempt.result.value,  # type: ignore[arg-type]
            played_uci=attempt.selected_move.move.uci,
            played_san=attempt.selected_move.san,
            expected_uci=expected_uci,
            expected_san=(recommendation.move_san if recommendation else None),
            source=(recommendation.source if recommendation else "frontier"),
            engine_review=review,
        )

    async def _engine_review(self, workspace: FlowWorkspace) -> EngineReviewSnapshot:
        if self.evaluations.engine is None:
            return EngineReviewSnapshot(status="engine-off")
        attempt = workspace.attempt
        assert attempt is not None
        try:
            before = await self.evaluations.analyse(attempt.board_before)
            if workspace.outcome is None:
                after = await self.evaluations.analyse(workspace.board)
            else:
                after = _terminal_analysis(workspace.outcome)
            played = chess.Move.from_uci(attempt.selected_move.move.uci)
            assessment = build_white_move_assessment(
                attempt.board_before,
                played,
                before,
                after,
            )
        except (EngineError, RuntimeError) as error:
            return EngineReviewSnapshot(status="error", error_message=str(error))
        return EngineReviewSnapshot(
            status="ready",
            quality=assessment.quality.value,
            loss_cp=assessment.loss_cp,
            best_move_uci=assessment.best_uci,
            best_move_san=before.san,
            evaluation_before_cp=assessment.evaluation_before_cp,
            evaluation_after_cp=assessment.evaluation_after_cp,
            mate_before=assessment.mate_before,
            mate_after=assessment.mate_after,
        )

    def _display_path(self, path: Path) -> str:
        try:
            return path.relative_to(self.project_root).as_posix()
        except ValueError:
            return path.name


def _phase(workspace: FlowWorkspace) -> str:
    if workspace.outcome is not None:
        return "game-over"
    if workspace.attempt is not None:
        return "white-result"
    if workspace.board.turn is chess.WHITE:
        return "white-ready"
    return "black-ready"


def _decision(workspace: FlowWorkspace, phase: str) -> DecisionSnapshot | None:
    if phase in {"black-ready", "game-over"}:
        return None
    turn = workspace.white_turn
    if turn is None:
        return None
    recommendation = turn.recommendation
    if recommendation is None:
        return DecisionSnapshot(
            status="frontier",
            move_uci=None,
            move_san=None,
            source="frontier",
            source_id=None,
            step=turn.white_step,
            note=None,
        )
    board = workspace.attempt.board_before if workspace.attempt else workspace.board
    try:
        move_uci = board.parse_san(recommendation.move_san).uci()
    except ValueError:
        move_uci = None
    return DecisionSnapshot(
        status="unavailable" if turn.unavailable_reason else "ready",
        move_uci=move_uci,
        move_san=recommendation.move_san,
        source=recommendation.source,
        source_id=recommendation.exception_id,
        step=turn.white_step,
        note=recommendation.note,
        unavailable_reason=turn.unavailable_reason,
    )


def _rules(decision: DecisionSnapshot | None) -> RuleGroupsSnapshot:
    selected = None
    if decision is not None and decision.source != "frontier" and decision.move_san:
        selected = RuleSummary(
            source=decision.source,
            source_id=decision.source_id,
            step=decision.step,
            move_san=decision.move_san,
            note=decision.note,
        )
    return RuleGroupsSnapshot(
        selected=selected,
        model_message=(
            "Legacy version 1 flows use numbered defaults and exact-position "
            "exceptions. Active, dormant, and retired lifecycle rules are not "
            "available yet."
        ),
    )


def _game_over(outcome: chess.Outcome | None) -> GameOverSnapshot | None:
    if outcome is None:
        return None
    winner = None
    if outcome.winner is not None:
        winner = "white" if outcome.winner is chess.WHITE else "black"
    return GameOverSnapshot(
        result=outcome.result(),
        termination=outcome.termination.name.lower().replace("_", "-"),
        winner=winner,  # type: ignore[arg-type]
    )


def _terminal_analysis(outcome: chess.Outcome) -> AnalysedMove:
    if outcome.termination is chess.Termination.CHECKMATE:
        mate = 0 if outcome.winner is chess.WHITE else -1
        return AnalysedMove("", "", None, (), mate_in=mate)
    return AnalysedMove("", "", 0, ())


def _is_relative_to(path: Path, directory: Path) -> bool:
    try:
        path.relative_to(directory)
    except ValueError:
        return False
    return True
