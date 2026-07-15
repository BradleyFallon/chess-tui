"""Command-line interface for the Chess TUI package."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

from . import DEFAULT_STARTING_FEN, __version__
from .board import FenError, parse_fen
from .flow import FlowError
from .modes import AppMode
from .renderers.mode import RendererMode
from .runtime import RuntimeRequirementError, validate_textual_runtime
from .tui import run_chess_app


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="chess-tui",
        description="Play local chess or test and edit a White flow.",
    )
    parser.add_argument(
        "--fen",
        default=DEFAULT_STARTING_FEN,
        help=("Local-game FEN to render (defaults to the standard starting position)."),
    )
    parser.add_argument(
        "--mode",
        choices=[mode.value for mode in AppMode],
        default=AppMode.LOCAL_GAME.value,
        help="Application mode (defaults to local-game).",
    )
    parser.add_argument(
        "--flow",
        type=Path,
        default=None,
        help="White-flow TOML file (required for flow mode).",
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

    mode = AppMode(args.mode)
    if mode is AppMode.FLOW and args.flow is None:
        parser.error("--flow is required when --mode flow is selected")
    if mode is not AppMode.FLOW and args.flow is not None:
        parser.error("--flow is only supported with --mode flow")

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
        if mode is AppMode.FLOW:
            run_chess_app(position, renderer=renderer, mode=mode, flow_path=args.flow)
        else:
            run_chess_app(position, renderer=renderer, mode=mode)
    except (RuntimeRequirementError, FlowError) as exc:
        parser.exit(2, f"{parser.prog}: error: {exc}\n")
    return 0
