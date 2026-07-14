"""Command-line interface for the Chess TUI package."""

from __future__ import annotations

import argparse
import sys

from . import DEFAULT_STARTING_FEN, __version__
from .board import FenError, parse_fen
from .runtime import RuntimeRequirementError, validate_textual_runtime


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
        "--pieces",
        choices=("pixel", "figurine"),
        default="pixel",
        help="Piece rendering mode (defaults to pixel).",
    )
    parser.add_argument(
        "--version",
        action="store_true",
        help="Print the package version and exit",
    )
    return parser


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

    try:
        validate_textual_runtime(sys.stdout)
        from .tui import run_chess_app

        run_chess_app(position, piece_mode=args.pieces)
    except RuntimeRequirementError as exc:
        parser.exit(2, f"{parser.prog}: error: {exc}\n")
    return 0
