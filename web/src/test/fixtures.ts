import type { WorkspaceSnapshot } from "../types/workspace";

export function workspaceFixture(
  overrides: Partial<WorkspaceSnapshot> = {},
): WorkspaceSnapshot {
  return {
    sessionId: "session-1",
    mode: "develop",
    phase: "white-ready",
    flow: {
      name: "London System",
      version: 1,
      path: "flows/london.toml",
      policyModel: "legacy-v1",
    },
    position: {
      fen: "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
      historySan: [],
      turn: "white",
      ply: 0,
      lastMoveUci: null,
      legalMovesUci: ["d2d4", "e2e4"],
      gameOver: null,
    },
    decision: {
      status: "ready",
      moveUci: "d2d4",
      moveSan: "d4",
      source: "default",
      sourceId: null,
      step: 1,
      priority: null,
      note: "Control the center.",
      unavailableReason: null,
    },
    attempt: null,
    rules: {
      selected: {
        source: "default",
        sourceId: null,
        step: 1,
        moveSan: "d4",
        note: "Control the center.",
      },
      applicable: [
        {
          id: "default-step-1",
          kind: "default",
          status: "selected",
          step: 1,
          moveSan: "d4",
          note: "Control the center.",
          afterSan: [],
          editable: true,
        },
      ],
      active: [],
      dormant: [],
      retired: [],
      modelMessage:
        "Legacy version 1 flows use numbered defaults and exact-position exceptions. Active, dormant, and retired lifecycle rules are not available yet.",
    },
    evaluation: {
      status: "ready",
      perspective: "white",
      centipawns: 22,
      mateIn: null,
      previousCentipawns: null,
      previousMateIn: null,
      changeCentipawns: null,
      errorMessage: null,
    },
    navigation: { canBack: false, canRestart: false },
    activity: [
      {
        id: 1,
        kind: "info",
        title: "Development session ready",
        message: "Loaded London System. White moves follow the saved flow rules.",
      },
    ],
    errors: [],
    ...overrides,
  };
}

export function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}
