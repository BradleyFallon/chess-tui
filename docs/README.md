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

`chess-tui --mode flow --flow flows/london.toml` uses one test-first workflow.
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
depth but is not intended to model realistic chess strength. A later engine
source can replace it without changing `FlowWorkspace` or the screen.

`MoveSuggestionPanel` labels book and bot rows and marks explored branches.
Manual board and typed-SAN entry remain available.
Explicit `[NAV]`, `[TEXT: MOVE]`, and `[TEXT: NOTE]` modes determine whether
printable keys invoke application shortcuts or enter literal text.
Flow files persist explored SAN branches but not opening statistics, source
labels, bot profiles, or evaluations.
