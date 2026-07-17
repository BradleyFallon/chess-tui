import type { CommandResponse, ClientEffect, RuleRuntimeSnapshot, WorkspaceSnapshot } from "../types/workspace";

export function ruleFixture(overrides: Partial<RuleRuntimeSnapshot> = {}): RuleRuntimeSnapshot {
  return {
    kind: "rule", authoredKind: "development", id: "develop-d-pawn", priority: 400, enabled: true,
    piece: "piece:white:pawn:d", destination: "d4", moveUci: "d2d4", moveSan: "d4",
    legal: true, lifecycle: "active", status: "selected", selected: true,
    shadowed: false, note: "Control the center.", activateWhen: null,
    retireWhen: { expression: { moved: "piece:white:pawn:d" }, value: false, explanation: "White d-pawn has not moved" },
    activatedAtPly: 0, retiredAtPly: null, reason: "Highest-priority active legal rule.",
    ...overrides,
  };
}

export function workspaceFixture(overrides: Partial<WorkspaceSnapshot> = {}): WorkspaceSnapshot {
  const selected = ruleFixture();
  const opening = {
    primaryMatch: null, currentMatches: [], lastKnownMatch: null,
    entered: [], maintained: [], exited: [], playedMoveInBook: null,
    bookContinuations: [], reachableDefenses: [], moveSource: null,
    policyRuleId: null, exactOverrideId: null, recordedReplyId: null,
  };
  return {
    sessionId: "session-1", mode: "develop", phase: "policy-ready",
    flow: { name: "London System", version: 2, path: "flows/london.toml", side: "white", openingTags: [], policyModel: "deterministic-v2" },
    position: {
      fen: "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
      historySan: [], turn: "white", ply: 0, lastMoveUci: null,
      legalMovesUci: ["d2d4", "e2e4"], gameOver: null,
    },
    decision: {
      status: "ready", moveUci: "d2d4", moveSan: "d4", source: "rule",
      sourceId: "develop-d-pawn", priority: 400, note: "Control the center.",
      trace: ["Selected rule develop-d-pawn at priority 400."],
    },
    attempt: null,
    rules: {
      selected, appliesNow: [], waiting: [],
      dormant: [ruleFixture({ id: "develop-dark-bishop", priority: 390, piece: "piece:white:bishop:queenside", destination: "f4", moveUci: null, moveSan: null, legal: false, lifecycle: "dormant", status: "dormant", selected: false, note: "Develop outside the chain.", activatedAtPly: null, reason: "White d-pawn has not moved" })],
      retired: [], disabled: [], overrides: [],
    },
    startingPieces: [
      {
        ref: "piece:white:pawn:d", originalPieceId: "white:d2", color: "white",
        pieceType: "pawn", qualifier: "d", label: "White d-pawn",
        startingSquare: "d2", currentSquare: "d2", state: "undeveloped",
        firstMovedPly: null, capturedPly: null,
        developmentRule: {
          id: "develop-d-pawn", target: "d4", priority: 1000, order: 1,
          status: "selected", readyWhen: null, note: "Control the center.",
          enabled: true, reason: "Highest-priority active legal rule.",
        },
      },
      {
        ref: "piece:white:bishop:queenside", originalPieceId: "white:c1", color: "white",
        pieceType: "bishop", qualifier: "queenside", label: "White queenside bishop",
        startingSquare: "c1", currentSquare: "c1", state: "undeveloped",
        firstMovedPly: null, capturedPly: null,
        developmentRule: {
          id: "develop-dark-bishop", target: "f4", priority: 900, order: 2,
          status: "dormant", readyWhen: null, note: "Develop outside the chain.",
          enabled: true, reason: "White d-pawn has not moved.",
        },
      },
    ],
    opening,
    openingHistory: [],
    evaluation: {
      status: "ready", perspective: "white", centipawns: 22, mateIn: null,
      previousCentipawns: null, previousMateIn: null, changeCentipawns: null, errorMessage: null,
    },
    navigation: { canBack: false, canRestart: false },
    activity: [{ id: 1, sequence: 1, kind: "info", title: "Development session ready", message: "Loaded London System. White follows the deterministic policy.", attachment: null }],
    chat: [],
    availableCommands: [
      command("analyse_position", "/analyse", "/analyse", "Show opening-index moves and Stockfish's best candidates."),
      command("explain_decision", "/why", "/why", "Explain why the current policy decision was selected."),
      command("inspect_rule", "/rule", "/rule <rule-id>", "Inspect one policy rule or exact override.", [{ name: "rule_id", description: "Rule or override identifier.", required: true }]),
      command("list_rules", "/rules", "/rules", "List rules grouped by their current effective status."),
      command("trace_decision", "/trace", "/trace", "Show the deterministic trace for the current decision."),
      command("inspect_position", "/position", "/position", "Show the current position, history, and legal moves."),
      command("inspect_opening", "/opening", "/opening", "Explain the current or last known opening classification."),
      command("list_openings", "/openings", "/openings", "List all named opening matches for the current position."),
      command("list_defenses", "/defenses", "/defenses", "List entered defenses and book defenses still reachable."),
      command("inspect_book", "/book", "/book", "Show book alignment and continuations from the opening index."),
      command("inspect_book_history", "/book-history", "/book-history", "Summarize opening transitions along the current line."),
      command("play_move", "/play", "/play <SAN>", "Play a legal move using SAN notation.", [{ name: "move", description: "Move in SAN notation.", required: true }]),
      command("hint_policy_move", "/hint", "/hint", "Highlight the piece selected by the current policy."),
      command("list_commands", "/help", "/help", "Show the commands available in the current position."),
    ],
    errors: [], ...overrides,
  };
}

function command(
  id: WorkspaceSnapshot["availableCommands"][number]["id"],
  slash: string,
  usage: string,
  description: string,
  arguments_: WorkspaceSnapshot["availableCommands"][number]["arguments"] = [],
): WorkspaceSnapshot["availableCommands"][number] {
  return { id, slash, usage, description, arguments: arguments_ };
}

export function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

export function commandResponse(
  workspace: WorkspaceSnapshot,
  effects: ClientEffect[] = [],
): CommandResponse {
  return { workspace, effects };
}
