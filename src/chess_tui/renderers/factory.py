"""Factory for constructing the requested piece renderer."""

from __future__ import annotations

from .base import PieceRenderer
from .errors import RendererStartupError
from .mode import RendererMode


def create_piece_renderer(mode: RendererMode) -> PieceRenderer:
    """Construct exactly the requested renderer mode."""

    if mode is RendererMode.PIXEL_MASK:
        from .pixel_mask import build_pixel_mask_renderer

        return build_pixel_mask_renderer()
    if mode is RendererMode.UNICODE:
        from .unicode import build_unicode_renderer

        return build_unicode_renderer()
    if mode is RendererMode.LEGACY_SPRITE:
        from .legacy_sprite import build_legacy_sprite_renderer

        return build_legacy_sprite_renderer()
    raise RendererStartupError(f"Unsupported renderer mode: {mode!r}.")
