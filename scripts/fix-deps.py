#!/usr/bin/env python3
"""Install or update this project and all development dependencies."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


def project_root() -> Path:
    root = os.environ.get("PROJECT_ROOT")
    if root:
        return Path(root).expanduser().resolve()
    return Path(__file__).resolve().parents[1]


def ensure_venv(root: Path) -> Path:
    venv_python = root / "venv" / "bin" / "python"
    nested_venv_python = root / "src" / "venv" / "bin" / "python"
    if venv_python.exists():
        return venv_python
    if nested_venv_python.exists():
        return nested_venv_python

    creator = shutil.which("python3") or shutil.which("python")
    if creator is None:
        raise SystemExit(
            "Python not found. Install Python 3 to create a virtual environment."
        )

    subprocess.run([creator, "-m", "venv", str(root / "venv")], check=True)
    return root / "venv" / "bin" / "python"


def main() -> int:
    root = project_root()
    pyproject = root / "pyproject.toml"
    if not pyproject.exists():
        raise SystemExit(f"Missing project configuration: {pyproject}")

    python = ensure_venv(root)
    print(f"Updating dependencies with {python}...", flush=True)
    install = subprocess.run(
        [
            str(python),
            "-m",
            "pip",
            "install",
            "--upgrade",
            "--editable",
            f"{root}[dev]",
        ],
        check=False,
    )
    if install.returncode != 0:
        return install.returncode

    return subprocess.run(
        [str(python), "-m", "pip", "check"],
        check=False,
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
