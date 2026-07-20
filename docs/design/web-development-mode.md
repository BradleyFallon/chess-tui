# Local Web Development Mode

Status: current product and architecture contract. Opening policy semantics are
defined by [opening-rule-engine-v4.md](opening-rule-engine-v4.md), and the
authoring interaction is defined by
[rule-authoring-ui.md](rule-authoring-ui.md).

## Purpose

Development Mode is a local React and FastAPI workspace for exploring an
opening line, understanding the current Python-owned decision, inspecting legal
piece relationships, editing a version 4 Rulebook, and analyzing positions with
an optional local Stockfish process.

Quiz Mode remains memory-oriented and does not expose or mutate policy unless a
separate explicit authoring action is designed.

## Architecture

```text
React presentation
        |
        | HTTP / JSON
        v
FastAPI routes and session manager
        |
        v
FlowWorkspace / RulebookAuthor
        |
        v
Rulebook, tracker, relations, conditions, actions, scheduler, opening, engine
```

Python owns legality, SAN, original-piece identity, relationships, conditions,
action resolution, scheduling, frontiers, replay, persistence, opening
classification, opponent moves, and Stockfish. React owns layout, form state,
board interaction presentation, requests, and rendering returned snapshots.

Operations return a coherent workspace snapshot rather than requiring the
browser to merge domain state from unrelated responses.

## Workspace

The main surface contains the board and move history, piece-script inspector,
current decision/frontier, Back and Restart, optional engine analysis, and
opening context. Selecting a piece never disables move selection.

Controlled pieces expose default-development and interrupt authoring. Opponent
pieces are read-only. Relationship details distinguish each legal attacker and
the legal recaptures after that specific capture.

Rule statuses, diagnostics, attempt outcomes, frontier reasons, and decision
traces are values returned by Python.

## Operations

The API supports session creation, move submission, retry/continue,
`/accept-here`, Back, Restart, reload, analysis, development preview/apply/delete,
interrupt preview/apply/delete, and semantic order updates.

Every mutation follows:

```text
draft -> preview -> review -> apply -> revalidate
      -> atomic save -> replay -> complete snapshot
```

`/accept-here` persists a piece-owned exact-position interrupt and commits the
attempt only after successful validation, save, replay, and reassessment.

## Engine and opening context

Stockfish is optional in the local web mode. `engine-off` and configured-engine
failures are explicit; no fixture engine silently replaces a failed configured
engine. Blocking UCI work stays off the event loop and shared access is
serialized. Scores are White-normalized, with mate kept separate.

The bundled Lichess opening index is the only classification and book source.
It is offline and deterministic and does not provide popularity data. Opening
identity and opponent branch data remain separate from Rulebook policy.

## Persistence and navigation

The TOML Rulebook is durable and reviewable. Runtime completion, evaluations,
source labels, and relationship snapshots are transient. Back, Restart, reload,
and applied edits replay retained SAN to restore the board, original pieces,
completed instructions, completed interrupts, and opening history. Navigation
does not delete persisted rules or explored branches.

The server remains local by default. Accounts, cloud storage, remote sync,
databases, hosted deployment, and WebSockets are deferred.
