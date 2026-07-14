"""Explicit renderer modes supported by the chess TUI."""

from __future__ import annotations

from enum import Enum


class RendererMode(str, Enum):
    PIXEL_MASK = "pixel-mask"
    UNICODE = "unicode"
    LEGACY_SPRITE = "legacy-sprite"
