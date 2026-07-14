"""Strict runtime requirements for the Textual application."""

from __future__ import annotations

import codecs
from importlib.metadata import PackageNotFoundError, version
from typing import TextIO

from .board import PIECE_GLYPHS, PIECE_SPRITES, PIXEL_SPRITE_WIDTH

REQUIRED_TEXTUAL_VERSION = "8.2.8"
REQUIRED_RICH_VERSION = "15.0.0"
REQUIRED_CHESSNUT_VERSION = "0.4.1"


class RuntimeRequirementError(RuntimeError):
    """Raised when the runtime cannot faithfully display the application."""


class TerminalCapabilityError(RuntimeRequirementError):
    """Raised when the terminal does not provide a required capability."""


def validate_textual_runtime(stream: TextIO) -> None:
    """Require the exact UI stack and terminal text capabilities."""

    _require_distribution("rich", REQUIRED_RICH_VERSION)
    _require_distribution("textual", REQUIRED_TEXTUAL_VERSION)
    _require_distribution("Chessnut", REQUIRED_CHESSNUT_VERSION)

    try:
        import textual
    except ImportError as exc:
        raise RuntimeRequirementError(
            "Textual is installed but could not be imported. Reinstall the project dependencies."
        ) from exc
    if textual.__version__ != REQUIRED_TEXTUAL_VERSION:
        raise RuntimeRequirementError(
            f"Imported Textual reports version {textual.__version__}, but "
            f"{REQUIRED_TEXTUAL_VERSION} is required."
        )

    if not stream.isatty():
        raise TerminalCapabilityError(
            "chess-tui requires an interactive TTY; redirected output is unsupported."
        )

    encoding = stream.encoding
    try:
        normalized_encoding = codecs.lookup(encoding or "").name
    except LookupError as exc:
        raise TerminalCapabilityError(
            f"chess-tui requires UTF-8 output, but the terminal uses {encoding!r}."
        ) from exc
    if normalized_encoding != "utf-8":
        raise TerminalCapabilityError(
            f"chess-tui requires UTF-8 output, but the terminal uses {encoding!r}."
        )

    try:
        from rich.cells import cell_len
    except ImportError as exc:
        raise RuntimeRequirementError(
            "Rich is installed but could not be imported. Reinstall the project dependencies."
        ) from exc

    invalid_glyphs = [glyph for glyph in PIECE_GLYPHS.values() if cell_len(glyph) != 1]
    if invalid_glyphs:
        rendered = ", ".join(repr(glyph) for glyph in invalid_glyphs)
        raise TerminalCapabilityError(
            f"Chess symbols must occupy exactly one terminal cell; invalid: {rendered}."
        )

    invalid_sprite_rows = [
        row
        for sprite in PIECE_SPRITES.values()
        for row in sprite
        if cell_len(row) != PIXEL_SPRITE_WIDTH
    ]
    if invalid_sprite_rows:
        rendered = ", ".join(repr(row) for row in invalid_sprite_rows)
        raise TerminalCapabilityError(
            f"Pixel sprite rows must occupy exactly {PIXEL_SPRITE_WIDTH} terminal "
            f"cells; invalid: {rendered}."
        )


def _require_distribution(package: str, required_version: str) -> None:
    """Require an installed package to match its supported version exactly."""

    display_name = package.capitalize()
    try:
        installed_version = version(package)
    except PackageNotFoundError as exc:
        raise RuntimeRequirementError(
            f"{display_name} {required_version} is required. "
            "Install the project dependencies before running chess-tui."
        ) from exc

    if installed_version != required_version:
        raise RuntimeRequirementError(
            f"{display_name} {required_version} is required, but "
            f"{installed_version} is installed."
        )
