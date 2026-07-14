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

## Local White-flow authoring

`chess-tui --mode author --flow flows/london.toml` uses a separate authoring
state machine. The TOML file contains numbered White defaults and readable SAN
histories for exact-position exceptions. `WhitePolicy` derives normalized
position keys and resolves exceptions before defaults; `FlowStore` validates
and atomically saves changes with a backup.

The author screen uses python-chess as its rules authority. White plays or types
the recommendation in SAN, while Black moves are selected on the board or typed
in SAN to explore a line.
Explicit `[NAV]`, `[TEXT: MOVE]`, and `[TEXT: NOTE]` modes determine whether
printable keys invoke application shortcuts or enter literal text.
The screen emits default/exception edit intent to `WhiteFlowAuthor`; policy and
persistence semantics do not live in the Textual screen.
