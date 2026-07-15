"""Errors raised by local flow loading, policy, and persistence."""

from __future__ import annotations


class FlowError(RuntimeError):
    pass


class FlowValidationError(FlowError):
    pass


class FlowStorageError(FlowError):
    pass


class FlowPolicyError(FlowError):
    pass
