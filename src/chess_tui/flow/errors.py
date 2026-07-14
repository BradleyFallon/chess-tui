"""Errors raised by local flow loading, policy, and persistence."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import Recommendation


class FlowError(RuntimeError):
    pass


class FlowValidationError(FlowError):
    pass


class FlowStorageError(FlowError):
    pass


class FlowPolicyError(FlowError):
    pass


class RuleUnavailableError(FlowPolicyError):
    def __init__(self, recommendation: Recommendation, detail: str) -> None:
        self.recommendation = recommendation
        super().__init__(detail)
