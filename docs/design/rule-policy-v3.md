# Deterministic Rule Policy v3

## Status

This document is authoritative for the persisted opening-flow schema and runtime.
Version 3 replaces version 2. The loader accepts only `version = 3`; it does not
translate version 2 files or accept a mixed schema.

## Purpose

A flow is a deterministic opening policy for one explicitly named side. It can
describe immediate responses, ordinary piece development, structure-dependent
plans, later continuations, and exact-position exceptions without encoding a
move tree.

Python owns legality, original-piece identity, condition evaluation, lifecycle,
structure selection, resolution, replay, and persistence. Presentation clients
display the resulting state and submit authored mutations.

## Top-level schema

```toml
version = 3
name = "London System"
start_fen = "startpos"
side = "white"

[[opening_tags]]
eco = "D00"
name = "Queen's Pawn Game: Accelerated London System"
```

The optional ordered collections are:

```text
conditions
structures
responses
development
continuations
overrides
opponent_replies
```

Collection order is preserved during round trips. Authored order is semantic
for structures, responses, development assignments, and continuations.

## Starting-piece references

Authored references identify pieces from `start_fen`, not current occupants.

```text
piece:white:pawn:d
piece:white:knight:kingside
piece:black:bishop:queenside
piece:white:queen
```

Pawns require a file qualifier. Rooks, knights, and bishops require
`queenside` or `kingside`. Kings and queens take no qualifier. Original identity
continues through moves, captures, en passant, castling, and promotion.

## Conditions

Named conditions remove repeated expressions:

```toml
[[conditions]]
id = "london-core"
when = { all = [
  { at = { piece = "piece:white:pawn:d", square = "d4" } },
  { at = { piece = "piece:white:bishop:queenside", square = "f4" } },
  { at = { piece = "piece:white:knight:kingside", square = "f3" } },
] }
```

The closed condition language contains:

```text
moved
unmoved
captured
at
occupied
empty
occupied_by
attacked
attacked_by
in_check
last_move
condition
all
any
not
```

Examples:

```toml
when = { unmoved = "piece:white:king" }
when = { captured = "piece:white:bishop:queenside" }
when = { last_move = {
  piece = "piece:black:pawn:c",
  to = "c5",
} }
when = { condition = "london-core" }
```

`last_move` is true only for the immediately preceding committed move. Named
condition references must exist and must be acyclic.

## Structures

A structure represents a mutually exclusive strategic branch:

```toml
[[structures]]
id = "traditional"
name = "Traditional London"
available_when = { at = {
  piece = "piece:black:pawn:d",
  square = "d5",
} }
selected_when = { at = {
  piece = "piece:white:pawn:c",
  square = "c3",
} }
note = "Build the compact London shell."
```

A structure has one of four effective states:

```text
UNAVAILABLE
AVAILABLE
SELECTED
REJECTED
```

Before selection, `available_when` is evaluated live. After every committed
move, the runtime selects the first authored structure whose availability and
selection conditions are both true. Selection is latched for the line and all
other structures become rejected. A structure must not select in the initial
position.

A policy item without `structures` is global. Before selection, a scoped item is
in scope when at least one listed structure is available. After selection, it
is in scope only when the selected structure is listed.

## Move actions

Every move action identifies one original piece and one destination:

```toml
move = { piece = "piece:white:pawn:c", to = "c4" }
```

Python derives SAN and filters illegal actions. An illegal action waits; it does
not retire automatically and does not block later authored items.

Promotion actions are not represented in version 3.

## Responses

Responses are checked before normal development:

```toml
[[responses]]
id = "advance-against-early-c5"
move = { piece = "piece:white:pawn:d", to = "d5" }
unlock_when = { last_move = {
  piece = "piece:black:pawn:c",
  to = "c5",
} }
when = { at = {
  piece = "piece:white:pawn:d",
  square = "d4",
} }
expire_when = { not = { at = {
  piece = "piece:white:pawn:d",
  square = "d4",
} } }
```

Response and continuation fields are:

```text
id
move
structures       optional
unlock_when      optional, latched
when             optional, live
expire_when      optional, permanent
note             optional
```

A rule with no `unlock_when` starts unlocked. Unlocking is latched.
`when` controls only current applicability. `expire_when` retires permanently.
Successfully executing a move rule always retires it as a one-shot rule.

## Development assignments

Development is a piece-centered ordered plan:

```toml
[[development]]
id = "develop-london-bishop"
piece = "piece:white:bishop:queenside"
target = "f4"
ready_when = { moved = "piece:white:pawn:d" }
note = "Develop outside the pawn chain."
```

Fields are:

```text
id
piece
target
structures       optional
ready_when       optional, live
note             optional
```

An assignment is eligible only while its original piece exists and is unmoved.
It becomes developed when that piece moves and captured when that piece is
captured. These states are derived from replay and are not persisted.

A piece may have at most one global assignment and at most one assignment for
each structure. Multi-structure assignments are allowed, but assignments for
the same piece may not overlap a structure.

## Continuations

Continuations have the same schema and lifecycle as responses. They are checked
after all development assignments:

```toml
[[continuations]]
id = "castle-kingside"
move = { piece = "piece:white:king", to = "g1" }
structures = ["traditional"]
when = { all = [
  { unmoved = "piece:white:king" },
  { unmoved = "piece:white:rook:kingside" },
  { empty = "f1" },
  { empty = "g1" },
] }
```

## Exact overrides and opponent replies

Exact overrides are strongest:

```toml
[[overrides]]
id = "after-d4-e5"
after = ["d4", "e5"]
move = { piece = "piece:white:pawn:d", to = "e5" }
note = "Capture the offered pawn."
```

Overrides contain no `enabled` field. Their SAN prefix must replay legally,
target the controlled side, resolve to a unique normalized position, and
produce a legal action there.

Opponent replies remain explored branch data rather than policy items:

```toml
[[opponent_replies]]
id = "after-d4-d5"
after = ["d4"]
move = "d5"
```

They do not participate in policy resolution.

## Deterministic resolution

The fixed section order is:

```text
1. Exact-position override
2. First applicable response
3. First applicable development assignment
4. First applicable continuation
5. Flow frontier
```

Within a section, the first authored applicable legal item wins. There is no
numeric priority, no specificity ranking, and no hidden declaration-order
fallback outside these explicit ordered lists.

Move-rule statuses are:

```text
LOCKED
INACTIVE
WAITING
APPLICABLE
SELECTED
RETIRED
OUT_OF_SCOPE
```

Development uses the applicable statuses plus the derived `DEVELOPED` and
`CAPTURED` states in presentation snapshots.

Every resolution returns a complete trace containing structure results,
override matching, every policy item's effective status and reason, the
selected source, or the frontier reason.

## Lifecycle transition order

After every committed move:

```text
1. Update the original-piece tracker and last-move fact.
2. Retire executed or expired move rules.
3. Unlock newly satisfied move rules.
4. Select the first matching available structure, if none is selected.
```

Retirement therefore wins when expiration and unlocking become true on the
same transition. Back and Restart rebuild every history-sensitive fact through
deterministic replay.

## Validation

Loading and preview validation reject:

- any version other than 3;
- unknown fields or condition operators;
- invalid or absent starting-piece references;
- unknown or cyclic named conditions;
- duplicate IDs;
- invalid structure references or duplicate scopes;
- initially selected structures;
- overlapping same-piece development scopes;
- more than one global assignment for a piece;
- malformed or wrong-side actions;
- duplicate normalized override positions;
- illegal override SAN prefixes or actions;
- duplicate opponent branches.

Non-fatal diagnostics report currently unused structures and named conditions.
All save operations validate, serialize deterministically, reparse, replay the
active line, write atomically, and retain the existing backup behavior.

## Development Mode

The left-side authoring hierarchy is:

```text
PIECE DEVELOPMENT
STRUCTURE
CURRENT DECISION
POLICY ORDER
  Responses
  Development
  Continuations
  Exact overrides
```

Runtime status and condition explanations come from the Python snapshot.
Structure scopes and conditions are editable. The current editor exposes
validated JSON for the closed condition language; it is not arbitrary
expression evaluation. Structured condition controls remain a presentation
follow-up and must produce the same typed Python condition data.

Every mutation validates the complete candidate flow and replays the current
line before atomic persistence. Development assignments also expose a
non-mutating validation endpoint. A richer before/after impact preview—covering
TOML diffs, stored branches, newly shadowed items, and decision changes—remains
planned and must not weaken this validation boundary.
