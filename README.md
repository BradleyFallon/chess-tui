# Chess TUI

A strict Textual chess board viewer that renders FEN positions as a colored
checkerboard with centered Unicode pieces.

## Quick start

```bash
source ./activate
update-deps
chess-tui --help
chess-tui --fen "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
```

Run `update-deps` after changing `pyproject.toml`. It installs the project in
editable mode with its `dev` dependencies and finishes with `pip check`.

`activate` creates the virtual environment if needed, keeps it aligned with
`requirements.txt`, and loads the shell aliases.

Press `q` to exit the viewer.

## Runtime contract

The viewer deliberately has no degraded rendering mode. Startup fails with an
error unless all of these requirements are met:

- Textual 8.2.8 and Rich 15.0.0 are installed.
- Standard output is an interactive UTF-8 TTY.
- Every Unicode chess symbol occupies exactly one terminal cell.
- The calculated centered board fits in the terminal.
- When the terminal reports pixel dimensions, its calculated square aspect
  ratio is within the required tolerance.

Terminals such as VS Code that do not report pixel dimensions use a fixed
centered 5x3-cell square geometry. This is a supported rendering mode, not a
plain-text fallback. Redirected output is unsupported. Terminal applications
cannot query whether a selected font visually contains a Unicode glyph; use a
terminal font that includes the standard chess symbols.

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
|   |-- chess-tui.py               # Direct development CLI wrapper
|   |-- check-setup.py              # Verify the environment and package import
|   `-- fix-deps.py                 # Install missing or outdated dependencies
|-- src/
|   `-- chess_tui/              # Installable application package
|       |-- __init__.py                # Public API and package version
|       |-- __main__.py                # python -m entry point
|       |-- board.py                   # FEN parsing and chess symbols
|       |-- cli.py                     # Command-line interface
|       |-- runtime.py                 # Strict dependency/capability checks
|       |-- tui.py                     # Textual board widget and application
|       `-- output_schema.json         # Optional structured-output schema
|-- tests/
|   |-- fixtures/
|   |   `-- fens.json                  # Sample positions used by tests
|   |-- test_board.py                 # FEN parsing and rendering coverage
|   `-- test_smoke.py                 # Minimal package behavior tests
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
- `activate` - activates this project's `venv/`, creates it if needed, sets
  `PROJECT_ROOT` and `PYTHONPATH`, synchronizes dependencies from
  `requirements.txt`, and loads the development aliases. Source this file
  rather than running it as a separate process.
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
- `src/chess_tui/runtime.py` - validates the pinned UI dependencies, UTF-8 TTY,
  and Unicode cell widths before the application starts.
- `src/chess_tui/tui.py` - implements the Textual line-rendered chess board,
  cell-based geometry with optional pixel-aware sizing, and strict terminal
  capability checks.
- `src/chess_tui/output_schema.json` - a packaged placeholder for
  project-specific structured-output metadata; replace or remove it if the
  project does not need a schema.
- `scripts/chess-tui.py` - a directly executable development wrapper for
  the same CLI exposed after package installation.
- `devtools/aliases.sh` - defines convenience shell aliases loaded by
  `activate`. It includes `fix-deps` and `install-missing-packages` for
  dependency repair.
- `tests/test_smoke.py` - a minimal test proving the generated package can be
  imported and its starter behavior works.
- `docs/` - a home for longer documentation that does not belong in this
  overview.
- `venv/` - the generated, local Python environment. It is machine-specific,
  ignored by Git, and should be recreated instead of copied or committed.

## Customize me

- Use `chess_tui.parse_fen()` to validate and normalize FEN strings.
- The CLI accepts `--fen` and opens the standard starting position by default.
- Add dependencies under `[project.dependencies]` in `pyproject.toml`.
