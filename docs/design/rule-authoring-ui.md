# Piece-centered rule authoring UI

## Status

Implemented design for local Web Development Mode.

This is an authoring-experience redesign over the repository's existing strict
version 3 Python flow model. It does not introduce a new schema, resolver,
structure behavior, compatibility mode, or feature flag. The primary authoring
surface deliberately exposes only normal development, existing response rules,
and exact-position fixes.

## Product language

The normal interface starts with chess intent:

```text
Piece
Current decision
Normal development
Special responses
Exact fixes
Change rule order
```

Runtime names such as lifecycle, effective status, authored ID, raw condition
data, and TOML are confined to **Policy details**. Normal status labels are:

| Authored behavior | Normal labels |
| --- | --- |
| Development | Not ready, Ready, Recommended now, Blocked, Completed |
| Special response | Not triggered, Available, Recommended now, Blocked, Completed |
| Exact fix | Exact fix active, Applies in another position |

Python returns both the friendly and exact runtime status. React never derives
policy status or groups rules by parsing IDs.

## Always-active piece inspection

Every original tracked piece is present in `startingPieces`, including the
uncontrolled side and captured pieces. A board click inspects the current
occupant's original identity while retaining ordinary legal move selection.
Captured and moved pieces remain directly inspectable from Piece history,
including pieces with no authored rule.

Each starting-piece snapshot owns its mechanical identity and movement state,
development assignments, related response and other move rules, and exact fixes
whose action uses the piece. A rule relates to a piece when its Python-owned
move action uses that original piece.

## Guided development editing

Development editing uses one local draft with piece, target, readiness, and
reason. Readiness offers:

1. Immediately
2. After one or more pieces develop
3. Advanced condition

One prerequisite compiles to `{"moved": "<piece>"}`. Multiple prerequisites
compile to an `all` node. Existing structure scopes, if any, are preserved by
the focused editor but are not exposed or changed.

The workflow is:

```text
Edit -> Validate -> Review -> Apply
```

Validation serializes and reparses the complete candidate flow, replays the
active line, and reports the current and preview decisions without writing.
Apply repeats validation through the shared workspace mutation boundary, saves
atomically, and replays.

## Guided special responses

A special response is an existing v3 `[[responses]]` move rule presented as a
chess task. The wizard chooses its move and target, trigger, expiration, and
reason. Common triggers include an attacked piece, another original piece on a
square, and another piece having moved. Advanced triggers use the same visual
condition builder.

New response drafts are validated without persistence through
`POST /rules/drafts/validate`, then applied through `POST /rules`. Updates,
deletes, and ordering share the same complete-flow validation, atomic save, and
replay boundary.

## Condition builder

The frontend owns one typed draft AST. It converts losslessly to and from the
closed Python condition data for:

```text
piece moved or not moved
piece on square
occupied or empty square
square occupied by color and piece type
piece attacked
piece attacked by another original piece
side in check
named condition
all
any
not
```

“Has not moved” serializes as `{"not":{"moved":"..."}}`; this translation is
not shown in the normal editor.

Advanced condition source edits the same AST. Source must parse into a supported
visual node or the UI reports an error and retains the previous draft. There
are never independent visual and JSON copies of policy truth.

## Authored order

The UI shows **Special responses** and **Normal development order** with
accessible Earlier and Later buttons. The browser sends complete ID order to
Python. Python reorders only the requested authored section.

Version 3 has fixed cross-section precedence:

```text
exact fix -> response -> development -> continuation -> frontier
```

There are no numeric priorities to display or preserve. Reordering responses
cannot reorder development or continuations.

## Exact fixes

Normal exact-fix cards display a numbered chess line, move, and reason. Raw SAN
arrays and normalized-position details remain advanced diagnostics. Editing an
exact fix follows validate, review, and apply.

## Frontier and mismatch resolution

Both mismatch and frontier attempts expose:

```text
Accept in this position
Create broader response
Retry
```

Mismatches additionally expose **Use expected move**.

**Accept in this position** invokes `accept_attempt_as_override`, available as
the `/accept-here` command and `POST /attempt/accept-here`. Python:

1. Restores `attempt.history_before`.
2. Finds the moved original piece.
3. Creates or replaces the exact fix for the normalized position.
4. Validates and saves the complete flow atomically.
5. Replays the line.
6. Reassesses and commits the attempted move.
7. Returns a complete workspace snapshot.

The retired `/add-rule` command and route are not supported.

**Create broader response** opens the guided response wizard with the attempted
piece and destination from Python. Python may also return current board facts as
optional trigger suggestions. Nothing is applied until the user chooses a
trigger, reviews, and applies the draft.

## Advanced diagnostics

**Policy details** opens a focus-managed drawer containing the selected,
available, blocked, not-triggered, and completed items; exact fixes; the decision
trace; and flow TOML. This is the surface for authored IDs, exact runtime state,
lifecycle, legality, raw conditions, SAN source lines, and canonical TOML.

## Accessibility

Board target picking always has a text-input alternative. Target-picking state
is announced in a live region. Condition groups use fieldsets and labels.
Ordering has explicit button labels and is not drag-only. Status is always
written as text. The diagnostics drawer focuses its close control, traps
keyboard focus, closes on Escape, restores focus to its opener, and uses dialog
semantics.

## Current constraints

The repository already persists strict version 3 flows. This batch does not:

* add or migrate a schema;
* add structure or continuation authoring;
* change structure selection or response/development/continuation precedence;
* add `last_move` to the guided trigger choices;
* add promotion actions;
* add an LLM, autonomous condition generation, or frontend policy logic.

Future schema work can extend the draft and piece-authoring models without
replacing this interaction hierarchy.
