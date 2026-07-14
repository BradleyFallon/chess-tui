"""Command-line interface for the Chess TUI package."""

from __future__ import annotations

import argparse
import os
import sys

from . import DEFAULT_STARTING_FEN, __version__
from .board import FenError, parse_fen
from .renderers.mode import RendererMode
from .runtime import RuntimeRequirementError, validate_textual_runtime
from .tui import run_chess_app


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="chess-tui",
        description="Render a chess position from FEN in the terminal.",
    )
    parser.add_argument(
        "--fen",
        default=DEFAULT_STARTING_FEN,
        help="FEN string to render (defaults to the standard starting position).",
    )
    parser.add_argument(
        "--renderer",
        choices=[mode.value for mode in RendererMode],
        default=None,
        help=(
            "Piece renderer mode (defaults to the CHESS_TUI_RENDERER "
            "environment variable or pixel-mask)."
        ),
    )
    parser.add_argument(
        "--version",
        action="store_true",
        help="Print the package version and exit",
    )
    return parser


def _resolve_renderer_mode(
    value: str | None, parser: argparse.ArgumentParser
) -> RendererMode:
    candidate = value or os.environ.get(
        "CHESS_TUI_RENDERER", RendererMode.PIXEL_MASK.value
    )
    try:
        return RendererMode(candidate)
    except ValueError:
        parser.exit(
            2,
            f"{parser.prog}: error: invalid renderer mode {candidate!r}. "
            f"Supported modes: {', '.join(mode.value for mode in RendererMode)}\n",
        )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.version:
        print(__version__)
        return 0

    try:
        position = parse_fen(args.fen)
    except FenError as exc:
        parser.error(str(exc))

    renderer_mode = _resolve_renderer_mode(args.renderer, parser)

    try:
        renderer = validate_textual_runtime(
            sys.stdout,
            renderer_mode=renderer_mode,
        )
        run_chess_app(position, renderer=renderer)
    except RuntimeRequirementError as exc:
        parser.exit(2, f"{parser.prog}: error: {exc}\n")
    return 0
