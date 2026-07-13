# Chess TUI

A clean starting point for a Python package + CLI project.

## Quick start

```bash
source ./activate
chess-tui --help
```

## Project tree

Copy this block when providing the project structure to an LLM:

```text
.
|-- .gitignore                         # Generated files excluded from Git
|-- .vscode/                           # Shared VS Code project settings
|   |-- extensions.json                # Recommended Python extensions
|   `-- settings.json                  # Interpreter, tests, and import paths
|-- AGENTS.md                          # Instructions for coding agents
|-- LICENSE                            # Project license
|-- README.md                          # Project overview and setup guide
|-- activate                           # Development environment activation
|-- devtools/
|   `-- aliases.sh                     # Shell aliases loaded by activate
|-- docs/
|   `-- README.md                      # Starting point for detailed docs
|-- pyproject.toml                     # Package, build, and tool configuration
|-- requirements.txt                  # Development dependency install list
|-- scripts/
|   `-- chess-tui.py            # Direct development CLI wrapper
|-- src/
|   `-- chess_tui/              # Installable application package
|       |-- __init__.py                # Public API and package version
|       |-- __main__.py                # python -m entry point
|       |-- cli.py                     # Command-line interface
|       `-- output_schema.json         # Optional structured-output schema
|-- tests/
|   `-- test_smoke.py                  # Minimal package behavior tests
|-- tox.ini                            # Multi-version test environments
`-- venv/                              # Generated local Python environment
```

## Project file guide

- `pyproject.toml` - the main Python project configuration. It defines package
  metadata, build settings, dependencies, the `chess-tui` command, and
  settings used by tools such as pytest.
- `requirements.txt` - a pip-compatible list of development tools. It provides
  a simple `pip install -r requirements.txt` setup path; runtime dependencies
  belong in `pyproject.toml`.
- `tox.ini` - tells tox how to run the test suite in isolated environments for
  Python 3.10, 3.11, and 3.12. Those Python versions must be installed locally
  for every tox environment to run.
- `activate` - activates this project's `venv/`, sets `PROJECT_ROOT` and
  `PYTHONPATH`, and loads the development aliases. Source this file rather than
  running it as a separate process.
- `.gitignore` - keeps generated environments, caches, test output, and build
  artifacts out of version control.
- `.vscode/` - recommends the Python development extensions and gives VS Code
  the project's interpreter, import path, formatter, and test settings.
- `AGENTS.md` - gives coding agents and automation tools a concise description
  of the repository's conventions and common commands.
- `LICENSE` - states the legal terms under which the project may be used and
  distributed.
- `src/chess_tui/` - the installable Python package. Using a `src/`
  layout prevents tests from accidentally importing an uninstalled copy from
  the repository root.
- `src/chess_tui/__init__.py` - marks the directory as a package and
  exposes its small public API and version.
- `src/chess_tui/__main__.py` - makes
  `python -m chess_tui` invoke the command-line interface.
- `src/chess_tui/cli.py` - defines command-line arguments and the CLI's
  `main()` function.
- `src/chess_tui/output_schema.json` - a packaged placeholder for
  project-specific structured-output metadata; replace or remove it if the
  project does not need a schema.
- `scripts/chess-tui.py` - a directly executable development wrapper for
  the same CLI exposed after package installation.
- `devtools/aliases.sh` - defines convenience shell aliases loaded by
  `activate`.
- `tests/test_smoke.py` - a minimal test proving the generated package can be
  imported and its starter behavior works.
- `docs/` - a home for longer documentation that does not belong in this
  overview.
- `venv/` - the generated, local Python environment. It is machine-specific,
  ignored by Git, and should be recreated instead of copied or committed.

## Customize me

- Replace the placeholder `greet` function with your real logic.
- Add dependencies under `[project.dependencies]` in `pyproject.toml`.
