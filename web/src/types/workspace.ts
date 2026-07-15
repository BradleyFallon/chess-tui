export type ErrorCode =
  | "INVALID_MOVE" | "FLOW_VALIDATION_ERROR" | "FLOW_PERSISTENCE_ERROR"
  | "ENGINE_ERROR" | "SESSION_NOT_FOUND" | "INVALID_NAVIGATION" | "INVALID_REQUEST";

export interface ApiErrorItem { code: ErrorCode; message: string; details: Record<string, unknown>; }

export interface FlowSnapshot {
  name: string; version: number; path: string; side: "white" | "black";
  policyModel: "deterministic-v2";
}

export interface GameOverSnapshot { result: string; termination: string; winner: "white" | "black" | null; }
export interface PositionSnapshot {
  fen: string; historySan: string[]; turn: "white" | "black"; ply: number;
  lastMoveUci: string | null; legalMovesUci: string[]; gameOver: GameOverSnapshot | null;
}

export type ConditionExpression = Record<string, unknown>;
export interface ConditionSnapshot { expression: ConditionExpression; value: boolean; explanation: string; }

export interface RuleRuntimeSnapshot {
  kind: "rule"; id: string; priority: number; enabled: boolean; piece: string;
  destination: string; moveUci: string | null; moveSan: string | null; legal: boolean;
  lifecycle: "dormant" | "active" | "retired";
  status: "selected" | "active" | "waiting" | "dormant" | "retired" | "disabled";
  selected: boolean; shadowed: boolean; note: string | null;
  activateWhen: ConditionSnapshot | null; retireWhen: ConditionSnapshot | null;
  activatedAtPly: number | null; retiredAtPly: number | null; reason: string;
}

export interface OverrideRuntimeSnapshot {
  kind: "exact-override"; id: string; enabled: boolean; afterSan: string[];
  piece: string; destination: string; moveUci: string | null; moveSan: string | null;
  matched: boolean; legal: boolean; selected: boolean; note: string | null; reason: string;
}

export type PolicyItemSnapshot = RuleRuntimeSnapshot | OverrideRuntimeSnapshot;
export interface RuleGroupsSnapshot {
  selected: PolicyItemSnapshot | null;
  appliesNow: RuleRuntimeSnapshot[]; waiting: RuleRuntimeSnapshot[];
  dormant: RuleRuntimeSnapshot[]; retired: RuleRuntimeSnapshot[];
  disabled: RuleRuntimeSnapshot[]; overrides: OverrideRuntimeSnapshot[];
}

export interface DecisionSnapshot {
  status: "ready" | "frontier"; moveUci: string | null; moveSan: string | null;
  source: "rule" | "exact-override" | "frontier"; sourceId: string | null;
  priority: number | null; note: string | null; trace: string[];
}

export interface EngineReviewSnapshot {
  status: "ready" | "engine-off" | "error"; quality: string | null; lossCp: number | null;
  bestMoveUci: string | null; bestMoveSan: string | null;
  evaluationBeforeCp: number | null; evaluationAfterCp: number | null;
  mateBefore: number | null; mateAfter: number | null; errorMessage: string | null;
}

export interface AttemptSnapshot {
  result: "correct" | "mismatch" | "frontier"; playedUci: string; playedSan: string;
  expectedUci: string | null; expectedSan: string | null;
  source: "rule" | "exact-override" | "frontier"; sourceId: string | null;
  note: string | null; trace: string[]; engineReview: EngineReviewSnapshot | null;
}

export interface EvaluationSnapshot {
  status: "ready" | "analyzing" | "engine-off" | "error" | "game-over";
  perspective: "white"; centipawns: number | null; mateIn: number | null;
  previousCentipawns: number | null; previousMateIn: number | null;
  changeCentipawns: number | null; errorMessage: string | null;
}

export interface ActivitySnapshot { id: number; kind: "info" | "move" | "success" | "warning"; title: string; message: string; }
export interface WorkspaceSnapshot {
  sessionId: string; mode: "develop";
  phase: "policy-ready" | "policy-result" | "opponent-ready" | "game-over";
  flow: FlowSnapshot; position: PositionSnapshot; decision: DecisionSnapshot | null;
  attempt: AttemptSnapshot | null; rules: RuleGroupsSnapshot; evaluation: EvaluationSnapshot;
  navigation: { canBack: boolean; canRestart: boolean }; activity: ActivitySnapshot[]; errors: ApiErrorItem[];
}

export interface RuleUpdate {
  priority: number; enabled: boolean; note: string | null;
  move: { piece: string; to: string };
  activateWhen: ConditionExpression | null; retireWhen: ConditionExpression | null;
}

export interface OverrideUpdate {
  afterSan: string[]; enabled: boolean; note: string | null;
  move: { piece: string; to: string };
}
