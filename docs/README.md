# Documentation

## Quiz demo architecture

`chess-tui --mode quiz-demo` exercises the future external-provider boundary
without starting another process or using a network service.

The dependency direction is intentionally narrow:

```text
packaged TOML -> DemoQuizSession -> QuizSessionState -> QuizScreen
                                               |
                                               `-> BoardViewState -> ChessBoard
```

`QuizSession` is the only provider interface. Presentation models do not mention
serialization, transport, ChessFlow, or TypeScript. A future integration should
implement that protocol and leave `QuizScreen`, `ChoicePanel`, and `ChessBoard`
unchanged.

The two packaged flows are validated at load time: every FEN must parse, every
choice must be legal, the correct move must appear exactly once, and applying
the canonical continuation must produce the next fixture FEN. Mismatches still
advance through that canonical path.

The frontier continuation modal is deliberately a preview. Its values remain in
memory only and are labeled `DEMO ONLY — NOT SAVED`.
