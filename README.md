# Chess TUI

An interactive Textual chess board that loads FEN positions, highlights legal
moves, and renders chess pieces on a responsive checkerboard.

## Quick start

```bash
source ./activate
update-deps
chess-tui --help
chess-tui
chess-tui --mode local-game
chess-tui --mode quiz-demo
chess-tui --mode flow --flow flows/london.toml
chess-tui --mode flow --flow flows/london.toml --engine /path/to/stockfish
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

With no arguments, `chess-tui` starts flow mode with the most recently saved
`flows/*.toml` file and the `stockfish` executable found in `PATH`. London is
currently the most recently saved flow. Startup fails clearly if no saved flow
or Stockfish executable is available; the deterministic prototype is not used
for this default path. Black's first ranked book or engine response is played
automatically. `--flow` and `--engine` remain explicit overrides, and
`--select-black` restores the suggestion selector.

## Local web Development Mode

Build the browser application and start the local FastAPI server with:

```bash
cd web
npm install
npm run build
cd ..

chess-tui web \
  --flow flows/london.toml \
  --engine "$(command -v stockfish)"
```

The server binds to `127.0.0.1:8765` and opens a browser by default. Use
`--no-browser`, `--host`, or `--port` to change those server options. Unlike the
default Textual flow, the web workspace may omit `--engine`; evaluation then
shows `engine-off` and never substitutes fixture analysis.

Development Mode displays the Python-owned board, SAN history, current
legacy-v1 recommendation, White result, Back/Restart navigation, and optional
Stockfish evaluation. White and Black moves travel as UCI over HTTP, but Python
remains authoritative for legality, SAN, policy, persistence, replay, and
analysis. Web Quiz is a placeholder, while web rule editing and version 2
abstract rules remain deferred. The Textual application remains supported.

For two-process frontend development:

```bash
fastapi dev src/chess_tui/web/app.py --port 8000

cd web
npm run dev
```

Vite proxies `/api` to `http://127.0.0.1:8000`.

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
- After a mismatch, press `E` to make the selected move correct for the current
  quiz session.
- Press `L` to switch between the packaged London and Caro-Kann demo flows.
- At the frontier, press `A` to set a default response after any opponent move.
- After setting the default, press `A` to add an exception for one specific
  opponent move or `D` to edit the default. These preview rules are unsaved.
- Continuation fields open inline beside or below the board; the board remains
  visible while editing.
- Press `S` to restart from the frontier or `F` to exit.

Quiz demo data is local and read-only. It does not start, connect to, or persist
data in ChessFlow.

## Flow controls

Flow mode tests and edits one local White-flow TOML file. White recommendations
resolve an exact-position exception first, then the numbered default for that
White step.

- When a White rule exists, play without seeing its move or note. Correct moves
  reveal the saved rule briefly, then continue to Black's response.
- On a mismatch, press `R` to retry or `Enter` to roll back the attempted move,
  apply the saved rule, and continue. Press `E` to make the move an exception,
  `D` to replace the numbered default, or `N` to edit the saved note. Exception
  mismatches also support `X` to replace the exception and `Delete` to remove it.
  When `--engine` is configured, the mismatch also receives a White-normalized
  engine review with `BEST`, `GOOD`, `INACCURACY`, `MISTAKE`, or `BLUNDER`, its
  centipawn loss, and the engine's best move. This advice never edits the flow.
- At the flow frontier, play the desired move, enter its note, and save it as the
  next default. If the numbered default is illegal in the current position, the
  legal move is saved as an exact-position exception instead.
- Play on the board and press `Enter` after highlighting the destination; board
  selection autofills the SAN field. You can also type SAN and press `Enter`.
- On Black's turn, the first ranked book response is played automatically; when
  book data ends, Stockfish supplies and plays one response. Engine failures
  remain visible and support retry or manual entry; they never fall back
  silently. Launch with `--select-black` to show source-labelled suggestion
  rows and explored state instead. In selector mode use `Up`/`Down` or
  `A`/`S`/`D`/`F` and press `Enter`; press `M` for manual board entry or `I` to
  type SAN.
- Completed positions enter `GAME OVER` with the termination and result instead
  of requesting another move. Press `R` to restart the flow or `Q` to quit.
- A live Black/White advantage bar tracks each committed flow position using
  the configured Stockfish service. Scores are normalized to White and display
  pawn advantage, forced mate, draw, or final result without analysing hover,
  selection, or other uncommitted board interactions.
- Default flow interaction starts in `[TEXT: MOVE]` with the SAN field focused;
  printable keys are literal until `Enter` submits. Press `Escape` to return to
  `[NAV]` for board controls and shortcuts, and press `I` to focus SAN entry
  again.
- Rule notes open in `[TEXT: NOTE]`. `Enter` finishes text entry, then `S` saves
  the selected rule action.
- `R` restarts the line from the flow's starting FEN; `Ctrl+N` remains an alias.
- `Ctrl+R` reloads and validates hand edits without discarding the active policy
  when the file is invalid.
- `Escape` leaves text mode or cancels a pending move or rule decision. `Q`
  quits in NAV mode and types a literal `q` in TEXT mode.
- A minimal debug line shows the current Flow phase, turn, White step, ply,
  active rule source, and error state.

Flow files store readable SAN histories and explored Black replies. Opening
counts, frequencies, bot profiles, and suggestion labels remain source data and
are not persisted. The prototype bot is deterministic infrastructure, not a
realistic strength or Elo model. Position matching derives piece placement,
side to move, castling rights, and en-passant state while ignoring move clocks.
Saves are atomic and preserve the previous file as `<flow>.bak`; generated
backup files are ignored by Git.

## Runtime contract

The viewer validates its rendering modes strictly. Startup fails with an error
unless all of these requirements are met:

- python-chess 1.999, Textual 8.2.8, and Rich 15.0.0 are installed.
- Standard output is an interactive UTF-8 TTY.
- The selected renderer's glyphs or masks pass strict startup validation.
- `pixel-mask` requires at least 67 columns by 35 rows, including the status line.
- The selected renderer is one of `pixel-mask`, `unicode`, or `legacy-sprite`.
- The selected application mode is `local-game`, `quiz-demo`, or `flow`.
- The default application mode is `flow`; it requires Stockfish from `PATH` or
  an explicit `--engine` executable.
- The CLI flag `--renderer` overrides `CHESS_TUI_RENDERER`; the default mode is
  `pixel-mask`.

The `pixel-mask` renderer uses fixed 8x8 pixel masks mapped directly to 8x4
terminal-cell squares and never scales. Chess TUI responds to terminal
dimensions by selecting a landscape, portrait, or compact quiz arrangement. It
never changes the selected piece renderer automatically. When that renderer
cannot fit, the current game or quiz session remains intact and resumes after
the terminal is enlarged. The responsive renderers choose from 7x3, 5x2, and
3x1-cell presets. Reported pixel dimensions improve their aspect selection but
are optional. Retro artwork and both piece palettes are stored in
`src/chess_tui/assets/pieces/retro-8.toml`. Masks use `_` for transparency, `A`
for outline/shadow, and `B` for fill/highlight. Each side defines only its `A`
and `B` colors. Redirected output is unsupported.
Terminal applications cannot query whether a selected font visually contains a
Unicode glyph; use a terminal font that includes the standard chess and
block-drawing symbols.

Quiz layouts use the board and controls side by side in landscape mode, place
the controls below the board in portrait mode, and show condensed choices in
compact mode. A terminal that cannot fit the compact arrangement displays the
selected renderer's resize requirement without discarding session state.

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
|   |-- README.md                      # Starting point for detailed docs
|   `-- design/                        # Policy and web design specifications
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
|       |-- flow/                      # Persistent White-flow policy and storage
|       |-- web/                       # FastAPI app, sessions, models, and server
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
|   |-- test_flow.py                  # Persistent flow policy and storage coverage
|   |-- test_author.py                # Flow-screen workflow coverage
|   |-- test_opponent.py              # Deep book-to-bot route coverage
|   |-- test_quiz.py                  # Quiz screen and widget behavior
|   |-- test_sessions.py              # Fixture provider and model validation
|   `-- test_smoke.py                 # Minimal package behavior tests
|-- web/                               # React, TypeScript, and Vite application
|   |-- src/                           # UI, API client, models, and browser tests
|   `-- package.json                   # Frontend scripts and dependencies
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
- `src/chess_tui/game.py` - adapts python-chess into typed move and interaction
  state without coupling chess legality to the renderer.
- `src/chess_tui/view.py` - defines immutable board presentation state shared
  by local-game and quiz providers.
- `src/chess_tui/sessions/` - defines the narrow quiz provider protocol,
  presentation models, strict errors, and packaged fixture implementation.
- `src/chess_tui/opening/` - defines book and bot source protocols, generic move
  suggestions, the book-first opponent planner, and deterministic local data.
- `src/chess_tui/screens/` - contains independent local-game and quiz UI state
  machines selected by the application shell.
- `src/chess_tui/runtime.py` - validates the pinned UI dependencies, UTF-8 TTY,
  and Unicode cell widths before the application starts.
- `src/chess_tui/tui.py` - implements the Textual line-rendered chess board,
  responsive geometry, pointer mapping, keyboard actions, and layered square
  styling.
- `src/chess_tui/web/` - owns FastAPI lifecycle, typed snapshots and errors,
  in-memory sessions, evaluation caching, static serving, and Uvicorn startup.
- `web/` - contains the React/TypeScript client and its Vite, ESLint,
  TypeScript, Vitest, and production-build scripts.
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
- The CLI accepts `--mode`, `--renderer`, and `--fen`; flow mode also accepts
  explicit `--flow` and `--engine` overrides. Local-game opens the standard
  starting position when selected explicitly.
- `chess-tui web` has a compatible command parser and does not require an
  interactive terminal or Textual renderer validation.
- Add dependencies under `[project.dependencies]` in `pyproject.toml`.
