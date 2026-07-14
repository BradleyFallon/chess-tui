#!/usr/bin/env python3
"""Verify the environment can import the package and parse the default FEN."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def project_root() -> Path:
    root = os.environ.get("PROJECT_ROOT")
    if root:
        return Path(root).expanduser().resolve()
    return Path(__file__).resolve().parents[1]


def python_executable(root: Path) -> str:
    venv_python = root / "venv" / "bin" / "python"
    if venv_python.exists():
        return str(venv_python)
    nested_venv_python = root / "src" / "venv" / "bin" / "python"
    if nested_venv_python.exists():
        return str(nested_venv_python)
    return sys.executable


def main() -> int:
    root = project_root()
    python = python_executable(root)
    console_script = root / "venv" / "bin" / "chess-tui"
    if not console_script.exists():
        raise SystemExit(
            "Missing chess-tui console script. Run update-deps to install the project."
        )

    subprocess.run([python, "-m", "pip", "check"], check=True)
    subprocess.run(
        [
            python,
            "-c",
            "from chess_tui import DEFAULT_STARTING_FEN, __version__, parse_fen; "
            "position = parse_fen(DEFAULT_STARTING_FEN); "
            "assert position.active_color == 'w'; "
            "print(f'Chess TUI {__version__} is ready.')",
        ],
        check=True,
    )
    subprocess.run([str(console_script), "--version"], check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
