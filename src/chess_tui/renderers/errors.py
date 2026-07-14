"""Renderer-specific exceptions."""

from __future__ import annotations


class RendererError(RuntimeError):
    """Raised when a renderer cannot initialize or render correctly."""


class RendererStartupError(RendererError):
    """Raised when renderer startup validation fails."""
