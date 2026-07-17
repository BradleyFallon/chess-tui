# Deterministic Rule Policy — Version 2

> Canonical authored piece references, typed development rules, compilation,
> statuses, and intrinsic move/capture retirement are defined in
> [piece-development-authoring.md](piece-development-authoring.md). That
> specification supersedes older original-square authoring examples.

## Status

Implemented design specification.

This document defines the active version 2 flow schema and policy runtime for deterministic, rule-based chess opening flows.

## 1. Purpose

The retired version 1 format represented White’s opening primarily as:

* Numbered default moves
* Exact-position exceptions
* Recorded Black replies

That model works for memorizing a specific sequence, but it does not naturally express how a player thinks about an opening system.

A player may instead think:

* Move the d-pawn before developing the dark-squared bishop.
* Move the e-pawn after the bishop is developed.
* Develop the kingside knight after the basic London structure is complete.
* Play c4 after Black’s original b8 knight reaches c6.
* Retreat the dark-squared bishop before continuing development if it is attacked.

These rules may apply across many move orders and board states.

Version 2 introduces a deterministic abstract rule system.

> A rule may match many positions, but every resolved position has exactly one correct flow move.

---

## 2. Design principles

The policy system follows these principles:

1. **Many positions may map to one rule.**
2. **Every rule specifies one concrete move.**
3. **The resolver returns one move or a flow frontier.**
4. **Rule priority is explicit.**
5. **Move legality is automatic.**
6. **Rules have a lifecycle.**
7. **Original pieces retain stable identities.**
8. **Exact-position overrides remain supported.**
9. **Policy state can be deterministically replayed.**
10. **The policy must explain why a rule won.**

---

## 3. Goals

Version 2 should support:

* Broad conditions that apply across transpositions
* Original-piece identity based on the starting position
* Current piece location
* Historical piece movement
* Square occupancy
* Piece attacks
* Reusable named condition states
* Latched rule activation
* Rule retirement and pruning
* Explicit priority ordering
* Automatic legality filtering
* Exact-position overrides
* Deterministic replay
* Back navigation
* Decision traces
* Manual TOML editing

---

## 4. Non-goals

The first implementation will not support:

* Multiple equally correct moves
* Candidate move lists
* Engine-selected rule actions
* Arbitrary scripts or expressions
* Instructions such as “improve the worst piece”
* Instructions such as “move any attacked piece”
* Automatic priority based on specificity
* Reusable rules that reactivate repeatedly
* Generic tactical move selection
* Automatic flow-strength or Elo ratings
* A graphical condition-builder UI

Every rule must identify one concrete move.

---

# 5. Top-level flow schema

```toml
version = 2
name = "London System"
start_fen = "startpos"
side = "white"
opening_tags = [
  { eco = "A40", name = "Queen's Pawn Game" },
  { eco = "D00", name = "Queen's Pawn Game: Accelerated London System" },
]
```

## Fields

### `version`

Schema version.

Version 2 enables:

* Abstract rules
* Named states
* Original-piece identity
* Rule lifecycle

### `name`

Human-readable flow name.

### `start_fen`

The position from which the flow begins.

The implementation may accept:

```toml
start_fen = "startpos"
```

as shorthand for the standard chess starting position.

Original-piece identity is established from this position.

### `side`

The side controlled by the flow.

```toml
side = "white"
```

White and Black flows are separate policies. Piece identifiers always use explicit colors rather than relative terms.

### `opening_tags`

Optional authored metadata associating the flow with established opening,
system, gambit, attack, or tactical variation names. Each item contains the
upstream ECO code and exact name:

```toml
opening_tags = [{ eco = "D00", name = "Queen's Pawn Game: Accelerated London System" }]
```

Opening tags do not participate in policy resolution and do not claim that
every reachable position has that classification. Development Mode may offer a
deterministic current match as a candidate, but adding or removing a label is
an explicit authoring action. Generated opening record ids are never persisted.

Use:

```text
piece:white:knight:kingside
piece:black:knight:queenside
```

Do not use:

```text
us:g1
them:b8
```

---

# 6. Original-piece identity

Each piece present in `start_fen` receives an identity based on:

* Its color
* Its starting square

Authored data names that internal identity with `StartingPieceRef`. For example,
`piece:white:pawn:d` maps to the internal
`OriginalPieceId("white", "d2")`; original-square strings are not an authored
syntax.

Examples from the standard starting position:

```text
piece:white:pawn:d
piece:white:bishop:queenside
piece:white:knight:kingside
piece:black:knight:queenside
piece:black:knight:kingside
```

These identify specific original pieces:

```text
piece:white:pawn:d  = White’s original d-pawn
piece:white:bishop:queenside  = White’s original c1 bishop
piece:white:knight:kingside  = White’s original g1 knight
piece:black:knight:queenside  = Black’s original b8 knight
```

Original-piece identity is different from current board occupancy.

The runtime must distinguish:

```text
The original g1 knight has moved.
```

from:

```text
A White knight is currently on f3.
```

and from:

```text
The original g1 knight is currently on f3.
```

---

# 7. Move actions

Each rule specifies exactly one move using:

* Original-piece identity
* Destination square

```toml
move = {
  piece = "piece:white:pawn:c",
  to = "c4",
}
```

Other examples:

```toml
move = {
  piece = "piece:white:pawn:d",
  to = "d4",
}
```

```toml
move = {
  piece = "piece:white:bishop:queenside",
  to = "f4",
}
```

```toml
move = {
  piece = "piece:white:knight:kingside",
  to = "f3",
}
```

## Resolution

To resolve an action, the policy runtime:

1. Finds the original piece’s current square.
2. Constructs a move from its current square to the configured destination.
3. Checks that the move is legal.
4. Derives SAN for display.

The same rule may therefore apply from more than one current square.

For example:

```toml
move = {
  piece = "piece:white:pawn:c",
  to = "c4",
}
```

may resolve when the original c-pawn is currently on:

* `c2`
* `c3`

provided moving it to `c4` is legal.

## Deferred action types

The initial move action does not need to model every chess action.

Later versions may add explicit support for:

* Promotion
* Castling
* En passant-specific actions

---

# 8. Named states

A named state is a reusable condition expression.

A state has:

* A unique ID
* A condition expression

A state does not have:

* A move
* A priority
* A lifecycle

Example:

```toml
[[states]]
id = "london-before-nf3"

when = { all = [
  { at = {
      piece = "piece:white:pawn:d",
      square = "d4",
  } },
  { at = {
      piece = "piece:white:bishop:queenside",
      square = "f4",
  } },
  { at = {
      piece = "piece:white:pawn:e",
      square = "e3",
  } },
] }
```

Another state may reference it:

```toml
[[states]]
id = "london-core"

when = { all = [
  { state = "london-before-nf3" },
  { at = {
      piece = "piece:white:knight:kingside",
      square = "f3",
  } },
] }
```

State references must not form cycles.

---

# 9. Rule schema

A rule has:

* A unique ID
* A unique priority
* One move action
* An optional activation condition
* An optional retirement condition
* An optional note
* An optional enabled flag

```toml
[[rules]]
id = "play-c4-against-nc6"
priority = 700
note = "Challenge Black's center after ...Nc6."

move = {
  piece = "piece:white:pawn:c",
  to = "c4",
}

activate_when = { at = {
  piece = "piece:black:knight:queenside",
  square = "c6",
} }

retire_when = { moved = "piece:white:pawn:c" }
```

## Required fields

| Field      | Meaning                       |
| ---------- | ----------------------------- |
| `id`       | Stable unique rule identifier |
| `priority` | Unique integer priority       |
| `move`     | One concrete move action      |

## Optional fields

| Field           | Default                           |
| --------------- | --------------------------------- |
| `note`          | No explanation                    |
| `enabled`       | `true`                           |
| `activate_when` | Rule begins active                |
| `retire_when`   | Rule retires only after execution |

All rules are one-shot in the first implementation.

When a rule’s configured move is committed, that rule retires.

---

# 10. Rule lifecycle

Every rule has one runtime state:

```text
DORMANT
ACTIVE
RETIRED
```

## Dormant

The rule has an activation condition that has not yet become true.

## Active

The rule participates in priority resolution.

## Retired

The rule is permanently removed from consideration on the current line.

## State transitions

```text
DORMANT
   |
   | activate_when becomes true
   v
ACTIVE
   |
   | retire_when becomes true
   | or configured move is committed
   v
RETIRED
```

A retired rule does not reactivate in the first implementation.

---

# 11. Activation

Rules may define:

```toml
activate_when = { ... }
```

If `activate_when` is omitted, the rule begins active.

## Latched activation

Activation is latched.

Once a dormant rule becomes active, it remains active even if its activation condition later becomes false.

Example:

```toml
activate_when = { at = {
  piece = "piece:black:knight:queenside",
  square = "c6",
} }
```

When Black’s original b8 knight reaches c6, the rule activates.

If that knight later leaves c6, the rule remains active.

This represents:

> Once Black has shown this setup, add this response to the active plan.

---

# 12. Retirement and pruning

Rules may define:

```toml
retire_when = { ... }
```

When the retirement condition becomes true, the rule is permanently retired on the current line.

Example:

```toml
retire_when = { moved = "piece:white:pawn:d" }
```

This means the rule is no longer relevant once White’s original d-pawn has moved.

The pawn does not need to have moved to the preferred destination.

Retirement applies to both:

* Dormant rules
* Active rules

If activation and retirement become true during the same transition, retirement wins.

## Retirement on execution

In the first implementation, successfully committing a rule’s configured move retires that rule automatically.

A recommendation alone does not consume a rule.

The move must be committed.

---

# 13. Condition language

The initial schema uses a closed set of conditions.

Supported atomic conditions:

* `moved`
* `at`
* `occupied`
* `empty`
* `occupied_by`
* `attacked`
* `attacked_by`
* `in_check`
* `state`

Supported logical combinators:

* `all`
* `any`
* `not`

Arbitrary expressions, scripts, and user-defined code are not supported.

---

## 13.1 `moved`

```toml
{ moved = "piece:white:knight:kingside" }
```

True when the original piece has made at least one move.

This remains true if the piece later returns to its starting square.

---

## 13.2 `at`

```toml
{ at = {
    piece = "piece:black:knight:queenside",
    square = "c6",
} }
```

True when the specified original piece is currently on the specified square.

---

## 13.3 `occupied`

```toml
{ occupied = "c5" }
```

True when any piece currently occupies the square.

---

## 13.4 `empty`

```toml
{ empty = "c5" }
```

True when no piece currently occupies the square.

---

## 13.5 `occupied_by`

```toml
{ occupied_by = {
    square = "c5",
    color = "black",
    type = "pawn",
} }
```

True when the square contains a current piece matching:

* Color
* Piece type

This predicate does not identify the original piece.

---

## 13.6 `attacked`

```toml
{ attacked = "piece:white:bishop:queenside" }
```

True when the specified original piece:

* Is still on the board
* Is currently attacked by the opposing side

The piece may be on any current square.

---

## 13.7 `attacked_by`

```toml
{ attacked_by = {
    target = "piece:white:bishop:queenside",
    attacker = "piece:black:knight:kingside",
} }
```

True when the specified original attacker currently attacks the specified original target.

Both pieces must still be present.

---

## 13.8 `in_check`

```toml
{ in_check = "white" }
```

True when the specified color is currently in check.

---

## 13.9 `state`

```toml
{ state = "london-before-nf3" }
```

True when the named state evaluates true.

---

# 14. Logical combinators

## `all`

```toml
activate_when = { all = [
  { moved = "piece:white:pawn:d" },
  { moved = "piece:white:bishop:queenside" },
] }
```

True when all nested conditions are true.

## `any`

```toml
activate_when = { any = [
  { at = {
      piece = "piece:black:knight:queenside",
      square = "c6",
  } },
  { at = {
      piece = "piece:black:knight:queenside",
      square = "a6",
  } },
] }
```

True when at least one nested condition is true.

## `not`

```toml
activate_when = { all = [
  { state = "london-before-nf3" },
  { not = {
      in_check = "white",
  } },
] }
```

True when the nested condition is false.

Logical combinators may be nested.

---

# 15. Move legality

Move legality is not an authored condition.

The schema must not support:

```toml
{ move_legal = "c4" }
```

The policy resolver always checks legality automatically.

For each active rule:

1. Locate the original piece.
2. Construct the move.
3. Test legality.
4. Skip the rule if illegal.
5. Select it if legal.

An illegal active rule:

* Is not selected
* Is not retired
* Remains active
* May become legal later

---

# 16. Priority

Multiple rules may be active simultaneously.

The highest-priority active legal rule wins.

Example:

```text
1000  retreat-dark-bishop
700   play-c4-against-nc6
380   develop-e-pawn
370   develop-kingside-knight
```

If the bishop retreat rule is active and legal, it wins.

Otherwise the c4 rule may win.

If c4 is currently illegal, resolution continues to lower-priority rules.

## Suggested priority ranges

```text
1000–1099  Immediate tactical responses
700–899    Opponent-specific reactions
400–699    Positional plans
100–399    Default development
```

These ranges are conventions for readability.

The resolver only uses numeric priority.

## Unique priorities

Version 2 requires every rule priority to be unique.

This is invalid:

```toml
[[rules]]
id = "rule-a"
priority = 700

[[rules]]
id = "rule-b"
priority = 700
```

The loader should report:

```text
Duplicate rule priority 700:
- rule-a
- rule-b
```

The resolver must not use declaration order as a hidden tie-breaker.

A future editor may present priority as an ordered list and generate numeric values automatically.

---

# 17. Policy resolution order

At every controlled-side turn:

```text
1. Exact-position override
2. Highest-priority active legal abstract rule
3. Flow frontier
```

This ordering must remain explicit.

---

# 18. Resolver algorithm

```python
def resolve(
    board: chess.Board,
    runtime: PolicyRuntime,
) -> PolicyDecision | None:
    override = runtime.exact_override_for(board)
    if override is not None:
        return override

    for rule in runtime.active_rules_by_priority:
        move = runtime.construct_move(board, rule.move)

        if move is None:
            continue

        if move not in board.legal_moves:
            continue

        return PolicyDecision.from_rule(
            board=board,
            rule=rule,
            move=move,
        )

    return PolicyDecision.frontier(runtime.trace)
```

If no exact override or abstract rule resolves, the policy reaches the flow frontier.

---

# 19. Lifecycle update order

After every committed move:

1. Update the board.
2. Append SAN history.
3. Update original-piece locations.
4. Mark the moved original piece as moved.
5. Record captured original pieces.
6. Evaluate relevant retirement conditions.
7. Retire matching dormant or active rules.
8. Evaluate relevant activation conditions.
9. Activate matching dormant rules.
10. Refresh the active priority structure.

Retirement is processed before activation.

---

# 20. Original-piece runtime tracking

The runtime must maintain information similar to:

```python
@dataclass(frozen=True, slots=True)
class OriginalPieceRuntime:
    id: OriginalPieceId
    piece_type: chess.PieceType
    current_square: chess.Square | None
    has_moved: bool
    captured: bool
    first_moved_ply: int | None
    captured_ply: int | None
```

Example:

```python
{
    OriginalPieceId("white", "d2"): OriginalPieceRuntime(
        current_square=chess.D4,
        has_moved=True,
        captured=False,
        first_moved_ply=1,
        captured_ply=None,
    ),
    OriginalPieceId("white", "c1"): OriginalPieceRuntime(
        current_square=chess.F4,
        has_moved=True,
        captured=False,
        first_moved_ply=3,
        captured_ply=None,
    ),
}
```

This tracker is initialized from `start_fen`.

It must be updated through move replay.

---

# 21. Efficient rule narrowing

Correctness should be implemented before optimization.

Once lifecycle behavior works, rules should be indexed by facts that may activate or retire them.

Example indexes:

```text
at:piece:black:knight:queenside:c6
    → play-c4-against-nc6

attacked:piece:white:bishop:queenside
    → retreat-dark-bishop

moved:piece:white:pawn:d
    → develop-dark-bishop

state:london-before-nf3
    → develop-kingside-knight
```

After a move, determine which facts changed:

* Moved original piece
* Changed square occupancy
* Captured original piece
* Attack relationships
* Check state
* Affected named states

Only relevant dormant and live rules need to be reevaluated.

Possible runtime structures:

```python
dormant_by_activation_fact
live_by_retirement_fact
active_rules_by_priority
state_dependency_index
original_piece_tracker
```

The active rule set should normally remain small.

---

# 22. Complete example

```toml
version = 2
name = "London System"
start_fen = "startpos"
side = "white"

[[states]]
id = "london-before-nf3"

when = { all = [
  { at = {
      piece = "piece:white:pawn:d",
      square = "d4",
  } },
  { at = {
      piece = "piece:white:bishop:queenside",
      square = "f4",
  } },
  { at = {
      piece = "piece:white:pawn:e",
      square = "e3",
  } },
] }

[[rules]]
id = "retreat-dark-bishop"
priority = 1000
note = "Preserve the London bishop before continuing development."

move = {
  piece = "piece:white:bishop:queenside",
  to = "g3",
}

activate_when = {
  attacked = "piece:white:bishop:queenside",
}

[[rules]]
id = "play-c4-against-nc6"
priority = 700
note = "Challenge Black's center after ...Nc6."

move = {
  piece = "piece:white:pawn:c",
  to = "c4",
}

activate_when = { at = {
  piece = "piece:black:knight:queenside",
  square = "c6",
} }

retire_when = {
  moved = "piece:white:pawn:c",
}

[[rules]]
id = "develop-d-pawn"
priority = 400
note = "Claim the center."

move = {
  piece = "piece:white:pawn:d",
  to = "d4",
}

retire_when = {
  moved = "piece:white:pawn:d",
}

[[rules]]
id = "develop-dark-bishop"
priority = 390
note = "Develop the bishop outside the pawn chain."

move = {
  piece = "piece:white:bishop:queenside",
  to = "f4",
}

activate_when = {
  moved = "piece:white:pawn:d",
}

retire_when = {
  moved = "piece:white:bishop:queenside",
}

[[rules]]
id = "develop-e-pawn"
priority = 380
note = "Support d4 and open the light-squared bishop."

move = {
  piece = "piece:white:pawn:e",
  to = "e3",
}

activate_when = { all = [
  { moved = "piece:white:pawn:d" },
  { moved = "piece:white:bishop:queenside" },
] }

retire_when = {
  moved = "piece:white:pawn:e",
}

[[rules]]
id = "develop-kingside-knight"
priority = 370
note = "Complete the basic London development."

move = {
  piece = "piece:white:knight:kingside",
  to = "f3",
}

activate_when = {
  state = "london-before-nf3",
}

retire_when = {
  moved = "piece:white:knight:kingside",
}
```

---

# 23. Example resolution

Suppose these rules are active:

| Rule                      | Priority | Configured move |
| ------------------------- | -------: | --------------- |
| `retreat-dark-bishop`     |     1000 | Bishop to g3    |
| `play-c4-against-nc6`     |      700 | c-pawn to c4    |
| `develop-e-pawn`          |      380 | e-pawn to e3    |
| `develop-kingside-knight` |      370 | Knight to f3    |

## Bishop attacked

If the original c1 bishop is attacked and moving it to g3 is legal:

```text
Selected rule:
retreat-dark-bishop

Move:
Bg3
```

## Bishop not attacked, c4 available

If the bishop rule is not active and the c4 rule is active:

```text
Selected rule:
play-c4-against-nc6

Move:
c4
```

## c4 temporarily illegal

If the c4 rule is active but the move is illegal:

```text
Skipped:
play-c4-against-nc6

Selected:
develop-e-pawn

Move:
e3
```

The c4 rule remains active.

---

# 24. Decision traces

Every recommendation should expose why it was selected.

Example:

```text
RECOMMENDED: c4

Winning rule:
play-c4-against-nc6

Priority:
700

Activated because:
Black's original b8 knight reached c6.

Lifecycle:
ACTIVE

Retires when:
White's original c-pawn moves.

Higher-priority rules:
1000 retreat-dark-bishop — DORMANT

Shadowed active rules:
380 develop-e-pawn
370 develop-kingside-knight
```

Suggested internal representation:

```python
@dataclass(frozen=True, slots=True)
class DecisionTrace:
    selected_rule_id: str
    selected_priority: int
    active_rule_ids: tuple[str, ...]
    skipped_illegal_rule_ids: tuple[str, ...]
    shadowed_rule_ids: tuple[str, ...]
    explanation: tuple[str, ...]
```

The full trace should be available for:

* Tests
* Diagnostics
* Flow Development Mode
* Rule debugging

Quiz Mode may show only a simplified explanation after the user submits a move.

---

# 25. Exact-position overrides

Exact-position overrides remain the strongest policy mechanism.

They are appropriate when:

* A tactical position requires one special move
* A broad rule has an unusual exception
* Move order creates a concrete threat
* A general move is inappropriate in one exact position
* Two broad plans require a special resolution

Exact overrides do not need abstract lifecycle behavior in the initial implementation.

They are authored with a legal SAN prefix and the same original-piece action
used by abstract rules:

```toml
[[overrides]]
id = "after-d4-e5"
after = ["d4", "e5"]
note = "Capture the offered pawn."
move = { piece = "piece:white:pawn:d", to = "e5" }
```

The loader replays `after` from `start_fen` and indexes the override by the
first four FEN fields. Duplicate normalized positions are rejected. Overrides
may set `enabled = false`; they do not otherwise have lifecycle state.

---

# 26. Determinism and replay

Because activation is latched and execution retires rules, board position alone does not define complete policy state.

Deterministic policy state includes:

```text
Board
+ SAN history
+ original-piece tracker
+ rule lifecycle
```

Two identical board positions reached through different histories may have different rule lifecycle states.

This is acceptable and intentional.

The same complete history must always reproduce the same:

* Piece identities
* Moved flags
* Captured flags
* Active rules
* Dormant rules
* Retired rules
* Selected move
* Decision trace

---

# 27. Back navigation

Back navigation must restore:

* Board position
* SAN history
* Original-piece tracker
* Moved-piece history
* Captured-piece state
* Rule lifecycle
* Current recommendation
* Decision trace

The simplest correct implementation is:

1. Truncate the active SAN history.
2. Rebuild the board from `start_fen`.
3. Replay each move.
4. Apply lifecycle transitions after every move.

In-memory snapshots may later optimize this.

Back navigation must not automatically delete:

* Rules
* Exact overrides
* Recorded opponent replies
* Other explored branches

Navigation and destructive editing are separate operations.

---

# 28. Validation

The loader must reject:

* Duplicate state IDs
* Duplicate rule IDs
* Duplicate priorities
* Invalid original-piece IDs
* Original-piece IDs absent from `start_fen`
* Invalid colors
* Invalid squares
* Invalid piece types
* Unknown state references
* Recursive state cycles
* Missing move actions
* More than one move action per rule
* Rules that move the uncontrolled side
* Unsupported condition types
* Malformed condition expressions
* Authored legality predicates
* Duplicate exact overrides for one normalized position

## Useful warnings

The system may also warn when:

* A named state is never referenced
* A rule retires before it can activate
* A rule appears permanently shadowed
* A rule never activates in stored test positions
* A rule action is never legal when its activation trigger occurs
* A retirement condition is already true in the starting position

Warnings should not silently alter behavior.

---

# 29. Proposed internal types

```python
@dataclass(frozen=True, slots=True)
class OriginalPieceId:
    color: chess.Color
    start_square: chess.Square
```

```python
@dataclass(frozen=True, slots=True)
class MoveAction:
    piece: OriginalPieceId
    to_square: chess.Square
```

```python
@dataclass(frozen=True, slots=True)
class AbstractRule:
    id: str
    priority: int
    move: MoveAction
    activate_when: Condition | None
    retire_when: Condition | None
    note: str | None
```

```python
class RuleStatus(str, Enum):
    DORMANT = "dormant"
    ACTIVE = "active"
    RETIRED = "retired"
```

```python
@dataclass(frozen=True, slots=True)
class RuleRuntime:
    rule_id: str
    status: RuleStatus
    activated_at_ply: int | None = None
    retired_at_ply: int | None = None
    retirement_reason: str | None = None
```

```python
@dataclass(frozen=True, slots=True)
class PolicyDecision:
    move: chess.Move
    move_san: str
    rule_id: str
    priority: int
    note: str | None
    trace: DecisionTrace
```

---

# 30. Version compatibility

Only version 2 is supported. Version 1 files and mixed schemas fail validation;
there is no fallback parser or resolver.

---

# 31. Implementation phases

## Phase 1: schema and validation

Implement:

* Version 2 models
* Original-piece IDs
* Move actions
* Condition AST
* Named states
* TOML parsing
* Validation

Exit criterion:

> The example version 2 flow loads successfully and invalid files fail clearly.

## Phase 2: original-piece replay

Implement:

* Original-piece tracker
* Current-square tracking
* Moved flags
* Captured flags
* Deterministic replay

Exit criterion:

> Replaying a line recreates the same original-piece state.

## Phase 3: lifecycle runtime

Implement:

* Dormant rules
* Active rules
* Retired rules
* Latched activation
* Retirement conditions
* Retirement on execution

Exit criterion:

> Replaying a line recreates the same rule lifecycle.

## Phase 4: resolver

Implement:

* Exact override precedence
* Priority ordering
* Move construction
* Automatic legality filtering
* Flow frontier
* Decision traces

Exit criterion:

> Every tested controlled-side position returns one deterministic move or frontier.

## Phase 5: workspace integration

Integrate version 2 policy decisions with:

* FlowWorkspace
* Quiz Mode
* Flow Development Mode
* Retry and mismatch behavior
* Back navigation

## Phase 6: optimization

Add:

* Activation indexes
* Retirement indexes
* State dependency indexes
* Active priority structures

Only optimize after behavior is correct and fully tested.

---

# 32. MVP acceptance criteria

The version 2 policy foundation is complete when:

1. One rule can match multiple board states.
2. Every rule specifies one concrete move.
3. The original c2 pawn can move to c4 from any legal current square.
4. A rule activates when Black’s original b8 knight reaches c6.
5. That activation remains latched if the knight later leaves c6.
6. A development rule retires once its original piece moves.
7. Retirement can occur before activation.
8. An attacked-bishop rule can outrank development.
9. Multiple active rules are ordered by unique priority.
10. Illegal active moves are skipped automatically.
11. Illegal active moves do not retire their rules.
12. Exact overrides outrank abstract rules.
13. Replay produces deterministic lifecycle state.
14. Back restores complete policy state.
15. Decision traces identify the winning rule.
16. Version 1 flows fail strict validation.
17. No authored legality predicate exists.

---

# 33. Deferred questions

## Reusable rules

The first implementation treats every rule as one-shot.

A later version may add:

```toml
lifetime = "reusable"
```

Only after clear recurring use cases are identified.

## Captured conditions

The runtime should track capture immediately.

An authored predicate such as:

```toml
{ captured = "piece:white:bishop:queenside" }
```

may be added later if real flow designs require it.

## Castling

Castling may eventually use a dedicated action:

```toml
move = {
  castle = "white:kingside",
}
```

It should not be forced into an ordinary original-piece destination action without design review.

## Promotion

Promotion actions may later require:

```toml
move = {
  piece = "piece:white:pawn:a",
  to = "a8",
  promote = "queen",
}
```

## Priority editing

The stored schema uses integers.

User interfaces should normally present priorities as a reorderable list rather than requiring manual number editing.

---

# 34. Final rule-system principle

> Original-piece and board-state facts define activation and retirement conditions. Activation adds rules to the active plan. Retirement prunes them. Explicit priority ranks active rules. Automatic legality filters them. Every rule specifies one concrete move, while exact-position overrides remain available for special cases.
