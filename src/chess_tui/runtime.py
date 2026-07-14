"""Strict runtime requirements for the Textual application."""

from __future__ import annotations

import codecs
from importlib.metadata import PackageNotFoundError, version
from typing import TextIO

from .renderers.base import PieceRenderer
from .renderers.errors import RendererStartupError
from .renderers.factory import create_piece_renderer
from .renderers.mode import RendererMode

REQUIRED_TEXTUAL_VERSION = "8.2.8"
REQUIRED_RICH_VERSION = "15.0.0"
REQUIRED_CHESSNUT_VERSION = "0.4.1"


class RuntimeRequirementError(RuntimeError):
    """Raised when the runtime cannot faithfully display the application."""


class TerminalCapabilityError(RuntimeRequirementError):
    """Raised when the terminal does not provide a required capability."""


def validate_textual_runtime(
    stream: TextIO,
    *,
    renderer_mode: RendererMode | str | None = None,
) -> PieceRenderer | None:
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

    if renderer_mode is None:
        return None

    try:
        mode = (
            renderer_mode
            if isinstance(renderer_mode, RendererMode)
            else RendererMode(renderer_mode)
        )
    except ValueError as exc:
        raise RuntimeRequirementError(
            f"Unsupported renderer mode: {renderer_mode!r}."
        ) from exc

    try:
        return create_piece_renderer(mode)
    except RendererStartupError as exc:
        raise RuntimeRequirementError(str(exc)) from exc


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
