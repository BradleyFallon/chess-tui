export type PieceType = "pawn" | "knight" | "bishop" | "rook" | "queen" | "king";

export type ConditionExpression =
  | { moved: string }
  | { unmoved: string }
  | { captured: string }
  | { at: { piece: string; square: string } }
  | { occupied: string }
  | { empty: string }
  | { occupied_by: { square: string; color: "white" | "black"; type: PieceType } }
  | { in_check: "white" | "black" }
  | { last_move: { piece: string; to: string } }
  | { attacked: string }
  | { attacked_by: { target: string; piece: string } }
  | { attacked_by: { target: string; type: PieceType } }
  | { undefended: string }
  | { under_defended: string }
  | { attack_balance: { target: string; at_least: number } }
  | { capturable: string }
  | { all: ConditionExpression[] }
  | { any: ConditionExpression[] }
  | { not: ConditionExpression };

export interface ApiErrorItem {
  code: "INVALID_MOVE" | "FLOW_VALIDATION_ERROR" | "FLOW_PERSISTENCE_ERROR" | "ENGINE_ERROR" | "SESSION_NOT_FOUND" | "INVALID_NAVIGATION" | "INVALID_REQUEST";
  message: string;
  details: Record<string, unknown>;
}

export interface ActionAttemptDraft {
  move?: string;
  capture?: string;
  captureType?: PieceType;
}

export interface DevelopmentDraft {
  alias: string;
  to: string;
  requires: string[];
  when: ConditionExpression | null;
  why: string;
}

export interface InterruptDraft {
  alias: string;
  id: string | null;
  requires: string[];
  afterSan: string[] | null;
  when: ConditionExpression | null;
  required: boolean;
  attempts: ActionAttemptDraft[];
  why: string;
}

export interface MutationPreview {
  valid: boolean;
  errors: string[];
  warnings: string[];
  currentDecision: string | null;
  previewDecision: string | null;
  generatedToml: string | null;
}

export interface ConditionEvaluation {
  value: boolean;
  explanation: string;
  details: Record<string, unknown>;
}

export interface ActionAttempt {
  kind: "move" | "capture-attacker" | "capture-piece" | "capture-type";
  value: string;
  status: "not-evaluated" | "failed" | "resolved" | "ambiguous";
  candidates: string[];
  reason: string | null;
}

export interface DevelopmentInstruction {
  reference: string;
  to: string;
  requires: string[];
  when: ConditionExpression | null;
  why: string;
  status: "not-ready" | "waiting-for-legality" | "available" | "selected" | "completed" | "captured";
  explanation: string;
  condition: ConditionEvaluation | null;
}

export interface InterruptRule {
  reference: string;
  id: string;
  requires: string[];
  afterSan: string[] | null;
  when: ConditionExpression | null;
  required: boolean;
  attempts: ActionAttempt[];
  why: string;
  status: "trigger-false" | "no-action" | "applicable" | "selected" | "completed" | "ambiguous" | "required-unhandled";
  explanation: string;
  trigger: ConditionEvaluation | null;
}

export interface Attack {
  piece: string;
  alias: string | null;
  moveUci: string;
}

export interface Defense {
  piece: string;
  alias: string | null;
  moveUci: string;
}

export interface PieceRelationships {
  attacks: Attack[];
  attackers: Attack[];
  defendersByAttacker: Array<{
    attacker: string;
    attackerAlias: string | null;
    defenders: Defense[];
  }>;
  distinctDefenders: string[];
  attackerCount: number;
  defenderCount: number;
  attackBalance: number;
  attacked: boolean;
  undefended: boolean;
  underDefended: boolean;
  kingPinned: boolean;
  pinnedBy: string | null;
}

export interface PieceScript {
  alias: string;
  ref: string;
  label: string;
  currentSquare: string | null;
  mechanicalState: "undeveloped" | "developed" | "captured-undeveloped" | "captured-developed";
  authorable: boolean;
  development: DevelopmentInstruction | null;
  interrupts: InterruptRule[];
  relationships: PieceRelationships;
}

export interface WorkspaceSnapshot {
  sessionId: string;
  mode: "develop";
  rulebook: {
    name: string;
    version: number;
    path: string;
    side: "white" | "black";
    openingTags: Array<{ eco: string; name: string }>;
    warnings: string[];
  };
  position: {
    fen: string;
    historySan: string[];
    turn: "white" | "black";
    legalMovesUci: string[];
    lastMoveUci: string | null;
    gameOver: string | null;
  };
  decision: {
    status: "ready" | "frontier";
    source: "interrupt" | "development" | "frontier";
    moveUci: string | null;
    moveSan: string | null;
    instructionRef: string | null;
    why: string | null;
    frontier: {
      reason: "development-complete" | "no-authored-legal-move" | "unhandled-required-rule" | "ambiguous-action";
      explanation: string;
    } | null;
    trace: string[];
  } | null;
  pieceScripts: PieceScript[];
  developmentOrder: string[];
  interruptOrder: string[];
  attempt: {
    result: "correct" | "mismatch" | "frontier";
    moveUci: string;
    moveSan: string;
    expectedUci: string | null;
    expectedSan: string | null;
  } | null;
  navigation: { canBack: boolean; canRestart: boolean };
  evaluation: {
    status: "off" | "ready" | "error";
    centipawns: number | null;
    mateIn: number | null;
    message: string | null;
  };
  errors: string[];
}
