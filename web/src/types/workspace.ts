export type ErrorCode =
  | "INVALID_MOVE"
  | "FLOW_VALIDATION_ERROR"
  | "FLOW_PERSISTENCE_ERROR"
  | "ENGINE_ERROR"
  | "SESSION_NOT_FOUND"
  | "INVALID_NAVIGATION"
  | "INVALID_REQUEST";

export interface ApiErrorItem {
  code: ErrorCode;
  message: string;
  details: Record<string, unknown>;
}

export interface FlowSnapshot {
  name: string;
  version: number;
  path: string;
  policyModel: "legacy-v1";
}

export interface GameOverSnapshot {
  result: string;
  termination: string;
  winner: "white" | "black" | null;
}

export interface PositionSnapshot {
  fen: string;
  historySan: string[];
  turn: "white" | "black";
  ply: number;
  lastMoveUci: string | null;
  legalMovesUci: string[];
  gameOver: GameOverSnapshot | null;
}

export interface DecisionSnapshot {
  status: "ready" | "frontier" | "unavailable";
  moveUci: string | null;
  moveSan: string | null;
  source: "default" | "exception" | "frontier";
  sourceId: string | null;
  step: number;
  priority: number | null;
  note: string | null;
  unavailableReason: string | null;
}

export interface RuleSummary {
  source: "default" | "exception";
  sourceId: string | null;
  step: number;
  moveSan: string;
  note: string | null;
}

export interface ApplicableRuleSnapshot {
  id: string;
  kind: "default" | "exception" | "opponent-reply";
  status: "selected" | "fallback" | "applicable";
  step: number;
  moveSan: string;
  note: string | null;
  afterSan: string[];
  editable: boolean;
}

export interface RuleGroupsSnapshot {
  selected: RuleSummary | null;
  applicable: ApplicableRuleSnapshot[];
  active: RuleSummary[];
  dormant: RuleSummary[];
  retired: RuleSummary[];
  modelMessage: string;
}

export interface EngineReviewSnapshot {
  status: "ready" | "engine-off" | "error";
  quality: string | null;
  lossCp: number | null;
  bestMoveUci: string | null;
  bestMoveSan: string | null;
  evaluationBeforeCp: number | null;
  evaluationAfterCp: number | null;
  mateBefore: number | null;
  mateAfter: number | null;
  errorMessage: string | null;
}

export interface AttemptSnapshot {
  result:
    | "correct"
    | "mismatch-default"
    | "mismatch-exception"
    | "frontier"
    | "rule-unavailable";
  playedUci: string;
  playedSan: string;
  expectedUci: string | null;
  expectedSan: string | null;
  source: "default" | "exception" | "frontier";
  engineReview: EngineReviewSnapshot | null;
}

export interface EvaluationSnapshot {
  status: "ready" | "analyzing" | "engine-off" | "error" | "game-over";
  perspective: "white";
  centipawns: number | null;
  mateIn: number | null;
  previousCentipawns: number | null;
  previousMateIn: number | null;
  changeCentipawns: number | null;
  errorMessage: string | null;
}

export interface ActivitySnapshot {
  id: number;
  kind: "info" | "move" | "success" | "warning";
  title: string;
  message: string;
}

export interface WorkspaceSnapshot {
  sessionId: string;
  mode: "develop";
  phase: "white-ready" | "white-result" | "black-ready" | "game-over";
  flow: FlowSnapshot;
  position: PositionSnapshot;
  decision: DecisionSnapshot | null;
  attempt: AttemptSnapshot | null;
  rules: RuleGroupsSnapshot;
  evaluation: EvaluationSnapshot;
  navigation: {
    canBack: boolean;
    canRestart: boolean;
  };
  activity: ActivitySnapshot[];
  errors: ApiErrorItem[];
}
