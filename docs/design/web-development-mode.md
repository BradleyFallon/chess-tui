# Web Application and Flow Development Mode

## Status

Draft design specification.

This document defines the planned local web application, its relationship to the existing Python core and terminal interface, and the product behavior of Quiz Mode and Flow Development Mode.

The deterministic rule-policy schema is defined separately in:

```text
docs/design/rule-policy-v2.md
```

---

# 1. Purpose

Chess TUI is evolving from a terminal-only opening trainer into a local chess opening development application with two primary modes:

1. **Quiz Mode**
2. **Flow Development Mode**

Quiz Mode tests whether the user can follow a flow from memory.

Flow Development Mode is used to:

* Explore opening positions
* Create and edit deterministic rules
* Navigate branches
* Inspect rule lifecycle
* Analyze moves and positions with Stockfish
* Test flow coverage
* Identify weaknesses
* Improve the effectiveness of the flow

The existing terminal interface remains useful, particularly for keyboard-driven practice and testing. The new web interface provides the space and interaction model needed for visual rule authoring, branch navigation, analysis, and diagnostics.

---

# 2. Product principles

The web application follows these principles:

1. **The Python core remains authoritative.**
2. **The browser is a presentation and interaction client.**
3. **Quiz and Development modes use the same flow policy.**
4. **TOML remains the durable source of truth.**
5. **The application runs locally before any hosted architecture is considered.**
6. **Manual TOML editing remains supported.**
7. **Flow navigation and destructive editing remain separate operations.**
8. **Engine failures are explicit.**
9. **The first web release should be a narrow vertical slice.**
10. **The complete rule builder is deferred until the basic browser-to-Python loop is stable.**

---

# 3. Product modes

## 3.1 Main menu

The web application should open to a flow-oriented main menu.

Example:

```text
CHESS FLOW

London System

[Quiz]
Practice the flow from memory.

[Develop]
Create rules, explore responses, and analyze the flow.

[Open another flow]
[Create new flow]
```

The selected flow should remain active when switching between Quiz Mode and Flow Development Mode.

The first vertical slice may open one configured flow directly rather than implementing full flow discovery and creation immediately.

---

## 3.2 Quiz Mode

Quiz Mode answers:

> Can the user correctly follow the flow without seeing its rules first?

Quiz Mode should deliberately hide authoring and engine information before the user submits a move.

### Quiz Mode should show

* Chessboard
* Current move history
* Side to move
* Move input
* Correct or incorrect result after submission
* Rule explanation after submission
* Retry and continue controls
* Progress and accuracy information

### Quiz Mode should normally hide before submission

* Expected move
* Rule ID
* Rule priority
* Active rules
* Dormant rules
* Retired rules
* Activation conditions
* Retirement conditions
* Decision trace
* Stockfish evaluation
* Engine-best move
* Flow-wide diagnostics

### Correct attempt

```text
CORRECT

Move:
c4

Rule:
Play c4 after Black's original b8 knight reaches c6.

[Continue]
```

### Incorrect attempt

```text
INCORRECT

You played:
Nf3

Expected:
c4

Rule:
Play c4 after Black's original b8 knight reaches c6.

[Retry]
[Continue with expected move]
[Open position in Development Mode]
```

A quiz mismatch may indicate either:

* The user forgot the rule
* The flow rule is wrong or poorly designed

The user should be able to open the current position in Development Mode without reconstructing the line manually.

### Quiz persistence

Quiz Mode should not modify the canonical flow unless the user explicitly chooses an authoring action and confirms it.

Quiz results and training history may eventually be stored separately from the flow TOML.

---

## 3.3 Flow Development Mode

Flow Development Mode answers:

> What should the flow do in this position, why should it do it, and how well does that decision perform?

Development Mode should expose:

* Current flow recommendation
* Responsible rule
* Rule lifecycle
* Rule priority
* Decision trace
* Exact-position overrides
* Current line and explored branches
* Black response choices
* Stockfish evaluation
* Move grading
* Rule creation and editing
* Flow coverage and effectiveness analysis

Development Mode is the primary authoring environment.

---

# 4. Development Mode workspace

The preferred desktop layout uses three primary areas.

```text
┌──────────────────┬────────────────────────┬─────────────────────────┐
│ Line / branches  │ Board and evaluation   │ Rules                   │
│                  │                        │                         │
│ Start            │       chessboard       │ SELECTED                │
│ d4               │                        │ 700 Play c4 after Nc6   │
│ ...d5            │  Evaluation bar +0.4   │                         │
│ Bf4              │                        │ ACTIVE                  │
│ ...Nc6           │                        │ 700 Play c4             │
│                  │                        │ 380 Develop e-pawn      │
│                  │                        │ 370 Develop knight      │
├──────────────────┴────────────────────────┴─────────────────────────┤
│ Analysis / rule editor / decision trace                            │
└─────────────────────────────────────────────────────────────────────┘
```

Responsive layouts may stack these areas on smaller screens.

The browser should never duplicate policy resolution. It displays the workspace state returned by Python.

---

# 5. Development Mode sections

## 5.1 Board workspace

The central board supports:

* Selecting and playing moves
* Showing legal destinations
* Displaying the last move
* Showing check state
* Moving backward and forward
* Restarting the line
* Choosing Black responses
* Displaying the flow recommendation
* Displaying engine evaluation

Primary controls:

```text
Back
Forward
Restart
Choose Black response
Play move
Analyze position
```

The board must remain synchronized with the Python session.

---

## 5.2 Evaluation display

When Stockfish is configured, Development Mode should show the current position evaluation.

The score is normalized consistently, initially from White's perspective.

Examples:

```text
+0.4
-1.2
M3
-M2
```

The UI should distinguish:

* Ready
* Analyzing
* Unavailable
* Engine error
* Game over

### Evaluation bar

On wide layouts, a vertical evaluation bar may appear beside the board.

On narrow layouts, use a horizontal bar or compact numeric display.

The display should show:

* Current score
* Previous score
* Change caused by the last move
* Mate score where applicable

Example:

```text
Current:  +0.6
Previous: +0.2
Change:   +0.4
```

### Evaluation history

Development Mode should eventually display a move-by-move history:

```text
Start       +0.20
d4          +0.31
...d5       +0.22
Bf4         +0.35
...Nc6      +0.48
c4          +0.62
```

Evaluation results are transient analysis data and should not be written into the canonical flow TOML.

They may be cached separately by:

* Normalized position
* Engine identity
* Analysis profile

---

## 5.3 Line and branch panel

The line panel initially displays the current SAN history.

```text
1. d4
1...d5
2. Bf4
2...Nc6
```

Later it may become an explored branch tree:

```text
1. d4
├── ...d5
│   ├── 2. Bf4
│   │   ├── ...Nf6
│   │   └── ...Nc6
└── ...Nf6
```

Selecting a branch node restores:

* Board
* SAN history
* Original-piece tracker
* Rule lifecycle
* Current recommendation
* Decision trace
* Cached engine evaluation

The branch panel should make exploration reversible and non-destructive.

---

## 5.4 Rule panel

Rules are grouped by lifecycle.

```text
ACTIVE
700  Play c4 after ...Nc6
380  Develop e-pawn
370  Develop kingside knight

DORMANT
1000 Retreat bishop if attacked
300  Develop light bishop

RETIRED
400  Develop d-pawn
390  Develop dark bishop
```

Selecting a rule should show:

* Rule ID
* Friendly title
* Configured move
* Current SAN if legal
* Priority
* Activation condition
* Retirement condition
* Note
* Lifecycle status
* Activation ply
* Retirement ply
* Retirement reason
* Whether the move is currently legal
* Whether it is currently shadowed

### Lifecycle explanation

Example:

```text
play-c4-against-nc6

Status:
ACTIVE

Activated after:
2...Nc6

Activation condition currently:
False

Still active because:
Activation is latched.

Retires when:
White's original c-pawn moves.
```

This explanation is necessary because a latched rule may remain active after its trigger is no longer visible on the board.

---

## 5.5 Decision trace

Development Mode should expose why the current recommendation was selected.

Example:

```text
RECOMMENDED: c4

Winning rule:
play-c4-against-nc6

Priority:
700

Higher-priority rules:
1000 retreat-dark-bishop — DORMANT

Shadowed active rules:
380 develop-e-pawn
370 develop-kingside-knight

Skipped active rules:
None
```

A more detailed trace may include:

* Activation explanation
* Retirement explanation
* Rule move construction
* Rules skipped because their moves were illegal
* Legacy-default fallback
* Exact-override precedence

The Python backend produces the trace. The browser only presents it.

---

# 6. Development subviews

Development Mode may use these tabs:

```text
Explore | Rules | Analyze | Source
```

## 6.1 Explore

Used for:

* Playing experimental lines
* Choosing Black responses
* Seeing the current recommendation
* Going Back
* Comparing evaluations
* Creating rules from observed moves

## 6.2 Rules

Used for:

* Viewing the complete rule list
* Reordering priority
* Enabling or disabling rules
* Editing notes
* Editing activation conditions
* Editing retirement conditions
* Inspecting named states
* Deleting rules explicitly

## 6.3 Analyze

Used for:

* Current-position engine analysis
* Coverage tests
* Finding uncovered positions
* Detecting shadowed rules
* Detecting unreachable rules
* Identifying poor flow moves
* Comparing challenger profiles
* Inspecting critical branches

## 6.4 Source

Used for:

* Viewing canonical TOML
* Copying rule definitions
* Manually editing source
* Reloading from disk
* Viewing validation errors
* Comparing unsaved and saved content

Manual source editing remains a supported expert workflow.

---

# 7. Primary authoring workflow

The preferred authoring workflow begins with experimental play.

## Step 1: choose a Black response

Black responses may come from:

* Opening-book source
* Configured Stockfish challenger
* Strong Stockfish move
* Previously explored branch
* Manual move entry

## Step 2: inspect the current recommendation

Development Mode shows:

```text
Flow recommends:
e3

Winning rule:
develop-e-pawn
```

The user may optionally hide the recommendation to test intuition.

## Step 3: play the desired White move

Suppose the user plays `c4`.

The application compares:

* Flow-selected move
* User-selected move
* Stockfish assessment

```text
FLOW MISMATCH

Current flow:
e3

You chose:
c4

Engine review:
GOOD

Evaluation:
+0.3 → +0.5
```

## Step 4: choose an authoring action

```text
[Create general rule]
[Create exact override]
[Edit winning rule]
[Change priority]
[Keep current flow]
[Undo move]
```

This is the central Development Mode loop.

---

# 8. Creating a rule from a played move

Creating a rule from an observed move is preferred over starting from an empty form.

The application already knows:

* Board position
* Move played
* Original piece
* Destination square
* Current rule recommendation
* Current active rules
* Engine evaluation

The move action can therefore be inferred.

Example:

```text
Move:
white:c2 → c4
```

The user then defines:

1. Activation condition
2. Retirement condition
3. Relative priority
4. Note

---

## 8.1 Activation editor

The board can help define conditions.

Examples:

```text
Black's original b8 knight is on c6
White's original g1 knight has moved
Square c5 is occupied
White's original c1 bishop is attacked
Named state london-core is complete
```

The browser should allow the user to select pieces and squares rather than type identifiers whenever practical.

The underlying schema remains visible.

```toml
activate_when = { at = {
  piece = "black:b8",
  square = "c6",
} }
```

---

## 8.2 Retirement editor

The application should suggest retirement based on the moving piece.

For:

```text
white:c2 → c4
```

the suggested retirement is:

```toml
retire_when = {
  moved = "white:c2",
}
```

The user may:

* Accept the suggestion
* Replace it
* Remove condition-based retirement

Execution still retires the rule in the version 2 MVP.

---

## 8.3 Priority editor

Users should normally edit priority as relative order.

Example:

```text
Place this rule:

Below:
Retreat bishop when attacked

Above:
Default development rules
```

The browser assigns unique numeric priorities when saving.

The interface may use drag-and-drop:

```text
1. Retreat dark bishop
2. Play c4 after ...Nc6
3. Develop d-pawn
4. Develop dark bishop
5. Develop e-pawn
6. Develop kingside knight
```

The TOML continues to store explicit integers.

---

## 8.4 Condition builder

Compound conditions can be represented as a tree.

```text
ALL
├── black:b8 is on c6
├── white:g1 has moved
└── NOT
    └── White is in check
```

Supported operations:

```text
Add condition
Add ALL group
Add ANY group
Negate condition
Edit condition
Remove condition
```

The condition builder must generate only the closed condition language defined in `rule-policy-v2.md`.

It must never allow arbitrary scripts.

The complete condition builder is not required for the first web vertical slice.

---

# 9. Rule editing

A rule editor should eventually support:

* Move action
* Activation condition
* Retirement condition
* Priority
* Note
* Enabled or disabled state
* Explicit deletion

### Disable versus delete

Rules should be disableable without being permanently deleted.

Potential schema:

```toml
enabled = false
```

A disabled rule remains visible and persists in TOML but does not participate in lifecycle or resolution.

Deletion must require an explicit destructive action.

Back navigation must never delete rules.

---

# 10. Flow analysis

Development Mode should support analysis at two levels.

## 10.1 Current-line analysis

For the active line, show:

* Evaluation after every move
* Evaluation change
* Flow move
* User move
* Engine-best move
* Move-quality classification
* Responsible flow rule

Example:

```text
Move: c4
Rule: play-c4-against-nc6
Quality: GOOD
Evaluation: +0.3 → +0.5
Engine best: c4
```

## 10.2 Flow-wide analysis

A separate analysis action should eventually report:

* Positions where no rule resolves
* Common Black responses with no coverage
* Rules that never activate
* Rules that are always shadowed
* Rules whose configured move is usually illegal
* Flow moves graded as mistakes or blunders
* Average covered depth
* Worst evaluated branch
* Coverage by opponent profile
* Flow performance against progressively stronger challengers

Flow Power or Elo-like scoring is deferred until rule resolution, navigation, and coverage analysis are stable.

---

# 11. Challenger and judge engines

Future flow benchmarking should distinguish two engine roles.

## Challenger

The challenger chooses Black's moves at a configured strength.

Possible profiles may use:

* Stockfish `UCI_Elo`
* Stockfish skill level
* Fixed search limits
* Opening-book frequencies
* Multiple candidate moves

## Judge

The judge evaluates positions using a fixed stronger and reproducible profile.

The judge determines:

* Current advantage
* Advantage change
* Move quality
* Whether the flow has been refuted
* Whether a branch remains acceptable

The web architecture must avoid assuming that one engine configuration serves every role.

The first vertical slice may use one shared analysis service.

---

# 12. Local application architecture

The web application remains in the same repository as the existing TUI and Python core.

Recommended structure:

```text
chess-tui/
├── src/chess_tui/
│   ├── flow/
│   ├── policy/
│   ├── engine/
│   ├── opening/
│   ├── web/
│   │   ├── app.py
│   │   ├── api_models.py
│   │   ├── sessions.py
│   │   └── routes/
│   └── ...
│
├── web/
│   ├── src/
│   ├── package.json
│   ├── vite.config.ts
│   └── index.html
│
├── flows/
├── tests/
└── pyproject.toml
```

---

# 13. Technology choices

Recommended initial stack:

* **FastAPI** for the local Python API
* **React**
* **TypeScript**
* **Vite**
* Existing Python chess core
* Existing Stockfish service
* Existing TOML flow storage

The architecture is:

```text
React and TypeScript browser UI
                ↓ HTTP / JSON
Local FastAPI server
                ↓ direct Python calls
Chess core, policy, flow, Stockfish, and TOML
```

The browser must not reimplement:

* Chess legality
* SAN generation
* Original-piece identity
* Rule lifecycle
* Rule priority resolution
* Flow replay
* TOML serialization
* Stockfish analysis

---

# 14. Running the local application

A future command may be:

```bash
chess-tui web
```

or:

```bash
chess-tui web \
  --flow flows/london.toml \
  --engine /opt/homebrew/bin/stockfish
```

The command should:

1. Start a local FastAPI server.
2. Open or select a flow.
3. Initialize the application session.
4. Start Stockfish when configured.
5. Open a browser.
6. Serve the frontend and API from localhost.
7. Close owned engine processes on shutdown.

Example URL:

```text
http://127.0.0.1:8765
```

The initial implementation does not require:

* Accounts
* Cloud hosting
* Remote synchronization
* A database
* Authentication
* Multi-user support

---

# 15. Development environment

During frontend development, two processes may run.

## Backend

```bash
fastapi dev src/chess_tui/web/app.py --port 8000
```

## Frontend

```bash
cd web
npm run dev
```

Vite should proxy API requests to FastAPI.

Example:

```typescript
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8000",
    },
  },
});
```

In packaged operation, FastAPI may serve the built frontend files.

---

# 16. Python application responsibilities

Python owns:

* Flow discovery
* Flow loading
* Flow validation
* Development sessions
* Board state
* Move legality
* Move submission
* SAN history
* Back and Restart
* Rule lifecycle
* Policy resolution
* Decision traces
* Rule persistence
* Stockfish lifecycle
* Position evaluation
* Black move suggestions
* Branch recording

FastAPI routes should be thin adapters over application services.

Routes should not contain policy logic.

---

# 17. Frontend responsibilities

React and TypeScript own:

* Layout
* Chessboard rendering and input
* Rule-list presentation
* Lifecycle presentation
* Forms
* Priority drag-and-drop
* Evaluation visualization
* Loading and error states
* Calling API endpoints
* Local unsaved form state

The browser should treat each Python workspace response as authoritative.

---

# 18. Session model

The initial local application may use in-memory sessions.

Example:

```python
@dataclass
class DevelopmentSession:
    id: str
    flow_path: Path
    workspace: FlowWorkspace
    policy_runtime: PolicyRuntime
    evaluation_history: list[PositionEvaluation]
```

Sessions may be stored in:

```python
sessions: dict[str, DevelopmentSession]
```

No database is required.

Durable state remains in the flow TOML.

Session state must be reconstructable through replay.

---

# 19. Workspace snapshot

Most API operations should return one coherent workspace snapshot.

Example:

```json
{
  "sessionId": "session-1",
  "mode": "develop",
  "flow": {
    "name": "London System",
    "version": 2,
    "path": "flows/london.toml"
  },
  "position": {
    "fen": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
    "historySan": [],
    "turn": "white",
    "gameOver": null
  },
  "decision": {
    "moveUci": "d2d4",
    "moveSan": "d4",
    "source": "abstract-rule",
    "ruleId": "develop-d-pawn",
    "priority": 400,
    "note": "Claim the center."
  },
  "rules": {
    "active": [],
    "dormant": [],
    "retired": []
  },
  "evaluation": {
    "status": "ready",
    "centipawns": 22,
    "mateIn": null,
    "previousCentipawns": null,
    "changeCentipawns": null
  },
  "navigation": {
    "canBack": false,
    "canForward": false,
    "canRestart": false
  },
  "errors": []
}
```

Returning one snapshot prevents the frontend from reconstructing domain state from several potentially inconsistent responses.

---

# 20. Initial API design

Exact route names may change, but the first API should support these operations.

## Create a session

```http
POST /api/sessions
```

Request:

```json
{
  "flowPath": "flows/london.toml",
  "mode": "develop"
}
```

Response:

```json
{
  "workspace": {}
}
```

## Read a session

```http
GET /api/sessions/{session_id}
```

## Submit a move

```http
POST /api/sessions/{session_id}/moves
```

Request:

```json
{
  "uci": "d2d4"
}
```

The backend:

1. Validates the move.
2. Commits it.
3. Updates replay and lifecycle state.
4. Resolves the next policy decision.
5. Requests or retrieves evaluation.
6. Returns the updated workspace.

## Go Back

```http
POST /api/sessions/{session_id}/back
```

## Go Forward

```http
POST /api/sessions/{session_id}/forward
```

Forward may be deferred from the first slice.

## Restart

```http
POST /api/sessions/{session_id}/restart
```

## Reload from disk

```http
POST /api/sessions/{session_id}/reload
```

## Select a Black suggestion

Black suggestions may be submitted through the same move endpoint.

## Read source

```http
GET /api/sessions/{session_id}/source
```

## Save source

```http
PUT /api/sessions/{session_id}/source
```

Manual source editing may be deferred from the first slice.

---

# 21. Rule API direction

Rule editing is not required in the first web vertical slice, but the API should eventually support:

```http
GET    /api/sessions/{session_id}/rules
POST   /api/sessions/{session_id}/rules
PUT    /api/sessions/{session_id}/rules/{rule_id}
DELETE /api/sessions/{session_id}/rules/{rule_id}
POST   /api/sessions/{session_id}/rules/reorder
```

After every successful rule edit, Python should:

1. Validate the updated policy.
2. Write deterministic TOML.
3. Reload the policy.
4. Replay the current line.
5. Return the complete updated workspace.

The frontend must not directly edit TOML structures without backend validation.

---

# 22. Engine analysis API

The first implementation may use ordinary HTTP polling.

Example request:

```http
POST /api/sessions/{session_id}/analysis
```

Response:

```json
{
  "status": "analyzing",
  "requestId": "analysis-47"
}
```

Polling:

```http
GET /api/analysis/{request_id}
```

Later, WebSockets or server-sent events may push:

* Evaluation updates
* Black move suggestions
* Long-running analysis progress

Do not begin with WebSockets unless needed by the first slice.

---

# 23. Back navigation semantics

Back is navigation, not deletion.

When the user goes Back, Python restores:

* Board
* SAN history
* Original-piece tracker
* Rule lifecycle
* Recommendation
* Decision trace
* Cached evaluation

Back must not delete:

* Rules
* Exact overrides
* Opponent replies
* Other branches

If there is an unfinished edit or attempted move, the UI should cancel or confirm that local action before navigating further.

---

# 24. Persistence behavior

TOML remains the canonical flow storage.

Requirements:

* Writes remain deterministic.
* Writes remain reviewable through Git.
* Existing atomic-save and backup behavior is preserved.
* Manual file editing remains supported.
* External changes are detected.
* The browser must not silently overwrite externally changed source.

If the file changes on disk while the browser has unsaved edits, show a conflict:

```text
FLOW CHANGED ON DISK

[Reload from disk]
[Review differences]
[Keep unsaved editor state]
```

Do not silently merge or overwrite.

---

# 25. Stockfish lifecycle

Stockfish should be owned by the Python application.

The server should:

* Start the process lazily or at application startup
* Serialize engine access
* Keep blocking UCI calls off the event loop
* Reuse one persistent process where appropriate
* Close the process on application shutdown
* Surface startup and request failures explicitly

The frontend receives structured engine status.

Example:

```json
{
  "status": "error",
  "message": "Stockfish exited while analyzing the position.",
  "retryable": true
}
```

The frontend must not silently substitute another engine source.

---

# 26. Error handling

API errors should use structured responses.

Example:

```json
{
  "error": {
    "code": "FLOW_VALIDATION_ERROR",
    "message": "Duplicate rule priority 700.",
    "details": {
      "ruleIds": [
        "play-c4-against-nc6",
        "respond-to-c5"
      ]
    }
  }
}
```

Useful error categories include:

* Invalid move
* Flow validation error
* Persistence conflict
* Engine startup error
* Engine request error
* Session not found
* Invalid navigation
* External file change
* Unsupported schema version

The browser should preserve the last valid workspace when an edit or reload fails.

---

# 27. First web vertical slice

The first implementation should prove the browser-to-Python interaction loop.

## Required behavior

1. Start the local FastAPI server.
2. Start or serve a React application.
3. Open one configured flow.
4. Display the board from Python-provided FEN.
5. Display SAN history.
6. Display side to move.
7. Display the current Python-selected policy decision.
8. Submit White and Black moves.
9. Support Back.
10. Support Restart.
11. Display active, dormant, and retired rule groups when available.
12. Display a compact decision trace.
13. Display Stockfish evaluation when configured.
14. Display explicit engine-off and engine-error states.
15. Return complete workspace snapshots.
16. Preserve the existing TUI.
17. Run without a database or cloud services.

## Deferred from the first vertical slice

* Full rule creation wizard
* Nested condition builder
* Named-state editor
* Rule deletion
* Drag-and-drop priority persistence
* Flow-wide coverage analysis
* Branch tree visualization
* Forward navigation
* Quiz statistics
* WebSockets
* Cloud hosting
* Flow Power scoring

---

# 28. Second web vertical slice

After the interaction loop is stable:

1. Reorder rule priority.
2. Enable or disable rules.
3. Edit rule notes.
4. Inspect full lifecycle details.
5. View canonical source.
6. Reload source from disk.
7. Save deterministic source.
8. Add saved test positions.

---

# 29. Third web vertical slice

Add rule creation from experimental play:

1. User plays a move that differs from the flow.
2. Backend identifies original piece and destination.
3. UI offers Create General Rule.
4. User defines activation.
5. Backend suggests retirement.
6. User chooses relative priority.
7. User adds a note.
8. Backend validates and saves.
9. Backend replays the line.
10. Updated recommendation appears immediately.

After that, add:

* Board-assisted condition selection
* Compound condition builder
* Named-state editing
* Explicit rule deletion
* Exact-override creation

---

# 30. Testing requirements

## Backend tests

Cover:

* Session creation
* Flow loading
* Snapshot creation
* Move submission
* Illegal moves
* Back
* Restart
* Rule lifecycle restoration
* Decision-trace serialization
* Evaluation status
* Engine failure
* Reload failure
* Persistence conflict
* Game-over positions

## Frontend tests

Cover:

* Initial workspace rendering
* Board update after a move
* Back and Restart controls
* Loading state
* Engine-off state
* Engine-error state
* Rule lifecycle lists
* Decision-trace display
* API error display
* Preservation of the last valid workspace

## Integration tests

Use a test server and fixture flow to verify:

```text
Browser action
→ HTTP request
→ Python workspace update
→ JSON response
→ frontend state update
```

Normal CI tests must not require a real Stockfish binary.

Optional Stockfish integration tests may use an explicit environment variable.

---

# 31. Development and build checks

Backend changes should run:

```bash
black --check src tests
ruff check src tests
pyright
pytest
```

Frontend changes should run the scripts configured in `web/package.json`, expected to include equivalents of:

```bash
npm run lint
npm run typecheck
npm test
npm run build
```

Do not claim these checks passed unless they were executed successfully.

---

# 32. Accessibility and interaction

The web interface should support:

* Keyboard board interaction
* Visible focus
* Non-color-only status indicators
* Accessible button labels
* Readable evaluation text in addition to the bar
* Text equivalents for rule lifecycle state
* Reasonable responsive layouts

Drag-and-drop priority editing must have keyboard alternatives.

---

# 33. Security and local boundaries

The initial server is local-only.

Default binding:

```text
127.0.0.1
```

Do not bind to all network interfaces unless explicitly requested.

Flow paths must be validated. The API should not permit arbitrary unrestricted filesystem access.

The browser must not be able to request arbitrary command execution.

Stockfish paths are provided through trusted local configuration or startup arguments, not arbitrary browser input in the first version.

---

# 34. Compatibility with the TUI

The existing TUI remains supported.

Both interfaces must use:

* The same FlowStore
* The same policy parser
* The same policy runtime
* The same original-piece tracker
* The same Stockfish service abstractions
* The same replay behavior
* The same decision model

The web application must not introduce a second interpretation of the flow format.

The TUI may remain the preferred client for:

* Fast keyboard training
* Manual experimental play
* Development diagnostics
* Regression testing

The web application becomes the preferred client for:

* Rule authoring
* Priority editing
* Branch inspection
* Evaluation history
* Flow-wide analysis

---

# 35. Acceptance criteria

The web foundation is complete when:

1. A user can start the local web application with one command.
2. The browser loads a workspace from the Python backend.
3. The browser displays the same board position as Python.
4. A move submitted in the browser is validated and committed by Python.
5. The updated FEN and SAN history return in one workspace snapshot.
6. Back restores the correct board and policy state.
7. Restart returns to the flow start.
8. The current policy recommendation is calculated only by Python.
9. Active, dormant, and retired rules can be displayed.
10. The decision trace can be displayed.
11. Stockfish evaluation can be displayed when configured.
12. Engine failures remain explicit.
13. No browser implementation of chess legality or rule resolution exists.
14. No database or cloud service is required.
15. The existing TUI remains functional.
16. TOML remains the durable source of truth.
17. Backend and frontend tests pass.
18. Production frontend assets can be served by the local Python server.

---

# 36. Final architecture principle

> The web application is a local visual client for the existing Python chess system. Python owns legality, policy, lifecycle, replay, persistence, and Stockfish. Quiz Mode hides the policy to test memory. Flow Development Mode exposes the policy so the user can build, inspect, test, and improve it.
