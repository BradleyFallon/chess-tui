# AGENTS.md

Instructions for coding agents working in this repository.

## Project purpose

Chess TUI is a chess opening training and development application.

The project is evolving toward two primary user modes:

1. **Quiz Mode**
   Tests whether the user can follow an opening policy from memory without exposing the underlying rules before the move is submitted.

2. **Flow Development Mode**
   Lets the user explore lines, create and edit deterministic opening policy items, inspect structures, lifecycle, and authored order, navigate backward through positions, and analyze flow coverage and effectiveness with Stockfish.

Both modes must use the same Python chess, policy, flow, persistence, and engine implementations.

## Read before changing code

Before changing rule-policy or flow-schema behavior, read:

* `docs/design/rule-policy-v3.md`

Before changing the local web application or development-mode behavior, read:

* `docs/design/web-development-mode.md`
* `docs/design/opening-classification.md`

Also review:

* `README.md`
* `docs/README.md`
* `pyproject.toml`

The design documents are authoritative for intended behavior. If implementation and design disagree, call out the conflict rather than silently inventing new semantics.

## Architecture boundaries

### Python is authoritative

Python owns:

* Chess legality
* Board state
* Move parsing and SAN generation
* Original-piece identity
* Rule-condition evaluation
* Rule lifecycle
* Authored section and item-order resolution
* Mutually exclusive structure selection
* Exact-position overrides
* Flow replay and Back behavior
* TOML parsing, validation, and persistence
* Stockfish processes and analysis
* Opening and opponent move sources
* Workspace and session state

Do not duplicate these responsibilities in TypeScript.

### Browser code owns presentation

The web frontend may own:

* Page and component layout
* Board interaction presentation
* Forms and editing controls
* Rule list presentation
* Drag-and-drop ordering
* Evaluation visualizations
* Client-side request state
* Calling the Python API

The browser must treat Python responses as the source of truth for legal moves, selected rules, lifecycle state, evaluations, and persisted flow data.

### Shared core

The TUI and web application must call the same core Python services.

Do not create a separate rule implementation for the web UI.

Preferred dependency direction:

```text
TUI / FastAPI routes
        ↓
Workspace and application services
        ↓
Policy, flow, engine, opening, and board core
        ↓
python-chess / Stockfish / TOML storage
```

Screens, routes, and React components should coordinate and display state. They should not contain domain logic that belongs in the core.

## Product invariants

### Piece development authoring

* Authored TOML, conditions, and mutation APIs use
  `piece:<color>:<type>[:<qualifier>]`.
* Pawns use file qualifiers `a` through `h`; rooks, knights, and bishops use
  `queenside` or `kingside`; queens and kings have no qualifier.
* `StartingPieceRef` maps this syntax to internal original-square identity.
  Do not accept original-square strings in authored data.
* `undeveloped` means the original piece exists and has never moved. Track
  developed, captured-undeveloped, and captured-developed separately.
* A `kind = "development"` rule is a typed authored variant compiled into the
  existing `PolicyRule` runtime. Do not create a separate development resolver.
* A development rule retires intrinsically when its assigned piece moves
  anywhere or is captured. Only one development rule may assign a starting
  piece.
* Web Development Mode piece inspection is always active and coexists with move
  selection. Python owns starting-piece identity, mechanical state, rule
  status, and order priorities; React renders the returned snapshot.

### Deterministic flow policy

* A flow controls White or Black explicitly.
* Current persisted opening flows primarily control White.
* Piece identifiers use explicit colors:

  * `piece:white:knight:kingside`
  * `piece:white:bishop:queenside`
  * `piece:black:knight:queenside`
* Do not use relative identifiers such as `us` and `them`.
* A broad rule may match many board states.
* Every move rule specifies exactly one concrete move.
* The policy resolves to exactly one move or a flow frontier.
* There are no multiple equally correct flow moves.
* A move may be strategically reasonable and still be a flow mismatch.

### Rule actions

Abstract rule moves should use original-piece identity and a destination square.

Example:

```toml
move = { piece = "piece:white:pawn:c", to = "c4" }
```

SAN should normally be derived from the current board for display.

Do not make the rule engine choose among several candidate moves.

### Legality

* Move legality is always enforced automatically by Python.
* Legality must not be an authored rule condition.
* Do not add predicates such as `move_legal`.
* An active rule whose configured move is currently illegal is skipped.
* An illegal move does not automatically retire the rule.

### Authored order

* Section order is exact override, response, development, continuation, frontier.
* Within each policy section, the first authored applicable legal item wins.
* There is no numeric priority and no specificity ranking.
* Persisted list order is semantic, visible, and editable.

### Rule lifecycle

Move rules may be:

```text
LOCKED
UNLOCKED
RETIRED
```

* A rule without `unlock_when` begins unlocked.
* Unlocking is latched.
* `when` is live and does not latch.
* Retirement is permanent on the current line.
* Retirement is evaluated before unlocking when both become true at the same transition.
* Successfully executing a move rule retires it.
* Reusable rules are deferred until explicitly designed.

### Structures

* Structures are mutually exclusive on a line.
* Availability is live until selection.
* After each committed move, the first authored available structure whose `selected_when` is true is selected permanently.
* All other structures become rejected.
* Global policy items omit `structures`.
* Before selection, a scoped item participates when at least one listed structure is available.
* After selection, it participates only when the selected structure is listed.

### Resolution order

Policy resolution order is:

```text
1. Exact-position override
2. First applicable response
3. First applicable development assignment
4. First applicable continuation
5. Flow frontier
```

Do not silently change this order.

Versions 1 and 2 and mixed schemas are intentionally unsupported. Do not add a
fallback parser, migration-on-load path, mixed-schema model, or compatibility
resolver.

### Original-piece identity

Original pieces are identified by their square in the flow’s `start_fen`.

The runtime must distinguish:

* Whether an original piece has ever moved
* Where that original piece is currently located
* Whether that original piece has been captured
* The current occupancy of a square

A current board position alone may not be sufficient to reconstruct original-piece identity or latched lifecycle state.

### Replay and Back navigation

Deterministic policy state includes:

```text
Board
+ SAN history
+ original-piece tracker
+ rule lifecycle
```

Back navigation must restore all of these.

Do not implement Back as only `board.pop()` unless the complete policy state is also restored correctly.

Back navigation must not automatically delete persisted rules or explored branches. Navigation and destructive editing are separate actions.

### Persistence

* TOML is the durable flow representation.
* Writes must remain deterministic and reviewable in Git.
* Preserve atomic-save behavior and backups.
* Do not persist transient engine evaluations, source labels, opening frequencies, or runtime lifecycle snapshots in the canonical flow TOML unless a later design explicitly requires it.
* Manual TOML editing must remain supported.
* Reload errors must be explicit and must not silently discard a valid in-memory policy.

### Engine behavior

* Stockfish is optional only where the active mode explicitly permits operation without it.
* An explicitly configured engine failure must remain visible.
* Never silently replace a failed configured engine with a deterministic fixture bot.
* Keep blocking UCI operations off the event loop.
* Serialize access to a shared engine service.
* Close owned engine processes cleanly.
* Normalize evaluations consistently and document the evaluation perspective.
* Keep mate scores separate from ordinary centipawn values.

### Opening classification

* The bundled index built from the pinned `lichess-org/chess-openings` dataset
  is the sole opening-classification and book-sequence source.
* Runtime classification is offline and deterministic. Do not download opening
  data during startup or query an opening API.
* Opening data describes established names and sequences; flow policy describes
  authored decisions. Keep those concepts separate while recording when they
  agree.
* Python owns opening identity, transpositions, continuations, reachable
  defenses, and move provenance. React only renders returned context.
* Opening context belongs to move or branch history. Back, Restart, replay, and
  branch navigation must reproduce it without deleting explored branches.
* The bundled dataset contains no frequency information. Do not call reachable
  defenses likely or invent game counts and popularity percentages.

### Rendering

* Never automatically switch the selected renderer.
* Preserve the active session when the terminal is resized.
* If the selected renderer cannot fit, show the requirement and restore the same renderer and state when space becomes available.

## Product modes

### Quiz Mode

Quiz Mode is for memory training.

It should normally hide:

* The expected move before submission
* Active rule lists
* Priority
* Activation and retirement conditions
* Decision traces
* Engine-best moves
* Position evaluation

After submission, it may show the expected move, the responsible rule, its note, and retry or continuation controls.

Quiz Mode must not modify the flow unless the user explicitly enters an authoring action that is designed and confirmed.

### Flow Development Mode

Development Mode is for authoring and analysis.

It may expose:

* Current flow recommendation
* Active, dormant, and retired rules
* Rule priorities
* Rule lifecycle explanations
* Decision traces
* Exact overrides
* Branch and history navigation
* Stockfish evaluation
* Engine-best alternatives
* Coverage and flow diagnostics
* Rule creation and editing

Development Mode should support experimental play followed by turning an observed move into a deterministic rule.

The primary web authoring surface is piece-centered. Use chess-facing terms
such as Normal development, Special responses, Exact fixes, Recommended now,
Ready, Not ready, Blocked, and Completed. Keep authored IDs, lifecycle,
conditions, trace, and TOML in the advanced Policy details drawer.

Focused edits follow `Edit -> Validate -> Review -> Apply`. Validation must not
persist. Apply revalidates, saves atomically, replays the active line, and
returns a complete snapshot. The visual condition builder and advanced source
must edit one shared condition AST.

Mismatch and frontier attempts both support Accept in this position through
`accept_attempt_as_override` and `/accept-here`. `/add-rule` is unsupported.
Creating a broader response only prefills a reviewed draft; it must not apply a
rule automatically.

## Web application direction

The web application belongs in this repository and shares the Python core.

Recommended structure:

```text
src/chess_tui/
├── flow/
├── policy/
├── engine/
├── opening/
├── web/
└── ...

web/
├── src/
├── package.json
└── ...
```

The initial web architecture is:

```text
React and TypeScript
        ↓ HTTP / JSON
Local FastAPI server
        ↓
Existing Python core
```

The local server may serve the built frontend in production.

Do not add cloud accounts, hosted storage, remote synchronization, or a database unless explicitly requested.

For the initial local application, in-memory development sessions are acceptable. Durable edits belong in the TOML flow file.

## API design expectations

Prefer endpoints that return a coherent workspace snapshot after an operation.

A snapshot may contain:

* FEN
* SAN history
* Side to move
* Expected move
* Selected rule
* Decision trace
* Active rules
* Dormant rules
* Retired rules
* Engine evaluation status
* Current and previous evaluation
* Available navigation actions
* Validation or persistence errors

Do not require the frontend to reconstruct policy state by combining several inconsistent responses.

Use ordinary HTTP for the first vertical slice. Add WebSockets or server-sent events only when live engine updates materially require them.

## Repository layout

Important locations:

```text
src/chess_tui/     Installable Python package
tests/             Python tests
flows/             Persisted opening flows
docs/              Project documentation
docs/design/       Product and architecture specifications
scripts/           Development helper scripts
web/               Browser frontend
```

Keep domain modules focused:

```text
flow/       Schema, storage, authoring, replay-related flow services
policy/     Abstract conditions, lifecycle, original-piece tracking, resolution
engine/     Stockfish and fixture engine services
opening/    Book and opponent move sources
screens/    Textual presentation
web/        FastAPI routes and local web-session coordination
```

Avoid circular imports between presentation and core modules.

## Development environment

Enter the development environment with:

```bash
source ./activate
```

After modifying dependencies:

```bash
update-deps
```

Useful commands:

```bash
chess-tui
check-setup
update-deps
fix-deps
```

When the web frontend exists, document and preserve standard frontend commands such as:

```bash
cd web
npm install
npm run dev
npm run build
npm test
```

Do not assume a globally installed package when it can be declared in the project configuration.

## Required checks

Before completing a Python change, run:

```bash
black --check src tests
ruff check src tests
pyright
pytest
```

Fix all failures.

If frontend code is changed, also run the frontend’s configured:

```bash
npm run lint
npm run typecheck
npm test
npm run build
```

Use the actual scripts declared in `web/package.json`. Do not invent commands that are not configured.

Do not claim checks passed unless they were executed successfully.

## Testing expectations

Add focused tests for new behavior.

### Policy tests should cover

* Parsing and validation
* Original-piece tracking
* `moved`, `at`, occupancy, attack, and named-state conditions
* Latched activation
* Retirement
* Retirement on execution
* Priority resolution
* Automatic legality filtering
* Exact override precedence
* Legacy fallback
* Flow frontier
* Replay determinism
* Back restoration
* Decision traces
* Invalid and conflicting schemas

### Web tests should cover

* Session creation
* Loading a flow
* Playing moves
* Back and Restart
* Snapshot consistency
* Validation errors
* Save and reload behavior
* Engine-off and engine-error states
* Frontend rendering of returned workspace state

Tests must not require Stockfish to be installed unless explicitly marked as optional integration tests.

Use fixtures or fakes for normal CI.

## Change discipline

* Prefer small vertical slices over broad rewrites.
* Preserve existing working behavior unless the task explicitly replaces it.
* Keep migrations backward compatible when practical.
* Do not combine a full policy rewrite, complete web editor, and flow-wide benchmark system into one change.
* Avoid speculative abstractions without a current use case.
* Keep the initial rule condition language closed and validated.
* Do not introduce arbitrary expression evaluation.
* Do not hide errors through fallback behavior.
* Keep documentation synchronized with implemented behavior.
* Update the project tree and file guide when major modules are added.
* Report deferred behavior and limitations clearly.

## Current implementation sequence

Unless a task explicitly changes the order, prefer this progression:

1. Commit design documentation.
2. Establish the local FastAPI and React communication loop.
3. Display one flow, board state, history, and current policy decision.
4. Add move submission, Back, and Restart.
5. Add evaluation display.
6. Add lifecycle and decision-trace inspection.
7. Extend and integrate rule-policy version 3.
8. Add rule ordering and basic rule editing.
9. Add rule creation from an experimental move.
10. Add broader flow analysis and coverage testing.

Do not implement Elo-like Flow Power scoring until the rule, navigation, analysis, and coverage foundations are stable.
