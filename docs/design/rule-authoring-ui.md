# Rule Authoring UI

Status: current UI contract for Opening Rule Engine v4. The domain semantics are
defined by [opening-rule-engine-v4.md](opening-rule-engine-v4.md).

The browser is a piece-centered authoring surface over Python-owned snapshots.
It never reconstructs legality, tactical relationships, rule status, scheduling,
or replay state.

## Inspector

Selecting any board piece opens the same inspector. A controlled piece shows
its default development, zero or more interrupt cards, current relationships,
and authoring controls. An opponent piece shows its alias, canonical identity,
current square, attacks, attackers, and defenses, with `authorable = false`.

The sections are Piece, Current decision, Default development, Interrupting
rules, Current board relationships, Development order, Interrupt order, and
Policy details.

Development and interrupt cards show Python-provided status and explanation.
The relationship summary is collapsed initially and expands into legal
attackers plus per-attacker recapture defenses.

## Guided interrupt workflow

The Add interrupt wizard has five steps:

1. Select a trigger: attempt legality, attacked, attacked by piece/type,
   under-defended, undefended, capturable enemy, exact position, or advanced
   condition.
2. Choose optional or required failure behavior.
3. Add and order move/capture attempts.
4. Write the required explanation.
5. Review validation, attempt diagnostics, preview decision, warnings, and
   generated TOML before Apply.

The condition builder also exposes every surviving history/position condition
and keeps `unmoved` distinct from `not(moved)`. Named conditions do not exist.

Earlier/Later buttons reorder development, interrupts, and attempts. Keyboard
focus remains on an equivalent control after an operation. Numeric priorities
are not shown or accepted.

## Mutation contract

Preview validates without persistence. Apply revalidates the complete
Rulebook, atomically saves with backup, replays the current history, and returns
one refreshed snapshot. Delete follows the same dependency validation.

A mismatch or frontier move can use `/accept-here`; the result is an
exact-position interrupt owned by the moving original piece. “Add interrupt
rule” is the broader, non-automatic authoring path.

Raw conditions, traces, warnings, normalized positions, and generated TOML
belong in Policy details. They support diagnosis without becoming a second
authoring model.
