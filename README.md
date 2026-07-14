# Chess TUI

An interactive Textual chess board that loads FEN positions, highlights legal
moves, and renders chess pieces on a responsive checkerboard.

## Quick start

```bash
source ./activate
update-deps
chess-tui --help
chess-tui --mode local-game
chess-tui --mode quiz-demo
chess-tui --renderer pixel-mask
chess-tui --renderer unicode
chess-tui --renderer legacy-sprite
chess-tui --fen "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
```

Run `update-deps` after changing `pyproject.toml`. It installs the project in
editable mode with its `dev` dependencies and finishes with `pip check`.

`activate` creates the virtual environment if needed, keeps it aligned with
`requirements.txt`, and loads the shell aliases.

After activation, `chess-tui` resolves to the installed console script at
`venv/bin/chess-tui`, which runs `chess_tui.cli:main` from the editable source.

Application mode and renderer mode are independent, so combinations such as
`chess-tui --mode quiz-demo --renderer unicode` are supported.

## Local-game controls

- Click a piece to select it and show its legal destinations.
- Click a highlighted destination to create a pending move.
- Press `Enter` to confirm a pending move.
- Press `Escape` to cancel selection or a pending move.
- Press `F` to flip the board.
- Press `Q` to quit.

## Quiz-demo controls

- Press `A`, `S`, `D`, or `F` to highlight a move without submitting it.
- Press `Up` or `Down` to move the highlight and `Enter` to confirm.
- Hover a move to highlight it or click it to submit it.
- Correct answers advance automatically after 600 ms; `Enter` skips the delay.
- Mismatches show the canonical answer and wait for `Enter`.
- Press `L` to switch between the packaged London and Caro-Kann demo flows.
- At the frontier, press `A` for the unsaved mock continuation form, `S` to
  restart, or `F` to exit.

Quiz demo data is local and read-only. It does not start, connect to, or persist
data in ChessFlow.

## Runtime contract

The viewer validates its rendering modes strictly. Startup fails with an error
unless all of these requirements are met:

- Chessnut 0.4.1, Textual 8.2.8, and Rich 15.0.0 are installed.
- Standard output is an interactive UTF-8 TTY.
- The selected renderer's glyphs or masks pass strict startup validation.
- `pixel-mask` requires at least 67 columns by 35 rows, including the status line.
- The selected renderer is one of `pixel-mask`, `unicode`, or `legacy-sprite`.
- The selected application mode is `local-game` or `quiz-demo`.
- The CLI flag `--renderer` overrides `CHESS_TUI_RENDERER`; the default mode is
  `pixel-mask`.

The `pixel-mask` renderer uses fixed 8x8 pixel masks mapped directly to 8x4
terminal-cell squares and never scales. When the terminal cannot fit its 67x35
layout, the application automatically uses responsive Unicode rendering and
restores `pixel-mask` when enough space is available again. Explicit `unicode`
and `legacy-sprite` selections do not switch modes. The responsive renderers
choose from 7x3, 5x2, and 3x1-cell presets. Reported pixel dimensions improve
their aspect selection but are optional. If even the Unicode board is too
large, the application displays the exact size requirement and recovers when
resized. Retro artwork and both piece palettes are stored in
`src/chess_tui/assets/pieces/retro-8.toml`. Masks use `_` for transparency, `A`
for outline/shadow, and `B` for fill/highlight. Each side defines only its `A`
and `B` colors. Redirected output is unsupported.
Terminal applications cannot query whether a selected font visually contains a
Unicode glyph; use a terminal font that includes the standard chess and
block-drawing symbols.

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
|       |-- board.py                   # FEN parsing and board helpers
|       |-- cli.py                     # Command-line interface
|       |-- game.py                    # Legal moves and interaction state
|       |-- modes.py                   # Top-level application modes
|       |-- screens/                   # Local-game and quiz screens
|       |-- sessions/                  # Quiz presentation models and providers
|       |-- widgets/                   # Reusable quiz interaction widgets
|       |-- view.py                    # Renderer-neutral board display state
|       |-- renderers/                 # Explicit piece renderer modes
|       |-- runtime.py                 # Strict dependency/capability checks
|       |-- tui.py                     # Textual board widget and application
|       `-- assets/                    # Packaged retro text masks and assets
|       `-- output_schema.json         # Optional structured-output schema
|-- tests/
|   |-- fixtures/
|   |   `-- fens.json                  # Sample positions used by tests
|   |-- test_board.py                 # FEN parsing and rendering coverage
|   |-- test_game.py                  # Move controller coverage
|   |-- test_quiz.py                  # Quiz screen and widget behavior
|   |-- test_sessions.py              # Fixture provider and model validation
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
- `src/chess_tui/game.py` - adapts Chessnut into typed move and interaction
  state without coupling chess legality to the renderer.
- `src/chess_tui/view.py` - defines immutable board presentation state shared
  by local-game and quiz providers.
- `src/chess_tui/sessions/` - defines the narrow quiz provider protocol,
  presentation models, strict errors, and packaged fixture implementation.
- `src/chess_tui/screens/` - contains independent local-game and quiz UI state
  machines selected by the application shell.
- `src/chess_tui/runtime.py` - validates the pinned UI dependencies, UTF-8 TTY,
  and Unicode cell widths before the application starts.
- `src/chess_tui/tui.py` - implements the Textual line-rendered chess board,
  responsive geometry, pointer mapping, keyboard actions, and layered square
  styling.
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
- The CLI accepts `--mode`, `--renderer`, and `--fen`; local-game opens the
  standard starting position by default.
- Add dependencies under `[project.dependencies]` in `pyproject.toml`.
