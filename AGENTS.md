# AGENTS.md

Instructions for coding agents working in this repository.

## Product

Chess TUI is an opening training and Rulebook development application with two
primary modes:

- Quiz Mode tests recall without exposing policy before submission.
- Flow Development Mode explores lines, authors version 4 piece scripts,
  inspects legal relationships and decisions, navigates by replay, and performs
  optional Stockfish analysis.

Both modes and both UIs must use the same Python chess, Rule Engine, persistence,
opening, and engine services.

## Authoritative documents

Read these before changing policy or authoring behavior:

- `docs/design/opening-rule-engine-v4.md`
- `docs/design/web-development-mode.md`
- `docs/design/rule-authoring-ui.md`
- `docs/design/piece-development-authoring.md`
- `docs/design/opening-classification.md`
- `README.md`
- `docs/README.md`
- `pyproject.toml`

`docs/design/rule-policy-v3.md` and v2 material are historical only. Version 4
is the sole accepted Rulebook schema; do not add compatibility parsing,
migration-on-load, fallback semantics, or legacy runtime models.

## Architecture

Python owns:

- chess legality, board state, move parsing, and SAN;
- original-piece identity and movement/capture history;
- legal attack and per-attacker recapture analysis;
- condition evaluation and action resolution;
- interrupt and development scheduling;
- typed frontiers, traces, completion, and replay;
- strict TOML validation, canonical serialization, atomic saves, and backups;
- opening classification, opponent move sources, Stockfish, and sessions.

React and Textual own presentation, interaction state, forms, ordering controls,
and calls to Python. Browser code must not reproduce domain decisions.

Preferred dependency direction:

```text
Textual / FastAPI
        |
Workspace and authoring services
        |
Rulebook, policy, relations, actions, opening, engine
        |
python-chess / Stockfish / TOML
```

## Rulebook v4 invariants

The Rulebook is piece-centered:

```text
one optional default development per controlled piece
zero or more one-shot interrupt rules per controlled piece
one authored development_order
one authored interrupt_order
ordered action attempts inside each interrupt
```

Every referenced original piece has one alias and one canonical
`piece:<color>:<type>[:<qualifier>]` reference. Pawns use file qualifiers;
rooks, knights, and bishops use `queenside`/`kingside`; kings and queens have no
qualifier. Original squares are internal and never authored.

Opponent pieces are read-only aliases. Reject development or rules under them.
Every development and interrupt has a non-empty `why`.

Development completes when the original piece first moves anywhere. A
captured-undeveloped piece is terminal but does not satisfy a `.develop`
prerequisite. Completion and captures are replayed state, not persisted state.

Interrupts are one-shot and use optional prerequisites, optional exact SAN
history, optional live conditions, a required flag, and non-empty ordered
attempts. Exact-position behavior is an interrupt, never a separate persisted
rule type.

Supported action attempts are move to square, capture the triggering attacker,
capture a named original piece, and capture a unique enemy piece by type. Zero
legal candidates fails, one resolves, and multiple candidates are ambiguous.
Never choose arbitrarily or with an engine.

## Relationship and condition invariants

Attack relations are legal captures of occupied enemy squares. Defense is a
legal recapture after simulating one specific attacker. Analyze both colors on
copied boards and never mutate the live board. Sliding rays stop at the first
occupied square. `python-chess` legality is final, including absolute king
pins; a pinned slider may still capture along its pin line.

Keep `defenders_by_attacker` even though aggregate predicates use distinct
defenders across attacks.

Supported conditions are:

```text
moved, unmoved, captured, at, occupied, empty, occupied_by,
in_check, last_move, all, any, not,
attacked, attacked_by, undefended, under_defended,
attack_balance, capturable
```

Condition results include structured diagnostics. There are no named
conditions. Legality is automatic and must not become an authored predicate.

## Scheduler and replay

Resolution order is:

```text
1. Exact-position interrupts in interrupt_order
2. Other interrupts in interrupt_order
3. Default developments in development_order
4. Typed frontier
```

Required triggered rules with no resolving attempt stop at
`unhandled-required-rule`; optional rules continue. Do not skip an ambiguous
non-skippable action. Other frontier reasons are `ambiguous-action`,
`development-complete`, and `no-authored-legal-move`.

Deterministic state is board + SAN history + original-piece tracker + completed
developments and interrupts. Back, Restart, reload, and editing must replay all
of it. Navigation does not delete Rulebook data or explored branches.

## Persistence

TOML is the durable representation. Reject unknown fields, duplicate aliases or
canonical references, malformed/missing order entries, opponent authoring,
invalid prerequisites and cycles, invalid squares, empty attempts, invalid
conditions, invalid exact SAN, and missing explanations.

Mutation contract:

```text
edit -> validate without writing -> review -> explicit apply
     -> revalidate -> atomic save with backup -> replay -> complete snapshot
```

Invalid candidates must not alter the Rulebook, backup, workspace, history,
pending attempt, or runtime state. Do not persist transient evaluations,
relationship snapshots, provenance labels, or completion state.

## Modes

Quiz Mode normally hides expected moves, rules, order, conditions, traces, and
engine evaluation until submission. It does not mutate the Rulebook without an
explicit designed authoring action.

Development Mode may expose the current decision, piece scripts, conditions,
relationships, action diagnostics, order, trace, frontiers, history, and engine
analysis. `/accept-here` creates a piece-owned exact-position interrupt through
the normal validated save-and-replay workflow.

## Opening and engine

The bundled pinned `lichess-org/chess-openings` index is the sole offline
classification and book source. It has no frequency data. Opening identity and
opponent branches are not Rulebook policy.

Stockfish is optional only where the mode explicitly permits it. Configured
failures remain visible and never fall back silently. Keep UCI operations off
the event loop, serialize shared access, close owned processes, normalize score
perspective consistently, and keep mate separate from centipawns.

## Development environment

```bash
source ./activate
update-deps
```

Useful commands:

```bash
chess-tui
check-setup
update-deps
fix-deps
```

Frontend:

```bash
cd web
npm install
npm run dev
npm run build
```

## Required checks

Run before completing:

```bash
pytest
ruff check .
black --check .
pyright
```

When frontend code changes, also run the scripts declared in
`web/package.json`:

```bash
npm test
npm run lint
npm run typecheck
npm run build
```

Do not claim a check passed unless it was executed successfully. Normal tests
must not require a network connection or Stockfish binary.

## Change discipline

Keep domain logic in focused core modules, avoid circular presentation imports,
preserve manual TOML editing, add focused tests, and update docs with behavior.
Do not add cloud accounts, hosted storage, remote synchronization, databases,
relative material pins, static exchange evaluation, engine-selected actions,
reusable interrupts, promotion actions, or LLM integration without an explicit
task.
