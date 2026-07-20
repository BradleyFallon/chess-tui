# Chess TUI

Chess TUI contains a Python-owned Opening Rule Engine for training and
developing deterministic opening Rulebooks. Version 4 organizes policy around
original pieces: one default development instruction per controlled piece,
piece-owned interrupt rules with ordered attempts, and separately authored
development and interrupt order.

In Web Development Mode, click any board piece to inspect its persistent
starting-piece identity and legal attack/defense relationships. Controlled
pieces expose guided development and interrupt authoring; opponent pieces are
read-only condition and capture references. Every change is previewed,
revalidated, saved atomically with backup, and replayed through the shared
Python runtime.

Authored piece references use readable identifiers such as
`piece:white:pawn:d`, `piece:white:bishop:queenside`, and
`piece:black:king`; original-square strings are internal only.

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
for this default path. Black's first deterministic indexed book or engine response is played
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

Development Mode displays the Python-owned board, SAN history, a piece-centered
authoring inspector, a compact current decision, Back/Restart navigation, and
optional Stockfish evaluation. Runtime status, exact conditions, decision
traces, and TOML remain available through Policy details. The analysis options select Blunder check,
Quick, Analysis, or Deep local search at fixed depths 10, 15, 20, or 26.
Current-position and candidate
scores identify the UCI engine and report actual depth, elapsed time, and nodes
when supplied by the engine. Local Stockfish has no API or per-analysis fee;
deeper and multi-line searches use more local CPU time.

The browser provides complete v4 authoring for default development,
interrupting rules, ordered action attempts, exact-position interrupts, and
semantic scheduling order. Controlled pieces expose move authoring; opponent
pieces are read-only references for conditions and captures. The visual
condition tree includes legal relationship predicates and preserves `unmoved`
as distinct from logical `not moved`. Drafts validate without persistence,
show an impact review, then revalidate, save atomically, replay, and return a
complete snapshot on Apply.
The right-side timeline keeps application activity separate from user/assistant
conversation while displaying both in deterministic sequence order. Python
publishes the commands available in each snapshot and handles SAN, `/analyse`,
`/why`, `/rule`, `/rules`, `/trace`, `/position`, `/opening`, `/openings`,
`/defenses`, `/book`, `/book-history`, `/accept-here`, navigation, hint, and mismatch
commands through the shared command registry. React sends complete chat text or
typed command invocations; it does not parse slash syntax or reproduce command
availability rules. Python remains authoritative for legality, policy,
persistence, replay, analysis, and transient client effects such as hint
highlighting. Web Quiz remains a placeholder and the Textual application remains
supported.

Every committed Development Mode move is followed in the right-hand timeline
by a deterministic “Opening after …” commentary card. Python reports exact and
last-known opening, book alignment, and book-versus-policy provenance. The card
uses one deterministic primary match so ordinary commentary stays concise;
`/openings`, `/defenses`, and `/book` retain the fuller diagnostic views. A
current match can be promoted from its card to a durable flow label. Those
authored `{ ECO, name }` labels appear in the workspace header and are saved in
the flow TOML. The on-screen Development Options area includes a locally
remembered **Auto-respond** toggle; when enabled, the browser invokes the same
Python-owned Next Opponent command immediately after the controlled move, so no
Enter press is required. The browser does not classify positions or choose the
reply itself.

## Bundled opening data

Opening classification and book continuations use one offline position graph
built from a pinned CC0 copy of
[`lichess-org/chess-openings`](https://github.com/lichess-org/chess-openings).
Source provenance is in `data/openings/lichess/VERSION` and `LICENSE`; runtime
startup never downloads data.

To update intentionally, replace the combined `openings.tsv`, license, and full
commit in `VERSION` from one upstream revision, then run:

```bash
source ./activate
python scripts/build_opening_index.py
```

Commit the regenerated
`src/chess_tui/opening/data/lichess-index.json`. The build validates all source
rows and moves and produces stable ordering. The dataset has no popularity
statistics, so the UI reports “Book defenses still reachable” without
frequency or likelihood claims.

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

Flow mode runs a strict version 4 Opening Rulebook. Resolution is
exact-position interrupts, other interrupts in `interrupt_order`, default
development in `development_order`, then a typed frontier. Interrupts are
one-shot and their attempts resolve deterministically from legal moves.

- Play on the board or type SAN. A correct controlled-side move commits
  immediately and advances to the opponent; a mismatch supports `R`/`Escape`
  to retry and `Enter` to use the selected policy move.
- The Textual side panel shows the selected rule, note, and full decision trace.
  Edit v4 piece scripts in local Web Development Mode or directly in TOML, then use
  `Ctrl+R` to validate and deterministically replay the active line.
- On the opponent turn, normal mode automatically plays the first indexed book
  or Stockfish response. `--select-black` restores interactive selection and
  manual board/SAN entry. Recorded replies are branch data, never policy rules.
- The advantage bar and mismatch engine review are White-normalized; mate
  scores remain separate and engine advice never edits policy.
- Web Development Mode shows the engine identity and measured search work with
  current-position and candidate-move evaluations.
- `Ctrl+N` restarts, `I` focuses SAN entry, `Escape` leaves text entry or retries
  a pending result, and `Q` quits from navigation mode.

Versions other than 4 are rejected with no compatibility loader. Saves are
atomic and preserve the previous file as `<flow>.bak`; Back and Restart rebuild
original-piece and completion state by replaying SAN without deleting rules or
explored branches.

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
- `src/chess_tui/commands/` - defines backend command identities, slash aliases,
  typed invocations, availability predicates, outcomes, and client effects.
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
