"""Command-line interface for the Chess TUI package."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import sys

from . import DEFAULT_STARTING_FEN, __version__
from .board import FenError, parse_fen
from .engine import EngineError, validate_engine_path
from .flow import FlowError
from .modes import AppMode
from .renderers.mode import RendererMode
from .runtime import RuntimeRequirementError, validate_textual_runtime
from .tui import run_chess_app

DEFAULT_FLOW_DIRECTORY = Path("flows")


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
        default=AppMode.FLOW.value,
        help="Application mode (defaults to flow).",
    )
    parser.add_argument(
        "--flow",
        type=Path,
        default=None,
        help="White-flow TOML file (defaults to the most recently saved flow).",
    )
    parser.add_argument(
        "--engine",
        type=Path,
        default=None,
        help=(
            "Explicit Stockfish executable path (flow mode only; defaults to "
            "stockfish from PATH)."
        ),
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


def _most_recent_flow(parser: argparse.ArgumentParser) -> Path:
    candidates: list[tuple[int, Path]] = []
    try:
        flow_paths = DEFAULT_FLOW_DIRECTORY.glob("*.toml")
        for path in flow_paths:
            try:
                candidates.append((path.stat().st_mtime_ns, path))
            except OSError:
                continue
    except OSError:
        candidates = []
    if not candidates:
        parser.error(
            f"no saved flow files were found in {DEFAULT_FLOW_DIRECTORY}; "
            "pass --flow PATH"
        )
    return max(candidates, key=lambda item: (item[0], item[1].name))[1]


def _flow_engine_path(
    value: Path | None,
    parser: argparse.ArgumentParser,
) -> Path:
    candidate = value
    if candidate is None:
        discovered = shutil.which("stockfish")
        if discovered is None:
            parser.error(
                "Stockfish is required for flow mode but was not found in PATH; "
                "install Stockfish or pass --engine PATH"
            )
        candidate = Path(discovered)
    try:
        return validate_engine_path(candidate)
    except EngineError as exc:
        parser.error(str(exc))


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.version:
        print(__version__)
        return 0

    mode = AppMode(args.mode)
    if mode is not AppMode.FLOW and args.flow is not None:
        parser.error("--flow is only supported with --mode flow")
    if mode is not AppMode.FLOW and args.engine is not None:
        parser.error("--engine is only supported with --mode flow")
    if mode is AppMode.FLOW:
        args.flow = args.flow or _most_recent_flow(parser)
        args.engine = _flow_engine_path(args.engine, parser)

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
            run_chess_app(
                position,
                renderer=renderer,
                mode=mode,
                flow_path=args.flow,
                engine_path=args.engine,
            )
        else:
            run_chess_app(position, renderer=renderer, mode=mode)
    except (RuntimeRequirementError, FlowError, EngineError) as exc:
        parser.exit(2, f"{parser.prog}: error: {exc}\n")
    return 0
