"""Structured local-web API failures."""

from __future__ import annotations

from enum import Enum
from typing import Mapping


class ApiErrorCode(str, Enum):
    INVALID_MOVE = "INVALID_MOVE"
    FLOW_VALIDATION_ERROR = "FLOW_VALIDATION_ERROR"
    FLOW_PERSISTENCE_ERROR = "FLOW_PERSISTENCE_ERROR"
    ENGINE_ERROR = "ENGINE_ERROR"
    SESSION_NOT_FOUND = "SESSION_NOT_FOUND"
    INVALID_NAVIGATION = "INVALID_NAVIGATION"
    INVALID_REQUEST = "INVALID_REQUEST"


class WebApiError(RuntimeError):
    def __init__(
        self,
        code: ApiErrorCode,
        message: str,
        *,
        status_code: int = 400,
        details: Mapping[str, object] | None = None,
    ) -> None:
        self.code = code
        self.status_code = status_code
        self.details = dict(details or {})
        super().__init__(message)
