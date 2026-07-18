export type ErrorCode =
  | "INVALID_MOVE" | "FLOW_VALIDATION_ERROR" | "FLOW_PERSISTENCE_ERROR"
  | "ENGINE_ERROR" | "SESSION_NOT_FOUND" | "INVALID_NAVIGATION" | "INVALID_REQUEST";

export interface ApiErrorItem { code: ErrorCode; message: string; details: Record<string, unknown>; }

export interface OpeningTagSnapshot {
  recordId: number | null; eco: string; name: string;
}

export interface FlowSnapshot {
  name: string; version: number; path: string; side: "white" | "black";
  openingTags: OpeningTagSnapshot[];
  warnings: string[];
  policyModel: "deterministic-v3";
}

export interface GameOverSnapshot { result: string; termination: string; winner: "white" | "black" | null; }
export interface PositionSnapshot {
  fen: string; historySan: string[]; turn: "white" | "black"; ply: number;
  lastMoveUci: string | null; legalMovesUci: string[]; gameOver: GameOverSnapshot | null;
}

export type ConditionExpression = Record<string, unknown>;
export interface ConditionSnapshot { expression: ConditionExpression; value: boolean; explanation: string; }

export interface RuleRuntimeSnapshot {
  kind: "rule"; section: "response" | "development" | "continuation";
  id: string; order: number; structures: string[]; piece: string;
  destination: string; moveUci: string | null; moveSan: string | null; legal: boolean;
  lifecycle: "locked" | "unlocked" | "retired";
  status: "locked" | "inactive" | "waiting" | "applicable" | "selected" | "retired" | "out-of-scope";
  selected: boolean; shadowed: boolean; note: string | null;
  unlockWhen: ConditionSnapshot | null; when: ConditionSnapshot | null;
  expireWhen: ConditionSnapshot | null;
  unlockedAtPly: number | null; retiredAtPly: number | null; reason: string;
}

export type DevelopmentStatus =
  | "inactive" | "waiting" | "applicable" | "selected" | "developed"
  | "captured" | "out-of-scope";
export interface DevelopmentRuleSnapshot {
  id: string; target: string; order: number; structures: string[];
  status: DevelopmentStatus; readyWhen: ConditionSnapshot | null;
  note: string | null; reason: string;
}
export interface StartingPieceSnapshot {
  ref: string; originalPieceId: string; color: "white" | "black";
  pieceType: "pawn" | "rook" | "knight" | "bishop" | "queen" | "king";
  qualifier: string | null; label: string; startingSquare: string;
  currentSquare: string | null;
  state: "undeveloped" | "developed" | "captured-undeveloped" | "captured-developed";
  firstMovedPly: number | null; capturedPly: number | null;
  developmentRules: DevelopmentRuleSnapshot[];
}

export interface OverrideRuntimeSnapshot {
  kind: "exact-override"; id: string; afterSan: string[];
  piece: string; destination: string; moveUci: string | null; moveSan: string | null;
  matched: boolean; legal: boolean; selected: boolean; note: string | null; reason: string;
}

export type PolicyItemSnapshot = RuleRuntimeSnapshot | OverrideRuntimeSnapshot;
export interface StructureRuntimeSnapshot {
  id: string; name: string;
  status: "unavailable" | "available" | "selected" | "rejected";
  availableWhen: ConditionSnapshot; selectedWhen: ConditionSnapshot;
  selectedAtPly: number | null; note: string | null; reason: string;
}
export interface RuleGroupsSnapshot {
  selected: PolicyItemSnapshot | null;
  responses: RuleRuntimeSnapshot[]; development: RuleRuntimeSnapshot[];
  continuations: RuleRuntimeSnapshot[]; overrides: OverrideRuntimeSnapshot[];
  structures: StructureRuntimeSnapshot[];
}

export interface DecisionSnapshot {
  status: "ready" | "frontier"; moveUci: string | null; moveSan: string | null;
  source: "response" | "development" | "continuation" | "exact-override" | "frontier";
  sourceId: string | null; note: string | null; trace: string[];
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
  source: "response" | "development" | "continuation" | "exact-override" | "frontier";
  sourceId: string | null;
  note: string | null; trace: string[]; engineReview: EngineReviewSnapshot | null;
}

export interface EvaluationSnapshot {
  status: "ready" | "analyzing" | "engine-off" | "error" | "game-over";
  perspective: "white"; centipawns: number | null; mateIn: number | null;
  previousCentipawns: number | null; previousMateIn: number | null;
  changeCentipawns: number | null; errorMessage: string | null;
  analysis: AnalysisRunSnapshot | null;
}

export interface AnalysisRunSnapshot {
  engineName: string; profileId: string; requestedDepth: number | null;
  actualDepth: number | null; selectiveDepth: number | null;
  nodes: number | null; nps: number | null; timeMs: number | null; lines: number;
}
export interface AnalysisProfileSnapshot {
  id: string; label: string; depth: number; costLabel: string; costDescription: string;
}
export interface AnalysisSettingsSnapshot {
  status: "off" | "configured" | "ready" | "error"; engineName: string | null;
  selectedProfileId: string; profiles: AnalysisProfileSnapshot[];
  candidateCount: number; billingNote: string;
}

export interface OpeningMatchSnapshot {
  recordId: number; eco: string; name: string; family: string;
  variation: string | null; lineDepth: number;
}
export interface BookContinuationSnapshot {
  uci: string; san: string; openingNames: string[]; defenseNames: string[];
}
export type OpeningMoveSource =
  | "book-and-policy" | "policy-only" | "exact-override" | "recorded-branch"
  | "book" | "engine" | "manual" | "frontier";
export interface OpeningContextSnapshot {
  primaryMatch: OpeningMatchSnapshot | null;
  currentMatches: OpeningMatchSnapshot[];
  lastKnownMatch: OpeningMatchSnapshot | null;
  entered: OpeningMatchSnapshot[]; maintained: OpeningMatchSnapshot[];
  exited: OpeningMatchSnapshot[]; playedMoveInBook: boolean | null;
  bookContinuations: BookContinuationSnapshot[]; reachableDefenses: string[];
  moveSource: OpeningMoveSource | null; policyRuleId: string | null;
  exactOverrideId: string | null; recordedReplyId: string | null;
}
export interface OpeningHistoryItemSnapshot {
  ply: number; san: string; uci: string; positionKey: string;
  context: OpeningContextSnapshot;
}
export interface OpeningContextAttachment {
  kind: "opening-context"; entry: OpeningHistoryItemSnapshot | null;
  context: OpeningContextSnapshot; presentation: "compact" | "transition" | "current";
}

export interface BookMoveSnapshot {
  uci: string; san: string;
  source: "opening-index" | "book-and-policy" | "policy" | "opponent-branch";
  openingNames: string[]; defenseNames: string[];
}
export interface EngineMoveSnapshot {
  uci: string; san: string; evaluationCp: number | null; mateIn: number | null;
  principalVariation: string[];
}
export interface PositionAnalysisSnapshot {
  bookMoves: BookMoveSnapshot[]; engineMoves: EngineMoveSnapshot[];
  engine: AnalysisRunSnapshot | null;
}
export interface AvailableCommandSnapshot {
  id: CommandId; slash: string; usage: string; description: string;
  arguments: Array<{ name: string; description: string; required: boolean }>;
}
export interface PolicyReferenceSnapshot {
  kind: "rule" | "exact-override"; id: string;
  moveSan: string | null; note: string | null; reason: string;
}
export type ChatAttachment =
  | OpeningContextAttachment
  | { kind: "opening-list"; primaryMatch: OpeningMatchSnapshot | null; matches: OpeningMatchSnapshot[] }
  | { kind: "defense-list"; reachable: string[]; entered: string[] }
  | { kind: "book-details"; playedMoveInBook: boolean | null; continuations: BookContinuationSnapshot[] }
  | { kind: "book-history"; entries: OpeningHistoryItemSnapshot[]; firstPolicyWithoutBookPly: number | null }
  | { kind: "position-analysis"; analysis: PositionAnalysisSnapshot }
  | { kind: "decision-explanation"; selected: PolicyReferenceSnapshot | null; waiting: PolicyReferenceSnapshot[]; applicableLater: PolicyReferenceSnapshot[]; unavailable: PolicyReferenceSnapshot[]; conditionReasons: string[]; provenance: string[] }
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
  id: number; sequence: number;
  kind: "info" | "move" | "success" | "warning" | "commentary";
  title: string; message: string;
  attachment: OpeningContextAttachment | null;
}
export interface WorkspaceSnapshot {
  sessionId: string; mode: "develop";
  phase: "policy-ready" | "policy-result" | "opponent-ready" | "game-over";
  flow: FlowSnapshot; position: PositionSnapshot; decision: DecisionSnapshot | null;
  attempt: AttemptSnapshot | null; rules: RuleGroupsSnapshot;
  startingPieces: StartingPieceSnapshot[];
  opening: OpeningContextSnapshot; openingHistory: OpeningHistoryItemSnapshot[];
  evaluation: EvaluationSnapshot;
  analysisSettings: AnalysisSettingsSnapshot;
  navigation: { canBack: boolean; canRestart: boolean }; activity: ActivitySnapshot[];
  chat: ChatMessageSnapshot[]; availableCommands: AvailableCommandSnapshot[];
  errors: ApiErrorItem[];
}

export type CommandId =
  | "analyse_position" | "explain_decision" | "inspect_rule" | "list_rules"
  | "trace_decision" | "inspect_position" | "inspect_opening" | "list_openings"
  | "list_defenses" | "inspect_book" | "inspect_book_history"
  | "play_move" | "next_opponent"
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
  note: string | null; structures: string[];
  move: { piece: string; to: string };
  unlockWhen: ConditionExpression | null; when: ConditionExpression | null;
  expireWhen: ConditionExpression | null;
}

export interface OverrideUpdate {
  afterSan: string[]; note: string | null;
  move: { piece: string; to: string };
}

export interface StructureUpdate {
  name: string; note: string | null;
  availableWhen: ConditionExpression;
  selectedWhen: ConditionExpression;
}

export interface DevelopmentRuleDraft {
  id: string | null; piece: string; target: string; structures: string[];
  note: string | null; readyWhen: ConditionExpression | null;
}
export interface DevelopmentRuleValidation {
  valid: boolean; ruleId: string; piece: string; target: string;
  order: number; errors: string[];
}
