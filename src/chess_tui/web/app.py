"""FastAPI application for local Opening Rulebook development."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from ..engine import ChessEngineService, EngineError, StockfishEngineService
from ..flow import FlowStorageError, FlowValidationError
from .api_models import (
    AnalysisSettingsRequest,
    ApiErrorEnvelope,
    ApiErrorItem,
    CreateSessionRequest,
    DevelopmentDraftRequest,
    DevelopmentOrderRequest,
    FlowSourceResponse,
    HealthResponse,
    InterruptDraftRequest,
    InterruptOrderRequest,
    MoveRequest,
    MutationPreviewResponse,
    SanMoveRequest,
    WorkspaceSnapshot,
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
    config = settings or WebAppSettings()

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        engine = analysis_engine
        if engine is None and config.engine_path is not None:
            engine = StockfishEngineService(config.engine_path)
        application.state.session_manager = SessionManager(
            project_root=config.project_root,
            allowed_flow_directory=config.allowed_flow_directory,
            startup_flow_path=config.startup_flow_path,
            engine=engine,
        )
        try:
            yield
        finally:
            if engine is not None:
                await engine.close()

    application = FastAPI(
        title="Chess TUI Opening Rule Engine API",
        version="4.0",
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
        return _error_response(error.code, str(error), error.status_code, error.details)

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
    async def handle_storage(request: Request, error: FlowStorageError) -> JSONResponse:
        del request
        return _error_response(ApiErrorCode.FLOW_PERSISTENCE_ERROR, str(error), 500)

    @application.exception_handler(FlowValidationError)
    async def handle_validation(
        request: Request, error: FlowValidationError
    ) -> JSONResponse:
        del request
        return _error_response(ApiErrorCode.FLOW_VALIDATION_ERROR, str(error), 422)

    @application.exception_handler(EngineError)
    async def handle_engine(request: Request, error: EngineError) -> JSONResponse:
        del request
        return _error_response(ApiErrorCode.ENGINE_ERROR, str(error), 500)


def _register_api_routes(application: FastAPI) -> None:
    @application.get("/api/health", response_model=HealthResponse)
    async def health(request: Request) -> HealthResponse:
        return HealthResponse(engine=_manager(request).evaluations.health)

    @application.post("/api/sessions", response_model=WorkspaceSnapshot)
    async def create_session(
        request: Request, payload: CreateSessionRequest | None = None
    ) -> WorkspaceSnapshot:
        return await _manager(request).create_session(
            payload.flow_path if payload else None
        )

    @application.get("/api/sessions/{session_id}", response_model=WorkspaceSnapshot)
    async def get_session(request: Request, session_id: str) -> WorkspaceSnapshot:
        return await _manager(request).get_snapshot(session_id)

    @application.get(
        "/api/sessions/{session_id}/rulebook/source",
        response_model=FlowSourceResponse,
    )
    async def get_source(request: Request, session_id: str) -> FlowSourceResponse:
        return await _manager(request).get_flow_source(session_id)

    @application.post(
        "/api/sessions/{session_id}/moves", response_model=WorkspaceSnapshot
    )
    async def submit_move(
        request: Request, session_id: str, payload: MoveRequest
    ) -> WorkspaceSnapshot:
        return await _manager(request).submit_move(session_id, payload.uci)

    @application.post(
        "/api/sessions/{session_id}/moves/san", response_model=WorkspaceSnapshot
    )
    async def submit_san(
        request: Request, session_id: str, payload: SanMoveRequest
    ) -> WorkspaceSnapshot:
        return await _manager(request).submit_san_move(session_id, payload.san)

    @application.post(
        "/api/sessions/{session_id}/policy/retry", response_model=WorkspaceSnapshot
    )
    async def retry(request: Request, session_id: str) -> WorkspaceSnapshot:
        return await _manager(request).retry_policy(session_id)

    @application.post(
        "/api/sessions/{session_id}/policy/continue",
        response_model=WorkspaceSnapshot,
    )
    async def continue_policy(request: Request, session_id: str) -> WorkspaceSnapshot:
        return await _manager(request).continue_policy(session_id)

    @application.post(
        "/api/sessions/{session_id}/attempt/accept-here",
        response_model=WorkspaceSnapshot,
    )
    async def accept_here(request: Request, session_id: str) -> WorkspaceSnapshot:
        return await _manager(request).accept_attempt_as_interrupt(session_id)

    @application.post(
        "/api/sessions/{session_id}/development/validate",
        response_model=MutationPreviewResponse,
    )
    async def preview_development(
        request: Request, session_id: str, payload: DevelopmentDraftRequest
    ) -> MutationPreviewResponse:
        return await _manager(request).preview_development(session_id, payload)

    @application.post(
        "/api/sessions/{session_id}/development",
        response_model=WorkspaceSnapshot,
    )
    async def apply_development(
        request: Request, session_id: str, payload: DevelopmentDraftRequest
    ) -> WorkspaceSnapshot:
        return await _manager(request).apply_development(session_id, payload)

    @application.delete(
        "/api/sessions/{session_id}/development/{alias}",
        response_model=WorkspaceSnapshot,
    )
    async def delete_development(
        request: Request, session_id: str, alias: str
    ) -> WorkspaceSnapshot:
        return await _manager(request).delete_development(session_id, alias)

    @application.post(
        "/api/sessions/{session_id}/interrupts/validate",
        response_model=MutationPreviewResponse,
    )
    async def preview_interrupt(
        request: Request, session_id: str, payload: InterruptDraftRequest
    ) -> MutationPreviewResponse:
        return await _manager(request).preview_interrupt(session_id, payload)

    @application.post(
        "/api/sessions/{session_id}/interrupts", response_model=WorkspaceSnapshot
    )
    async def apply_interrupt(
        request: Request, session_id: str, payload: InterruptDraftRequest
    ) -> WorkspaceSnapshot:
        return await _manager(request).apply_interrupt(session_id, payload)

    @application.delete(
        "/api/sessions/{session_id}/interrupts/{alias}/{rule_id}",
        response_model=WorkspaceSnapshot,
    )
    async def delete_interrupt(
        request: Request, session_id: str, alias: str, rule_id: str
    ) -> WorkspaceSnapshot:
        return await _manager(request).delete_interrupt(session_id, alias, rule_id)

    @application.put(
        "/api/sessions/{session_id}/orders/development",
        response_model=WorkspaceSnapshot,
    )
    async def reorder_development(
        request: Request, session_id: str, payload: DevelopmentOrderRequest
    ) -> WorkspaceSnapshot:
        return await _manager(request).reorder_development(
            session_id, tuple(payload.aliases)
        )

    @application.put(
        "/api/sessions/{session_id}/orders/interrupts",
        response_model=WorkspaceSnapshot,
    )
    async def reorder_interrupts(
        request: Request, session_id: str, payload: InterruptOrderRequest
    ) -> WorkspaceSnapshot:
        return await _manager(request).reorder_interrupts(
            session_id, tuple(payload.rule_refs)
        )

    @application.post(
        "/api/sessions/{session_id}/analysis", response_model=WorkspaceSnapshot
    )
    async def analyse(request: Request, session_id: str) -> WorkspaceSnapshot:
        return await _manager(request).analyse_position(session_id)

    @application.put(
        "/api/sessions/{session_id}/analysis/settings",
        response_model=WorkspaceSnapshot,
    )
    async def analysis_settings(
        request: Request,
        session_id: str,
        payload: AnalysisSettingsRequest,
    ) -> WorkspaceSnapshot:
        return await _manager(request).update_analysis_profile(
            session_id, payload.profile_id
        )

    @application.post(
        "/api/sessions/{session_id}/back", response_model=WorkspaceSnapshot
    )
    async def back(request: Request, session_id: str) -> WorkspaceSnapshot:
        return await _manager(request).go_back(session_id)

    @application.post(
        "/api/sessions/{session_id}/restart", response_model=WorkspaceSnapshot
    )
    async def restart(request: Request, session_id: str) -> WorkspaceSnapshot:
        return await _manager(request).restart(session_id)

    @application.post(
        "/api/sessions/{session_id}/reload", response_model=WorkspaceSnapshot
    )
    async def reload(request: Request, session_id: str) -> WorkspaceSnapshot:
        return await _manager(request).reload(session_id)

    @application.api_route(
        "/api/{unknown_path:path}",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        include_in_schema=False,
    )
    async def unknown_api(unknown_path: str) -> JSONResponse:
        del unknown_path
        return _error_response(
            ApiErrorCode.INVALID_REQUEST, "API route was not found.", 404
        )


def _register_frontend_routes(application: FastAPI, frontend_dist: Path) -> None:
    dist = frontend_dist.resolve()

    @application.get("/{browser_path:path}", include_in_schema=False)
    async def frontend(browser_path: str):
        if not dist.is_dir() or not (dist / "index.html").is_file():
            return HTMLResponse(
                "<h1>Chess TUI web build not found</h1>"
                "<p>Run <code>cd web &amp;&amp; npm run build</code>.</p>",
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
        error=ApiErrorItem(code=code, message=message, details=details or {})
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
