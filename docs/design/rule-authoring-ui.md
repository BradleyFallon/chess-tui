# Deterministic-v3 rule authoring UI

## Status

Implemented design for local Web Development Mode.

The browser edits the repository's strict version 3 flow through validated
Python candidate operations. It does not introduce another schema, resolver,
compatibility mode, feature flag, or frontend policy implementation.

## Workspace and product language

The normal interface is piece-centered and uses chess/teaching language:

```text
Piece
Current decision
Current plan
Development assignments
Special responses
Later plans
Exact fixes
Change authored order
Plans and structures
Condition library
Policy details
```

Friendly statuses are shown in normal cards. Authored IDs, numeric ply data,
exact lifecycle states, condition expressions, normalized position keys,
legality, warnings, decision traces, and TOML belong in **Policy details**.
Numeric priority is never shown because authored list order is semantic.

## Controlled and opponent pieces

Every original piece from both colors appears in the Python snapshot.
`authorable` is true only for the flow's controlled color.

A controlled piece exposes all development, response, continuation, and exact
fix authoring. An opponent piece is read-only: the inspector shows its original
identity, current square, and mechanical state, explains that it may be used in
conditions, and does not expose move-authoring controls. Both colors remain
grouped and selectable in every condition builder.

## Multiple development assignments

The inspector renders every assignment for the selected starting piece. Each
card shows target, human-readable structure scope, readiness, friendly status,
runtime reason, Edit, and Remove. Selection is keyed by assignment ID; array
position is never used to choose the edited assignment.

New and edited assignments support:

* a board target picker with text fallback;
* global fallback or one-or-more structure scopes;
* immediate readiness;
* one or multiple piece-development prerequisites;
* an advanced condition;
* a teaching note;
* validation, review, explicit Apply, and deletion.

Board markers aggregate every assignment for an undeveloped controlled piece:

```text
selected ★
applicable ●
waiting !
inactive ○
all out of scope ◇
unassigned +
```

The accessible label includes the current plan and every target, scope, and
runtime status. A global assignment suppressed by an in-scope scoped assignment
is shown as a fallback that is out of scope, with Python's exact reason.

## Conditions and named conditions

The visual AST covers every v3 operator:

```text
moved, unmoved, captured, at, occupied, empty, occupied_by,
attacked, attacked_by, in_check, last_move, condition, all, any, not
```

`unmoved` has its own node and round-trips as `{"unmoved": ...}`. It is not
logical `not moved`: a piece captured before moving satisfies `not moved` but
does not satisfy `unmoved`. Advanced JSON edits the same AST and must parse back
to a supported visual node. The named-condition choice is absent when the
library is empty.

The **Condition library** lists each condition, summary, and references. It
supports create, edit, explicit rename, and delete. Rename updates all nested
references atomically. Deleting a referenced condition fails with its dependency
list, leaving the flow and workspace unchanged.

## Plans and structures

**Current plan** shows the selected structure and rejected alternatives, or the
currently available and unavailable plans before selection. **Plans and
structures** supports create, edit, dependency-safe delete, and accessible
Earlier/Later ordering. Editors expose name, live availability, post-move
selection condition, and teaching note.

Structure transition semantics are Python-owned:

1. Preserve available structures before the move.
2. Commit the board, tracker, captures, last move, and lifecycle.
3. Select the first authored pre-move-available structure whose
   `selected_when` is true after the move.

Selection is latched. Replay, Back, Restart, exact fixes, and accepted attempts
use the same transition. Stored-branch overlap warnings identify all matching
structures and the authored-order winner.

## Responses and continuations

Special responses and Later plans reuse one move-rule editor. The presentation
language and destination section differ, while both expose every persisted
field:

```text
controlled piece and destination
structure scopes
historical unlock_when
live when
expire_when
teaching note
```

Historical unlocking is explained as latched for the line. Existing fields are
always visible and editable; the API requires the complete draft and does not
silently retain omitted metadata. Responses and continuations have separate
Earlier/Later ordering, preserving fixed cross-section precedence:

```text
exact fix -> response -> development -> continuation -> frontier
```

When a mismatch/frontier attempt starts **Create broader response**, Python
prefills only the attempted original piece, destination, and optional condition
suggestions. Suggestions are labeled choices; none is selected automatically.
If no suggestion is chosen, the author must define a live trigger. Previous-move
suggestions use `last_move`.

## Exact fixes and attempts

Exact-fix cards show the numbered SAN prefix, move, and reason. Authors may
create a fix for the current position, edit it, delete it, or replace the fix
for the same normalized position. Normalized keys stay in diagnostics.

Mismatch and frontier attempts expose:

```text
Accept in this position
Create broader response
Retry
```

Mismatches also expose **Use expected move**. **Accept in this position** and
`/accept-here` call the same `accept_attempt_as_override` operation. Python
restores the pre-attempt state, identifies the original piece, creates or
replaces the exact fix, validates and saves atomically, replays, commits the
attempt, and returns a refreshed snapshot. `/add-rule` is unsupported.

## Validation, review, and persistence

Every mutation follows:

```text
Edit -> Validate -> Review -> Apply -> Revalidate -> Atomic save -> Replay
```

Validation serializes and reparses the complete candidate, validates
dependencies and legality representation, and replays the active line without
writing. Reviews show natural-language summary, current/preview decision,
current/preview plan, affected order, dependencies, warnings, and the generated
condition under Advanced. Apply recreates the candidate; it never trusts stale
preview output.

Failures preserve the canonical file, backup, valid in-memory flow, board
history, attempt, selected structure, and lifecycle state.

## Diagnostics and accessibility

The focus-managed **Policy details** drawer covers selected item, structures,
responses, development, continuations, completed, waiting/blocked, out of
scope, exact fixes, decision trace, warnings, named conditions, and flow TOML.
Full section lists ensure ready/not-ready development items are not omitted.

Board target picking has a text alternative and live announcement. Condition
groups use fieldsets and labels. Ordering uses explicit Earlier/Later controls.
The diagnostics drawer focuses its close button, traps focus, closes on Escape,
restores opener focus, and uses dialog semantics.

## Remaining limits

This work does not add promotion actions, arbitrary condition expressions, an
LLM, autonomous rule generation, accounts, remote synchronization, or
frontend-owned chess/policy logic.
