# Documentation

The authoritative Opening Rule Engine specification is
[`design/opening-rule-engine-v4.md`](design/opening-rule-engine-v4.md).
Piece-centered interaction is covered by
[`design/rule-authoring-ui.md`](design/rule-authoring-ui.md) and
[`design/piece-development-authoring.md`](design/piece-development-authoring.md).
The broader local application contract is
[`design/web-development-mode.md`](design/web-development-mode.md).

Version 4 is the sole accepted persisted policy schema. The v2 and v3 documents
are historical references only.

## Opening Rule Engine

`FlowStore` loads and strictly validates a piece-centered TOML `Rulebook`.
Controlled `PieceScript` values may contain one default development and
multiple one-shot interrupts. `development_order` and `interrupt_order` define
semantic scheduling order. Interrupts use optional conditions and exact SAN
histories plus ordered deterministic move/capture attempts.

The shared Python core consists of:

```text
Rulebook parser and author
OriginalPieceTracker
PositionAnalyzer
Condition evaluator
ActionResolver
PolicyRuntime scheduler and replay
FlowWorkspace
```

`PositionAnalyzer` computes legal attacks and legal per-attacker recaptures for
both colors on copied boards. This makes absolute pins and king safety part of
normal legality. Conditions expose these structured relationship facts to the
scheduler and UI.

Scheduling is exact-position interrupts, other interrupts,
default development, then a typed frontier. Required-rule failures and
ambiguities do not silently fall through. Back, Restart, reload, and edits
restore completion by replaying SAN rather than persisting runtime state.

## Textual flow mode

Plain `chess-tui` selects the most recently saved v4 Rulebook and discovers
Stockfish from `PATH`; `--flow` and `--engine` override those selections. The
Textual mode uses the same scheduler and displays the selected move,
explanation, trace, and frontier reason. Rule editing is performed in the local
web UI or directly in TOML.

Opponent replies are branch data chosen from the bundled opening graph or the
configured engine. They are not controlled-side policy rules. A configured
engine failure is explicit and never silently replaced.

## Local web Development Mode

The React application in `web/` talks to `src/chess_tui/web/` over ordinary
HTTP. FastAPI adapts the same workspace, Rulebook, relationships, scheduler,
opening classifier, and engine services used by Textual.

```bash
cd web
npm install
npm run build
cd ..

chess-tui web --flow flows/london.toml
```

The local web mode supports board/SAN input, piece inspection, relationship
diagnostics, default-development and interrupt authoring, semantic reordering,
validation preview, explicit Apply, `/accept-here`, Back, Restart, reload,
opening context, and optional Stockfish analysis.

Controlled pieces are authorable. Opponent pieces are read-only aliases usable
by conditions and capture attempts. Python returns coherent snapshots with
mechanical state, rule status, decision/frontier, attempt diagnostics, and
relationships; React renders those values without deriving domain semantics.

Mutations follow validate, review, Apply, revalidate, atomic save with backup,
replay, and refreshed snapshot. Invalid candidates leave the file, backup,
workspace, history, pending attempt, and runtime completion unchanged.

For two-process development:

```bash
fastapi dev src/chess_tui/web/app.py --port 8000
```

```bash
cd web
npm run dev
```

Vite proxies `/api` to `http://127.0.0.1:8000`.

## Quiz demo

`chess-tui --mode quiz-demo` exercises a read-only provider/session boundary.
It does not start another service or persist Rulebook changes. Presentation
models stay independent from serialization and transport so a future provider
can implement the same protocols.

## Opening data

[`design/opening-classification.md`](design/opening-classification.md) specifies
the offline deterministic opening graph generated from the pinned
`lichess-org/chess-openings` dataset. The dataset contains no popularity
frequencies. Opening identity, book continuation, and reachable-defense
information remain separate from authored Rulebook decisions.

## Historical documents

- [`design/rule-policy-v3.md`](design/rule-policy-v3.md)
- [`design/rule-policy-v2.md`](design/rule-policy-v2.md)

These explain previous designs only and must not be used to infer current
runtime behavior.
