# AGENTS.md

Instructions for coding agents working in this repository.

## Project purpose

Chess TUI is a chess opening training and development application.

The project is evolving toward two primary user modes:

1. **Quiz Mode**
   Tests whether the user can follow an opening policy from memory without exposing the underlying rules before the move is submitted.

2. **Flow Development Mode**
   Lets the user explore lines, create and edit deterministic opening rules, inspect rule lifecycle and priority, navigate backward through positions, and analyze flow coverage and effectiveness with Stockfish.

Both modes must use the same Python chess, policy, flow, persistence, and engine implementations.

## Read before changing code

Before changing rule-policy or flow-schema behavior, read:

* `docs/design/rule-policy-v2.md`

Before changing the local web application or development-mode behavior, read:

* `docs/design/web-development-mode.md`

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
* Rule priority resolution
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

### Deterministic flow policy

* A flow controls White or Black explicitly.
* Current persisted opening flows primarily control White.
* Piece identifiers use explicit colors:

  * `white:g1`
  * `white:c1`
  * `black:b8`
* Do not use relative identifiers such as `us` and `them`.
* A broad rule may match many board states.
* Every individual rule specifies exactly one concrete move.
* The policy resolves to exactly one move or a flow frontier.
* There are no multiple equally correct flow moves.
* A move may be strategically reasonable and still be a flow mismatch.

### Rule actions

Abstract rule moves should use original-piece identity and a destination square.

Example:

```toml
move = { piece = "white:c2", to = "c4" }
```

SAN should normally be derived from the current board for display.

Do not make the rule engine choose among several candidate moves.

### Legality

* Move legality is always enforced automatically by Python.
* Legality must not be an authored rule condition.
* Do not add predicates such as `move_legal`.
* An active rule whose configured move is currently illegal is skipped.
* An illegal move does not automatically retire the rule.

### Priority

* Explicit priority determines which active rule wins.
* Do not infer priority from apparent rule specificity.
* The initial rule-policy design requires unique priorities.
* Do not use declaration order as a hidden tie-breaker.
* User interfaces may present priority as an ordered list and generate numeric values when saving.

### Rule lifecycle

Rules may be:

```text
DORMANT
ACTIVE
RETIRED
```

* A rule without `activate_when` begins active.
* Activation is latched.
* Once activated, a rule does not return to dormant if its trigger later becomes false.
* Retirement is permanent on the current line.
* Retirement is evaluated before activation when both become true at the same transition.
* In the initial design, successfully executing a rule’s configured move retires that rule.
* Reusable rules are deferred until explicitly designed.

### Resolution order

Policy resolution order is:

```text
1. Exact-position override
2. Highest-priority active legal abstract rule
3. Flow frontier
```

Do not silently change this order.

Version 1 numbered defaults and exceptions are intentionally unsupported. Do not
add a fallback parser, mixed-schema model, or compatibility resolver.

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
7. Implement and integrate rule-policy version 2.
8. Add rule ordering and basic rule editing.
9. Add rule creation from an experimental move.
10. Add broader flow analysis and coverage testing.

Do not implement Elo-like Flow Power scoring until the rule, navigation, analysis, and coverage foundations are stable.
