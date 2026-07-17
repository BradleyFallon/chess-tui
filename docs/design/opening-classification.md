# Deterministic Opening Classification

## Status

Implemented design specification.

## Purpose and boundary

The bundled `lichess-org/chess-openings` data is the application's sole source
for ECO codes, established opening and variation names, standard opening move
sequences, transpositions, and book continuations. Classification is offline
and deterministic at runtime.

Opening data answers what established theory calls a position. Flow policy
answers which authored move this application chooses. A book-supported policy
move does not make the opening data part of the rule, and a policy-only move
does not create a new opening classification.

React displays Python results. It never classifies a FEN or reconstructs book
alignment.

## Provenance and updates

The pinned source is stored in:

```text
data/openings/lichess/
  VERSION
  LICENSE
  openings.tsv
```

`VERSION` contains the full upstream Git commit. `openings.tsv` is the
header-preserving concatenation of upstream `a.tsv` through `e.tsv` at that
revision. `LICENSE` is the upstream CC0 dedication.

After intentionally replacing those three source artifacts, rebuild with:

```bash
source ./activate
python scripts/build_opening_index.py
```

The script validates the TSV schema, ECO codes, non-empty names and PGNs,
duplicate records, every move's legality, and the revision format. It writes
the deterministic packaged artifact:

```text
src/chess_tui/opening/data/lichess-index.json
```

Normal startup performs no download or build.

## Position graph

Every source PGN is replayed with `python-chess`. Position identity uses the
same four-field key as flow overrides and engine caching:

```text
piece placement + side to move + castling rights + en-passant square
```

Move clocks are ignored. Castling and en-passant state are not.

Each graph node keeps two concepts separate:

- `matches`: records whose named line ends at exactly this position.
- Route membership and continuations: records whose line passes through this
  position.

Only terminal matches classify the current position. Route membership supplies
direct next moves and descendant defense families. This prevents `1.d4` from
being labeled as every later Queen's Pawn variation while still allowing the
application to report defenses that remain reachable.

Because graph keys describe positions rather than SAN prefixes, different
legal move orders that reach the same normalized position use the same matches
and continuations. Multiple terminal records are retained. The primary match
is selected by:

1. Most specific structured name (family, variation, subvariation).
2. Deepest named source line.
3. ECO code, name, and stable source record id.

## Opening context and transitions

Every committed move creates an immutable `OpeningHistoryEntry` containing its
SAN, UCI, ply, normalized position, and `OpeningContext`. The context contains:

- Primary, current, and last-known matches.
- Entered, maintained, and exited record sets.
- Whether the played move was a direct indexed continuation.
- Current book continuations.
- Book defense families still reachable through indexed routes.
- Move provenance and policy, override, or recorded-reply identifiers.

`last_known_match` is the most recent named match on an earlier ply. A current
match is always read from `primary_match`.

An entry is a transition when a match was entered or exited, or when policy
began operating without book support. Other entries render compactly. Returning
to a named node after an unknown node is a deterministic transposition
re-entry, not a guessed classification.

Reachable defenses are unique opening families containing the upstream term
`Defense` among records whose routes still pass through the current node.
They are not ranked or described as likely because the source contains no
frequency data.

## Replay and branch history

`FlowWorkspace` stores the current line's opening entries and an in-memory map
of explored entries keyed by complete SAN path. Back and Restart clear or
shorten only the current line. They do not delete explored branch nodes or
persisted opponent replies.

Replay recomputes opening identity from the bundled graph and policy provenance
from the replayed policy. Explicit opponent provenance such as engine or manual
selection is retained for explored in-memory branches. A branch loaded from
flow TOML is identified as a recorded branch. Canonical flow TOML does not
persist derived opening data because it can be reproduced from the pinned
dataset and move history.

## Book and policy provenance

Controlled moves use:

- `book-and-policy`: an abstract rule selected the move and the graph contained
  it as a continuation.
- `policy-only`: an abstract rule selected it without graph support.
- `exact-override`: the policy resolver selected an exact-position override;
  book alignment remains available separately.
- `frontier`: no policy move resolved. Frontier attempts are not opening
  history until a move is committed.

Opponent moves use `recorded-branch`, `book`, `engine`, or `manual`. Opponent
replies are never represented as controlled-side policy rules.

## Timeline and commands

Each committed move is followed by a dedicated `commentary` application event
with an `opening-context` attachment in the ordered Development Mode timeline.
It is structured deterministic output, not an LLM or assistant message.
Automatic commentary presents only the primary match selected by the ordering
above. It uses the variation name when one exists, so a position may read
“Accelerated London System” instead of repeating the full family-qualified
name. The source has no frequency data, so this is a deterministic best match,
not a “most common” claim.

The current primary match can be explicitly promoted to an authored flow label.
Labels persist in canonical TOML as `{ eco, name }`, not as generated record
ids, and do not affect classification or policy resolution. This lets one flow
carry broader and narrower associations accumulated while developing it, such
as both `Queen's Pawn Game` and
`Queen's Pawn Game: Accelerated London System`. The same mechanism applies when
later positions identify a named gambit, attack, or tactical variation.

Development Mode also exposes:

- `/opening`
- `/openings`
- `/defenses`
- `/book`
- `/book-history`

These commands return typed attachments. The workspace snapshot exposes the
current context and current-line history directly.

## Future LLM boundary

A future LLM may consume `get_current_opening_context`,
`get_opening_history`, `get_book_continuations`,
`get_reachable_defenses`, `compare_move_to_book`, and
`find_book_policy_transition`. It may explain those results. It must not infer
opening identity from raw FEN or replace the deterministic classifier.
