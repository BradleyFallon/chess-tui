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

export interface BookMoveSnapshot {
  uci: string; san: string; source: "local-book" | "policy" | "opponent-branch";
  games: number | null; frequency: number | null;
}
export interface EngineMoveSnapshot {
  uci: string; san: string; evaluationCp: number | null; mateIn: number | null;
  principalVariation: string[];
}
export interface PositionAnalysisSnapshot {
  bookMoves: BookMoveSnapshot[]; engineMoves: EngineMoveSnapshot[];
}
export interface AvailableCommandSnapshot {
  id: CommandId; slash: string; usage: string; description: string;
  arguments: Array<{ name: string; description: string; required: boolean }>;
}
export interface PolicyReferenceSnapshot {
  kind: "rule" | "exact-override"; id: string; priority: number | null;
  moveSan: string | null; note: string | null; reason: string;
}
export type ChatAttachment =
  | { kind: "position-analysis"; analysis: PositionAnalysisSnapshot }
  | { kind: "decision-explanation"; selected: PolicyReferenceSnapshot | null; higherPriorityWaiting: PolicyReferenceSnapshot[]; shadowedActive: PolicyReferenceSnapshot[]; dormant: PolicyReferenceSnapshot[]; conditionReasons: string[]; provenance: string[] }
  | { kind: "rule-details"; rule: PolicyItemSnapshot; provenance: string[] }
  | { kind: "rule-list"; groups: RuleGroupsSnapshot }
  | { kind: "decision-trace"; entries: string[]; provenance: "policy-trace" }
  | { kind: "position-details"; fen: string; historySan: string[]; turn: "white" | "black"; ply: number; inCheck: boolean; lastMoveUci: string | null; legalMoves: Array<{ uci: string; san: string }>; gameOver: GameOverSnapshot | null }
  | { kind: "command-list"; commands: AvailableCommandSnapshot[] }
  | { kind: "validation-error"; code: string; details: Record<string, unknown> };
export interface ChatMessageSnapshot {
  id: string; sequence: number; role: "user" | "assistant" | "system" | "tool";
  text: string; attachment: ChatAttachment | null;
}
export interface ActivitySnapshot {
  id: number; sequence: number; kind: "info" | "move" | "success" | "warning";
  title: string; message: string;
}
export interface WorkspaceSnapshot {
  sessionId: string; mode: "develop";
  phase: "policy-ready" | "policy-result" | "opponent-ready" | "game-over";
  flow: FlowSnapshot; position: PositionSnapshot; decision: DecisionSnapshot | null;
  attempt: AttemptSnapshot | null; rules: RuleGroupsSnapshot; evaluation: EvaluationSnapshot;
  navigation: { canBack: boolean; canRestart: boolean }; activity: ActivitySnapshot[];
  chat: ChatMessageSnapshot[]; availableCommands: AvailableCommandSnapshot[];
  errors: ApiErrorItem[];
}

export type CommandId =
  | "analyse_position" | "explain_decision" | "inspect_rule" | "list_rules"
  | "trace_decision" | "inspect_position" | "play_move" | "next_opponent"
  | "retry_policy" | "continue_policy" | "add_rule_for_mismatch" | "go_back"
  | "restart" | "hint_policy_move" | "list_commands";
type SimpleCommandId = Exclude<CommandId, "play_move" | "inspect_rule">;
export type TypedCommand =
  | { command: SimpleCommandId; source: "ui" | "tool" }
  | { command: "play_move"; source: "ui" | "tool"; notation: "san" | "uci"; move: string }
  | { command: "inspect_rule"; source: "ui" | "tool"; ruleId: string };
export interface ClientEffect { kind: "highlight-move"; uci: string; }
export interface CommandResponse { workspace: WorkspaceSnapshot; effects: ClientEffect[]; }

export interface RuleUpdate {
  priority: number; enabled: boolean; note: string | null;
  move: { piece: string; to: string };
  activateWhen: ConditionExpression | null; retireWhen: ConditionExpression | null;
}

export interface OverrideUpdate {
  afterSan: string[]; enabled: boolean; note: string | null;
  move: { piece: string; to: string };
}
