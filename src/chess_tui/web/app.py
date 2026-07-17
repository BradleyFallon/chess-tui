"""FastAPI application factory for local Flow Development Mode."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from ..commands import CommandFailure, CommandId, CommandInvocation
from ..engine import ChessEngineService, EngineError, StockfishEngineService
from ..flow import FlowStorageError, FlowValidationError
from .api_models import (
    ApiErrorEnvelope,
    ApiErrorItem,
    ChatRequest,
    CommandResponse,
    CreateSessionRequest,
    FlowSourceResponse,
    HealthResponse,
    MoveRequest,
    OpeningTagRequest,
    InspectRuleCommandRequest,
    PlayMoveCommandRequest,
    SanMoveRequest,
    UpdateOverrideRequest,
    UpdateRuleRequest,
    WorkspaceSnapshot,
    TypedCommandRequest,
)
from .errors import ApiErrorCode, WebApiError
from .sessions import SessionManager

PROJECT_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True, slots=True)
class WebAppSettings:
    project_root: Path = PROJECT_ROOT
    allowed_flow_directory: Path = PROJECT_ROOT / "flows"
    startup_flow_path: Path | None = None
    engine_path: Path | None = None
    frontend_dist: Path = PROJECT_ROOT / "web" / "dist"


def create_app(
    settings: WebAppSettings | None = None,
    *,
    analysis_engine: ChessEngineService | None = None,
) -> FastAPI:
    """Create an isolated local web application and its owned lifespan."""

    config = settings or WebAppSettings()

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        engine = analysis_engine
        identity = "engine-off"
        if engine is not None:
            identity = f"injected:{type(engine).__name__}"
        elif config.engine_path is not None:
            engine = StockfishEngineService(config.engine_path)
            identity = f"stockfish:{config.engine_path.resolve()}"
        application.state.session_manager = SessionManager(
            project_root=config.project_root,
            allowed_flow_directory=config.allowed_flow_directory,
            startup_flow_path=config.startup_flow_path,
            engine=engine,
            engine_identity=identity,
        )
        try:
            yield
        finally:
            if engine is not None:
                await engine.close()

    application = FastAPI(
        title="Chess TUI Local Web API",
        version="0.1.0",
        lifespan=lifespan,
    )
    _register_error_handlers(application)
    _register_api_routes(application)
    _register_frontend_routes(application, config.frontend_dist)
    return application


def _register_error_handlers(application: FastAPI) -> None:
    @application.exception_handler(WebApiError)
    async def handle_web_error(request: Request, error: WebApiError) -> JSONResponse:
        del request
        return _error_response(
            error.code,
            str(error),
            error.status_code,
            error.details,
        )

    @application.exception_handler(RequestValidationError)
    async def handle_request_validation(
        request: Request, error: RequestValidationError
    ) -> JSONResponse:
        del request
        return _error_response(
            ApiErrorCode.INVALID_REQUEST,
            "Request data is invalid.",
            422,
            {"issues": error.errors()},
        )

    @application.exception_handler(FlowStorageError)
    async def handle_flow_storage(
        request: Request, error: FlowStorageError
    ) -> JSONResponse:
        del request
        return _error_response(
            ApiErrorCode.FLOW_PERSISTENCE_ERROR,
            str(error),
            500,
        )

    @application.exception_handler(FlowValidationError)
    async def handle_flow_validation(
        request: Request, error: FlowValidationError
    ) -> JSONResponse:
        del request
        return _error_response(
            ApiErrorCode.FLOW_VALIDATION_ERROR,
            str(error),
            422,
        )

    @application.exception_handler(EngineError)
    async def handle_engine_error(request: Request, error: EngineError) -> JSONResponse:
        del request
        return _error_response(ApiErrorCode.ENGINE_ERROR, str(error), 500)

    @application.exception_handler(CommandFailure)
    async def handle_command_error(
        request: Request, error: CommandFailure
    ) -> JSONResponse:
        del request
        return _error_response(
            ApiErrorCode.INVALID_REQUEST,
            str(error),
            400,
            {"commandCode": error.code, **error.details},
        )


def _register_api_routes(application: FastAPI) -> None:
    @application.get("/api/health", response_model=HealthResponse)
    async def health(request: Request) -> HealthResponse:
        manager = _manager(request)
        return HealthResponse(engine=manager.evaluations.health)

    @application.post("/api/sessions", response_model=WorkspaceSnapshot)
    async def create_session(
        request: Request,
        payload: CreateSessionRequest | None = None,
    ) -> WorkspaceSnapshot:
        return await _manager(request).create_session(
            payload.flow_path if payload is not None else None
        )

    @application.get("/api/sessions/{session_id}", response_model=WorkspaceSnapshot)
    async def get_session(request: Request, session_id: str) -> WorkspaceSnapshot:
        return await _manager(request).get_snapshot(session_id)

    @application.get(
        "/api/sessions/{session_id}/flow/source",
        response_model=FlowSourceResponse,
    )
    async def get_flow_source(request: Request, session_id: str) -> FlowSourceResponse:
        return await _manager(request).get_flow_source(session_id)

    @application.post(
        "/api/sessions/{session_id}/moves", response_model=WorkspaceSnapshot
    )
    async def submit_move(
        request: Request,
        session_id: str,
        payload: MoveRequest,
    ) -> WorkspaceSnapshot:
        return await _manager(request).submit_move(session_id, payload.uci)

    @application.post(
        "/api/sessions/{session_id}/moves/san",
        response_model=WorkspaceSnapshot,
    )
    async def submit_san_move(
        request: Request,
        session_id: str,
        payload: SanMoveRequest,
    ) -> WorkspaceSnapshot:
        return await _manager(request).submit_san_move(session_id, payload.san)

    @application.post(
        "/api/sessions/{session_id}/chat",
        response_model=CommandResponse,
    )
    async def submit_chat(
        request: Request,
        session_id: str,
        payload: ChatRequest,
    ) -> CommandResponse:
        return await _manager(request).submit_chat(session_id, payload.text)

    @application.post(
        "/api/sessions/{session_id}/commands",
        response_model=CommandResponse,
    )
    async def execute_command(
        request: Request,
        session_id: str,
        payload: TypedCommandRequest,
    ) -> CommandResponse:
        invocation = CommandInvocation(
            command=CommandId(payload.command),
            source=payload.source,
            notation=(
                payload.notation
                if isinstance(payload, PlayMoveCommandRequest)
                else None
            ),
            move=(
                payload.move if isinstance(payload, PlayMoveCommandRequest) else None
            ),
            rule_id=(
                payload.rule_id
                if isinstance(payload, InspectRuleCommandRequest)
                else None
            ),
        )
        return await _manager(request).execute_command(session_id, invocation)

    @application.post(
        "/api/sessions/{session_id}/policy/retry",
        response_model=WorkspaceSnapshot,
    )
    async def retry_policy(request: Request, session_id: str) -> WorkspaceSnapshot:
        return await _manager(request).retry_policy(session_id)

    @application.post(
        "/api/sessions/{session_id}/policy/continue",
        response_model=WorkspaceSnapshot,
    )
    async def continue_policy(request: Request, session_id: str) -> WorkspaceSnapshot:
        return await _manager(request).continue_policy(session_id)

    @application.post(
        "/api/sessions/{session_id}/policy/add-rule",
        response_model=WorkspaceSnapshot,
    )
    async def add_rule_for_mismatch(
        request: Request, session_id: str
    ) -> WorkspaceSnapshot:
        return await _manager(request).add_rule_for_mismatch(session_id)

    @application.post(
        "/api/sessions/{session_id}/opponent/next",
        response_model=WorkspaceSnapshot,
    )
    async def play_next_opponent(
        request: Request, session_id: str
    ) -> WorkspaceSnapshot:
        return await _manager(request).play_next_opponent(session_id)

    @application.post(
        "/api/sessions/{session_id}/analysis",
        response_model=WorkspaceSnapshot,
    )
    async def analyse_position(request: Request, session_id: str) -> WorkspaceSnapshot:
        return await _manager(request).analyse_position(session_id)

    @application.put(
        "/api/sessions/{session_id}/rules/{rule_id}",
        response_model=WorkspaceSnapshot,
    )
    async def update_rule(
        request: Request,
        session_id: str,
        rule_id: str,
        payload: UpdateRuleRequest,
    ) -> WorkspaceSnapshot:
        return await _manager(request).update_rule(session_id, rule_id, payload)

    @application.put(
        "/api/sessions/{session_id}/overrides/{override_id}",
        response_model=WorkspaceSnapshot,
    )
    async def update_override(
        request: Request,
        session_id: str,
        override_id: str,
        payload: UpdateOverrideRequest,
    ) -> WorkspaceSnapshot:
        return await _manager(request).update_override(session_id, override_id, payload)

    @application.post(
        "/api/sessions/{session_id}/opening-tags",
        response_model=WorkspaceSnapshot,
    )
    async def add_opening_tag(
        request: Request,
        session_id: str,
        payload: OpeningTagRequest,
    ) -> WorkspaceSnapshot:
        return await _manager(request).add_opening_tag(session_id, payload.record_id)

    @application.delete(
        "/api/sessions/{session_id}/opening-tags/{record_id}",
        response_model=WorkspaceSnapshot,
    )
    async def remove_opening_tag(
        request: Request,
        session_id: str,
        record_id: int,
    ) -> WorkspaceSnapshot:
        return await _manager(request).remove_opening_tag(session_id, record_id)

    @application.post(
        "/api/sessions/{session_id}/back", response_model=WorkspaceSnapshot
    )
    async def go_back(request: Request, session_id: str) -> WorkspaceSnapshot:
        return await _manager(request).go_back(session_id)

    @application.post(
        "/api/sessions/{session_id}/restart", response_model=WorkspaceSnapshot
    )
    async def restart(request: Request, session_id: str) -> WorkspaceSnapshot:
        return await _manager(request).restart(session_id)

    @application.api_route(
        "/api/{unknown_path:path}",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        include_in_schema=False,
    )
    async def unknown_api(unknown_path: str) -> JSONResponse:
        del unknown_path
        return _error_response(
            ApiErrorCode.INVALID_REQUEST,
            "API route was not found.",
            404,
        )


def _register_frontend_routes(application: FastAPI, frontend_dist: Path) -> None:
    dist = frontend_dist.resolve()

    @application.get("/{browser_path:path}", include_in_schema=False)
    async def frontend(browser_path: str):
        if not dist.is_dir() or not (dist / "index.html").is_file():
            return HTMLResponse(
                "<h1>Chess TUI web build not found</h1>"
                "<p>Run <code>cd web &amp;&amp; npm run build</code>, then restart "
                "the server. The API remains available under <code>/api</code>.</p>",
                status_code=503,
            )
        candidate = (dist / browser_path).resolve()
        if _is_relative_to(candidate, dist) and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(dist / "index.html")


def _manager(request: Request) -> SessionManager:
    return cast(SessionManager, request.app.state.session_manager)


def _error_response(
    code: ApiErrorCode,
    message: str,
    status_code: int,
    details: dict[str, object] | None = None,
) -> JSONResponse:
    envelope = ApiErrorEnvelope(
        error=ApiErrorItem(
            code=code,
            message=message,
            details=details or {},
        )
    )
    return JSONResponse(
        status_code=status_code,
        content=envelope.model_dump(by_alias=True, mode="json"),
    )


def _is_relative_to(path: Path, directory: Path) -> bool:
    try:
        path.relative_to(directory)
    except ValueError:
        return False
    return True


app = create_app()
