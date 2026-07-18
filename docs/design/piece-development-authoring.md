# Piece-centered development authoring (Historical v2 slice)

> The authoritative piece-development schema and runtime are now part of
> [rule-policy-v3.md](rule-policy-v3.md). This document records the former v2
> implementation and must not override v3 structure-scoped assignments or
> authored-order semantics.
>
> The current piece-centered browser interaction, guided readiness editor,
> review workflow, condition builder, and diagnostics disclosure are defined in
> [rule-authoring-ui.md](rule-authoring-ui.md). The JSON-first editor described
> below is historical and is no longer the primary web experience.

## Starting-piece references

Authored TOML, condition data, and API mutations use:

```text
piece:<color>:<type>[:<qualifier>]
```

Colors are `white` and `black`. Pawns require a file qualifier from `a` through
`h`. Rooks, knights, and bishops require `queenside` or `kingside`. Queens and
kings have no qualifier. Examples:

```text
piece:white:pawn:d
piece:white:bishop:queenside
piece:white:knight:kingside
piece:black:queen
```

The parser rejects original-square strings and invalid type/qualifier
combinations. `StartingPieceRef` maps the readable reference to internal
`OriginalPieceId`; for example, `piece:white:pawn:d` maps to
`OriginalPieceId("white", "d2")`. Only the readable form is authored or accepted
by mutation APIs.

## Mechanical piece state

Python tracks each original piece through replay. A piece is `undeveloped` only
while it exists and has never moved. Its complete state is one of:

```text
undeveloped
developed
captured-undeveloped
captured-developed
```

The tracker records `first_moved_ply` and `captured_ply`. This definition is
mechanical and makes no strategic judgment.

## Authored development rules

```toml
[[rules]]
id = "develop-white-queenside-bishop"
kind = "development"
piece = "piece:white:bishop:queenside"
target = "f4"
priority = 900
ready_when = { moved = "piece:white:pawn:d" }
note = "Develop outside the pawn chain."
```

`ready_when`, `note`, and `enabled` are optional. A flow may contain at most one
development rule per starting piece. Development order is presented in the UI;
Python converts it to unique deterministic priorities.

At load and replay time, each `DevelopmentRule` compiles to the existing
`PolicyRule` shape:

```text
piece + target → original-piece MoveAction
ready_when     → activate_when
assigned piece → intrinsic move/capture retirement
```

The compiled rule enters the normal exact-override, priority, legality,
lifecycle, trace, replay, and Back pipeline. Exact overrides still resolve
first. Generic rules remain supported and may use priorities above the
development sequence.

The API/UI statuses map from the existing runtime:

```text
dormant   ready_when is false
ready     active and legal, but not selected
waiting   active but target is currently illegal
selected  highest-priority applicable rule
retired   assigned piece moved or was captured
disabled  authored rule is disabled
```

## Web workflow

Piece inspection is always active. Clicking a piece updates the inspector and
also preserves ordinary move selection when that piece can move. Empty-square
clicks do not clear the inspected piece. Moved pieces are found through their
tracked current square; captured assigned pieces remain reachable from the
development-order list.

The left panel is ordered as:

```text
PIECE DEVELOPMENT
CURRENT DECISION
RULE STATUS
```

Every undeveloped on-board piece has a shape-and-color marker for unassigned,
dormant, ready, selected, waiting, or disabled status. Markers ignore pointer
input and follow the controlled-side board orientation.

Editing uses a local draft. `Choose target` temporarily consumes the next board
square click, previews that square, and waits for Apply or Cancel. Validation
serializes, reparses, and replays the candidate without writing. Apply, delete,
and reorder validate the complete flow, save atomically, replay the current
line, and return a complete workspace snapshot.

Deterministic operations are exposed as:

```text
POST   /development-rules/validate
POST   /development-rules
DELETE /development-rules/{rule_id}
PUT    /development-rules/order
```

These operations suit future tool adapters. They expose no raw TOML mutation
path and do not use an LLM.
