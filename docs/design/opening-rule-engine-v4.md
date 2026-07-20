# Opening Rule Engine v4

Status: authoritative for persisted opening policy, runtime scheduling, replay,
and authoring behavior.

## Terminology and ownership

The **Opening Rule Engine** is the complete Python system: the Rulebook parser,
original-piece tracker, position analyzer, condition evaluator, action resolver,
scheduler, runtime state, replay, and decision trace.

The **Rulebook** is the human-readable version 4 TOML file. It contains authored
preferences; it does not contain computed relations, engine evaluations, or
runtime completion state.

Python is authoritative for chess legality and every Rule Engine decision.
React and Textual render coherent Python snapshots and submit operations.

## Rulebook shape

Required top-level fields are:

```toml
version = 4
name = "Accelerated London"
start_fen = "startpos"
side = "white"
development_order = ["d-pawn", "london-bishop"]
interrupt_order = ["london-bishop.escape-attack"]
```

`opening_tags` and `opponent_replies` remain separate opening metadata and
branch data. They never participate as rules.

Every referenced original piece has exactly one alias:

```toml
[pieces.london-bishop]
ref = "piece:white:bishop:queenside"
```

An opponent-side declaration is read-only and contains only `ref`. A
controlled-side piece may contain one default development instruction and any
number of interrupt rules:

```toml
[pieces.london-bishop.develop]
to = "f4"
why = "Develop outside the pawn chain as soon as the move is legal."

[[pieces.london-bishop.rules]]
id = "escape-attack"
when = { attacked = "self" }
required = true
try = [{ capture = "attacker" }, { move = "g3" }]
why = "Preserve the London bishop when it is concretely attacked."
```

Every `develop` and rule requires a non-empty `why`.

## Development and prerequisites

`development_order` schedules default development independently from where the
instructions are stored. A development instruction contains `to`, optional
`requires`, optional live `when`, and `why`.

The original piece's first move completes its default development, regardless
of whether the move came from development, an interrupt, an exact-position
interrupt, or an accepted manual move. A piece captured before it moves is
`captured-undeveloped`; this is terminal for development-frontier calculation
but does not satisfy a `.develop` prerequisite.

Prerequisites use canonical instruction references such as
`london-bishop.develop` and `d-pawn.take-bishop`. Serialization always writes
canonical full references. Unknown references and dependency cycles are
invalid.

## Interrupts and actions

`interrupt_order` contains every interrupt exactly once and defines precedence.
All interrupts are one-shot in v4. They may have optional prerequisites, an
optional live condition, an optional exact SAN history in `after`, a `required`
flag, ordered `try` attempts, and an explanation.

Exact behavior is not a separate rule type. It is an ordinary piece-owned
interrupt with `after = ["d4", "e5"]`. The parser replays the SAN and indexes
the normalized resulting position.

Supported attempts are:

```toml
{ move = "b3" }
{ capture = "attacker" }
{ capture = "black-queenside-bishop" }
{ capture_type = "bishop" }
```

Each attempt resolves against legal moves by the owning original piece:

- zero candidates: record failure and try the next attempt;
- one candidate: resolve deterministically;
- multiple candidates: record ambiguity and never choose arbitrarily.

`capture = "attacker"` uses the attackers supplied by the triggering condition.
No action uses Stockfish or a material tie-breaker.

## Legal relationship analysis

The position analyzer computes relationships for every tracked original piece
and for both colors without mutating the live board.

An attack exists only if the attacker can legally capture the occupied enemy
square while preserving its own king. Pawn diagonals, knight jumps, king steps,
and sliding rays provide capture geometry; sliding rays stop at the first
occupied square. `python-chess` legal move generation is the final authority.

A defense is specific to an attacker. The analyzer copies the board, commits
that attack, and records each friendly original piece that can then legally
recapture on the captured square. Consequently `defenders_by_attacker` may
differ across attackers. Aggregate defenders are the distinct defenders that
work against at least one current attack.

Absolute king pins are handled through legality. A pinned piece does not count
for a move that exposes its king, but it may capture legally along its pin line.
Pin metadata (`king_pinned`, `pinned_by`, and `pin_ray`) is diagnostic only.

Derived facts use these meanings:

```text
attacker_count = distinct legal enemy attackers
defender_count = distinct legal recapturing friendly pieces
attack_balance = attacker_count - defender_count
undefended = attacker_count > 0 and defender_count == 0
under_defended = attacker_count > defender_count
```

## Conditions

Historical and position conditions are `moved`, `unmoved`, `captured`, `at`,
`occupied`, `empty`, `occupied_by`, `in_check`, `last_move`, `all`, `any`, and
`not`.

Relationship-backed conditions are `attacked`, `attacked_by`, `undefended`,
`under_defended`, `attack_balance`, and `capturable`.

Inside a piece rule, a subject may be `self`, an alias, or a canonical
starting-piece reference. Serialization prefers an available alias.
`attacked_by` requires exactly one of a piece or piece type. Condition results
contain a boolean, a concise explanation, and structured details such as
attackers, defenders, counts, and balance.

Legality is never an authored condition.

## Scheduler and frontiers

Resolution order is fixed:

1. exact-position interrupts in authored interrupt order;
2. other interrupts in authored interrupt order;
3. default developments in authored development order;
4. a typed frontier.

Completed rules, unmet prerequisites, false triggers, and nonmatching exact
histories are skipped. Attempts are tried in order. A triggerless interrupt may
become applicable through its attempts.

If a required triggered rule has no resolving action, scheduling stops at
`unhandled-required-rule`. Optional rules continue. An ambiguous non-skippable
action produces `ambiguous-action`.

Other frontier reasons are:

- `development-complete`: every development is complete or terminally captured;
- `no-authored-legal-move`: incomplete development remains, but nothing resolves.

The trace records condition evaluation and every failed, ambiguous, and selected
attempt. Python supplies presentation statuses and explanations.

## Replay and persistence

Runtime state is board plus SAN history, original-piece locations and movement,
captured states, completed developments, completed interrupts, and last move.
Back, Restart, reload, and edits rebuild it by replaying SAN. Runtime completion
is never persisted.

Writes use the existing validate/review/apply contract:

```text
edit -> validate without writing -> review -> explicit apply
     -> revalidate -> atomic save with backup -> replay -> snapshot
```

Invalid candidates do not modify the Rulebook, backup, workspace, history,
attempt, or runtime state. Version 4 is the only accepted policy schema;
version 3 and mixed schemas are rejected without fallback.

`/accept-here` creates or replaces a stable, piece-owned exact-position
interrupt, validates and saves it, replays, reassesses the attempted move, and
then commits that move.

## Authoring UI

The piece inspector presents:

```text
Piece
Current decision
Default development
Interrupting rules
Current board relationships
Development order
Interrupt order
Policy details
```

Opponent pieces are read-only relationship and condition references. The
interrupt wizard collects a trigger, required behavior, ordered attempts,
explanation, and review. Earlier/Later controls edit semantic order without
numeric priorities. Raw TOML is an advanced diagnostic, not the primary editor.

## LLM editing guidance

```text
Normal opening move:
Edit the owning piece's default development.

Opportunity or defensive response:
Add an interrupt rule to the moving piece.

Exact position:
Add an interrupt rule with after SAN.

Multiple preferred responses:
Use ordered try actions inside one interrupt.

Different scheduling precedence:
Edit interrupt_order or development_order.

Do not add conditions already enforced by legality.
Every development and rule requires why.
```

## Deferred functionality

V4 does not include relative material pins, static exchange evaluation,
engine-selected actions, arbitrary best-capture rules, fork discovery,
open-file or outpost evaluators, reusable interrupts, promotion actions,
hosted persistence, accounts, databases, or LLM integration.
