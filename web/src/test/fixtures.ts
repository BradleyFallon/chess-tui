import type { CommandResponse, ClientEffect, RuleRuntimeSnapshot, WorkspaceSnapshot } from "../types/workspace";

export function ruleFixture(overrides: Partial<RuleRuntimeSnapshot> = {}): RuleRuntimeSnapshot {
  return {
    kind: "rule", section: "development", id: "develop-d-pawn", order: 1, structures: [],
    piece: "piece:white:pawn:d", destination: "d4", moveUci: "d2d4", moveSan: "d4",
    legal: true, lifecycle: "unlocked", status: "selected", selected: true,
    shadowed: false, note: "Control the center.", unlockWhen: null, when: null,
    expireWhen: null, unlockedAtPly: 0, retiredAtPly: null, reason: "First applicable assignment in development order.",
    title: "Control the center.", triggerSummary: "Available immediately",
    expirationSummary: "Completed when this piece develops", friendlyStatus: "recommended",
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
    flow: { name: "London System", version: 3, path: "flows/london.toml", side: "white", openingTags: [], warnings: [], policyModel: "deterministic-v3" },
    position: {
      fen: "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
      historySan: [], turn: "white", ply: 0, lastMoveUci: null,
      legalMovesUci: ["d2d4", "e2e4"], gameOver: null,
    },
    decision: {
      status: "ready", moveUci: "d2d4", moveSan: "d4", source: "development",
      sourceId: "develop-d-pawn", note: "Control the center.",
      trace: ["Development develop-d-pawn: selected."],
      summary: "d4 · Normal development", reason: "Control the center.",
    },
    attempt: null,
    rules: {
      selected, responses: [],
      development: [
        selected,
        ruleFixture({ id: "develop-dark-bishop", order: 2, piece: "piece:white:bishop:queenside", destination: "f4", moveUci: null, moveSan: null, legal: false, lifecycle: "unlocked", status: "inactive", selected: false, note: "Develop outside the chain.", unlockedAtPly: 0, reason: "White d-pawn has not moved" }),
      ],
      continuations: [], overrides: [], structures: [],
    },
    startingPieces: [
      {
        ref: "piece:white:pawn:d", originalPieceId: "white:d2", color: "white",
        pieceType: "pawn", qualifier: "d", label: "White d-pawn",
        startingSquare: "d2", currentSquare: "d2", state: "undeveloped",
        firstMovedPly: null, capturedPly: null,
        developmentRules: [{
          id: "develop-d-pawn", target: "d4", order: 1, structures: [],
          status: "selected", readyWhen: null, note: "Control the center.",
          reason: "First applicable assignment in development order.",
          readinessSummary: "Ready immediately", friendlyStatus: "recommended",
        }],
        relatedRules: [], exactFixes: [],
      },
      {
        ref: "piece:white:bishop:queenside", originalPieceId: "white:c1", color: "white",
        pieceType: "bishop", qualifier: "queenside", label: "White queenside bishop",
        startingSquare: "c1", currentSquare: "c1", state: "undeveloped",
        firstMovedPly: null, capturedPly: null,
        developmentRules: [{
          id: "develop-dark-bishop", target: "f4", order: 2, structures: [],
          status: "inactive", readyWhen: null, note: "Develop outside the chain.",
          reason: "White d-pawn has not moved.",
          readinessSummary: "White d-pawn has moved", friendlyStatus: "not-ready",
        }],
        relatedRules: [], exactFixes: [],
      },
    ],
    namedConditions: [],
    opening,
    openingHistory: [],
    evaluation: {
      status: "ready", perspective: "white", centipawns: 22, mateIn: null,
      previousCentipawns: null, previousMateIn: null, changeCentipawns: null, errorMessage: null,
      analysis: {
        engineName: "Stockfish 18", profileId: "analysis", requestedDepth: 20,
        actualDepth: 20, selectiveDepth: 28, nodes: 125000, nps: 1000000,
        timeMs: 125, lines: 1,
      },
    },
    analysisSettings: {
      status: "ready", engineName: "Stockfish 18", selectedProfileId: "analysis",
      profiles: [
        { id: "blunder-check", label: "Blunder check", depth: 10, costLabel: "Lowest compute", costDescription: "Depth 10 catches obvious tactical errors quickly." },
        { id: "quick", label: "Quick", depth: 15, costLabel: "Low compute", costDescription: "Depth 15 is a fast interactive evaluation." },
        { id: "analysis", label: "Analysis", depth: 20, costLabel: "Moderate compute", costDescription: "Depth 20 provides stronger routine analysis." },
        { id: "deep", label: "Deep", depth: 26, costLabel: "Highest compute", costDescription: "Depth 26 is the slowest, strongest interactive search." },
      ],
      candidateCount: 4, billingNote: "Local engine: no API or per-analysis fee.",
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
