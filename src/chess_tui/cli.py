"""Command-line interface for the Chess TUI package."""

from __future__ import annotations

import argparse

from . import __version__, greet


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="chess-tui",
        description="Starter CLI for the Chess TUI project.",
    )
    parser.add_argument("name", nargs="?", default="world", help="Name to greet")
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
    print(greet(args.name))
    return 0
