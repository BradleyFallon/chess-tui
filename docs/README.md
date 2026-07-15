# Documentation

## Quiz demo architecture

`chess-tui --mode quiz-demo` exercises the future external-provider boundary
without starting another process or using a network service.

The dependency direction is intentionally narrow:

```text
packaged TOML -> DemoQuizProvider -> QuizSession -> QuizSessionState -> QuizScreen
                                                               |
                                                               `-> BoardViewState -> ChessBoard
```

`QuizProvider` owns flow discovery and session creation. `QuizSession` owns one
quiz run. Presentation models do not mention serialization, transport,
ChessFlow, or TypeScript. A future integration should implement those protocols
and leave `QuizScreen`, `ChoicePanel`, and `ChessBoard` unchanged.

The two packaged flows are validated at load time: every FEN must parse, every
choice must be legal, the correct move must appear exactly once, and applying
the canonical continuation must produce the next fixture FEN. Mismatches still
advance through that canonical path.

Frontier continuation rules are deliberately a preview. The first rule is a
default response used after any opponent move. Additional rules are exact
exceptions keyed by opponent SAN, and duplicate exceptions replace the earlier
rule. Values remain in memory only and are labeled `DEMO ONLY — NOT SAVED`.
The editor is part of the responsive quiz side panel rather than a modal, so it
never covers or unmounts the board.

The quiz screen chooses landscape, portrait, or compact arrangements as the
terminal changes. Renderer selection is strict: a screen that is too small
shows a resize requirement and restores the same renderer and session state
when enlarged.

## Unified White-flow mode

Plain `chess-tui` uses one test-first workflow in flow mode. It selects the most
recently saved `flows/*.toml` file and discovers `stockfish` from `PATH`, failing
startup rather than degrading to the deterministic bot when Stockfish is
unavailable. `--flow` and `--engine` explicitly override those selections.
The first ranked Black response is committed automatically in normal flow mode;
`--select-black` restores the interactive suggestion panel when branch choice
or manual entry is desired.
The TOML file contains numbered White defaults and readable SAN histories for
exact-position exceptions. `WhitePolicy` derives normalized position keys and
resolves exceptions before defaults; `FlowStore` validates and atomically saves
changes with a backup.

Known White rules stay hidden until the user submits a board or SAN move. A
correct attempt reveals the move and note; a mismatch can be retried, kept, or
edited inline. Keeping a saved rule restores the pre-attempt position before
applying it. At an undefined step, the selected move and note become the next
default. If a numbered default is illegal, the selected legal move is offered
as an exact-position exception.

`FlowWorkspace` owns the current board, SAN history, attempted White move,
rollback, and turn transitions. The Textual screen renders that state while
`WhiteFlowAuthor` owns policy and file writes.

Black responses come from `OpponentMovePlanner`. It converts statistical rows
from `OpeningMoveSource` into generic `MoveSuggestion` values when book data is
available. Otherwise it asks `BotMoveSource`; the current
`FixtureBotMoveSource` deterministically ranks legal moves from the normalized
position, profile id, and session seed. It works beyond the authored fixture
depth but is not intended to model realistic chess strength. With
`--engine /path/to/stockfish`, `StockfishBotMoveSource` instead uses a persistent
UCI process through `StockfishEngineService` and returns one `ENGINE PROTOTYPE`
move. Engine calls are serialized and kept off the Textual event loop. A
configured engine failure is shown explicitly with retry and manual-entry
controls; it never silently selects the fixture bot.

The same service analyses a mismatching White move before and after it is
played. Scores are normalized to White before calculating centipawn loss, and
mate scores remain separate from centipawn values. The screen reports a
configurable quality band and the best alternative while leaving every retry,
keep, and repertoire-edit choice under user control.

Flow mode also renders a compact Black/White advantage bar. It requests one
analysis only when the committed FEN changes, ignores stale results, preserves
mate scores as mate distances, and reports analysis failures without changing
the active flow phase.

`MoveSuggestionPanel` labels book and bot rows and marks explored branches.
Manual board and typed-SAN entry remain available.
Completed boards enter a dedicated `GAME_OVER` phase that reports checkmate,
stalemate, automatic draw terminations, or other python-chess outcomes.
Default CLI flow sessions focus SAN entry in `[TEXT: MOVE]`. `Escape` returns to
`[NAV]` for board shortcuts and `I` focuses SAN entry again. Explicit
`[NAV]`, `[TEXT: MOVE]`, and `[TEXT: NOTE]` modes determine whether printable
keys invoke application shortcuts or enter literal text.
Flow files persist explored SAN branches but not opening statistics, source
labels, bot profiles, or evaluations.

## Local web Development Mode

The first browser slice lives in `web/` and communicates with
`src/chess_tui/web/` through ordinary JSON HTTP. FastAPI routes adapt the same
`FlowWorkspace`, `FlowStore`, `WhitePolicy`, and engine service used elsewhere;
complete snapshots keep React from reconstructing chess or policy state.

```bash
cd web
npm install
npm run build
cd ..

chess-tui web \
  --flow flows/london.toml \
  --engine "$(command -v stockfish)"
```

The default bind is `127.0.0.1:8765`. Omitting `--engine` is supported and
reported as `engine-off`. Development Mode supports controlled board input,
White-result retry/continuation, manual Black moves, Back, Restart, legacy-v1
rule/source inspection, structured errors, and White-normalized evaluation.
Back replays the retained SAN prefix and never deletes persisted policy or
branches.

For frontend development, run these in separate terminals:

```bash
fastapi dev src/chess_tui/web/app.py --port 8000
```

```bash
cd web
npm run dev
```

Web Quiz, visual rule editing, version 2 rule parsing/lifecycle, forward
navigation, WebSockets, accounts, databases, and hosted deployment are
deferred. The authoritative specifications are
`docs/design/rule-policy-v2.md` and
`docs/design/web-development-mode.md`.
