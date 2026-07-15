import type { RuleRuntimeSnapshot, WorkspaceSnapshot } from "../types/workspace";

export function ruleFixture(overrides: Partial<RuleRuntimeSnapshot> = {}): RuleRuntimeSnapshot {
  return {
    kind: "rule", id: "develop-d-pawn", priority: 400, enabled: true,
    piece: "white:d2", destination: "d4", moveUci: "d2d4", moveSan: "d4",
    legal: true, lifecycle: "active", status: "selected", selected: true,
    shadowed: false, note: "Control the center.", activateWhen: null,
    retireWhen: { expression: { moved: "white:d2" }, value: false, explanation: "white:d2 has not moved" },
    activatedAtPly: 0, retiredAtPly: null, reason: "Highest-priority active legal rule.",
    ...overrides,
  };
}

export function workspaceFixture(overrides: Partial<WorkspaceSnapshot> = {}): WorkspaceSnapshot {
  const selected = ruleFixture();
  return {
    sessionId: "session-1", mode: "develop", phase: "policy-ready",
    flow: { name: "London System", version: 2, path: "flows/london.toml", side: "white", policyModel: "deterministic-v2" },
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
      dormant: [ruleFixture({ id: "develop-dark-bishop", priority: 390, piece: "white:c1", destination: "f4", moveUci: null, moveSan: null, legal: false, lifecycle: "dormant", status: "dormant", selected: false, note: "Develop outside the chain.", activatedAtPly: null, reason: "white:d2 has not moved" })],
      retired: [], disabled: [], overrides: [],
    },
    evaluation: {
      status: "ready", perspective: "white", centipawns: 22, mateIn: null,
      previousCentipawns: null, previousMateIn: null, changeCentipawns: null, errorMessage: null,
    },
    navigation: { canBack: false, canRestart: false },
    activity: [{ id: 1, kind: "info", title: "Development session ready", message: "Loaded London System. White follows the deterministic policy." }],
    errors: [], ...overrides,
  };
}

export function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}
