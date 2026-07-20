import { useMemo, useState } from "react";

import { conditionToExpression, defaultCondition, expressionToCondition, type ConditionNode } from "../authoring/conditionAst";
import type {
  DevelopmentRuleDraft,
  DevelopmentRuleSnapshot,
  DevelopmentRuleValidation,
  ExactFixDraft,
  NamedConditionDraft,
  RuleDraft,
  RuleDraftValidation,
  RuleRuntimeSnapshot,
  StartingPieceSnapshot,
  StructureDraft,
  WorkspaceSnapshot,
} from "../types/workspace";
import { ConditionBuilder } from "./ConditionBuilder";
import { ConditionLibrary } from "./ConditionLibrary";
import { CurrentDecisionCard } from "./CurrentDecisionCard";
import { CurrentPlanCard } from "./CurrentPlanCard";
import { MoveRuleEditor } from "./MoveRuleEditor";
import { PolicyDetailsDrawer } from "./PolicyDetailsDrawer";
import { RuleReview } from "./RuleReview";
import { StructureManager } from "./StructureManager";
import { StructureScopePicker } from "./StructureScopePicker";

interface Props {
  workspace: WorkspaceSnapshot;
  piece: StartingPieceSnapshot | null;
  selectedAssignmentId: string | null;
  pending: boolean;
  pickedTarget: string | null;
  responsePrefill: RuleDraft | null;
  responseSuggestions: Array<{ label: string; expression: Record<string, unknown> }>;
  onConsumeResponsePrefill: () => void;
  onSelectAssignment: (id: string | null) => void;
  onBeginTargetPick: () => void;
  onCancelTargetPick: () => void;
  onValidateDevelopment: (draft: DevelopmentRuleDraft) => Promise<DevelopmentRuleValidation>;
  onApplyDevelopment: (draft: DevelopmentRuleDraft) => Promise<void>;
  onDeleteDevelopment: (ruleId: string) => Promise<void>;
  onReorderDevelopment: (ruleIds: string[]) => Promise<void>;
  onValidateRule: (draft: RuleDraft) => Promise<RuleDraftValidation>;
  onApplyRule: (draft: RuleDraft) => Promise<void>;
  onDeleteMoveRule: (section: "response" | "continuation", ruleId: string) => Promise<void>;
  onReorderSection: (section: "response" | "continuation", ids: string[]) => Promise<void>;
  onValidateExactFix: (draft: ExactFixDraft) => Promise<RuleDraftValidation>;
  onApplyExactFix: (draft: ExactFixDraft) => Promise<void>;
  onDeleteExactFix: (id: string) => Promise<void>;
  onValidateStructure: (draft: StructureDraft) => Promise<RuleDraftValidation>;
  onApplyStructure: (draft: StructureDraft) => Promise<void>;
  onDeleteStructure: (id: string) => Promise<void>;
  onReorderStructures: (ids: string[]) => Promise<void>;
  onValidateNamedCondition: (draft: NamedConditionDraft) => Promise<RuleDraftValidation>;
  onApplyNamedCondition: (draft: NamedConditionDraft) => Promise<void>;
  onDeleteNamedCondition: (id: string) => Promise<void>;
  onInspectPiece: (pieceRef: string) => void;
  onExplain: () => void;
}

type MoveRuleEditing = { section: "response" | "continuation"; id: string | null } | null;

export function PieceAuthoringPanel(props: Props) {
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [developmentEditing, setDevelopmentEditing] = useState(
    props.selectedAssignmentId !== null,
  );
  const [moveRuleEditing, setMoveRuleEditing] = useState<MoveRuleEditing>(
    props.responsePrefill ? { section: "response", id: null } : null,
  );

  const selectedAssignment = props.piece?.developmentRules.find(
    (item) => item.id === props.selectedAssignmentId,
  ) ?? null;
  const existingMoveRule = moveRuleEditing?.id
    ? [...props.workspace.rules.responses, ...props.workspace.rules.continuations].find((item) => item.id === moveRuleEditing.id) ?? null
    : null;

  return (
    <aside className="workspace-panel authoring-panel" aria-labelledby="piece-authoring-heading">
      <div className="authoring-scroll">
        <PieceOverview workspace={props.workspace} piece={props.piece} />
        <CurrentDecisionCard workspace={props.workspace} onExplain={props.onExplain} onOpenDetails={() => setDetailsOpen(true)} />
        <CurrentPlanCard workspace={props.workspace} />

        {props.piece && !props.piece.authorable ? (
          <OpponentPieceInspector piece={props.piece} />
        ) : props.piece ? (
          <section className="authoring-section" aria-labelledby="authoring-actions-heading">
            <span className="eyebrow" id="authoring-actions-heading">Authoring</span>
            {developmentEditing ? (
              <DevelopmentAssignmentEditor
                key={selectedAssignment?.id ?? "new-assignment"}
                workspace={props.workspace}
                piece={props.piece}
                existing={selectedAssignment}
                pickedTarget={props.pickedTarget}
                pending={props.pending}
                onBeginTargetPick={props.onBeginTargetPick}
                onCancelTargetPick={props.onCancelTargetPick}
                onValidate={props.onValidateDevelopment}
                onApply={props.onApplyDevelopment}
                onCancel={() => {
                  setDevelopmentEditing(false);
                  props.onSelectAssignment(null);
                }}
              />
            ) : (
              <DevelopmentAssignmentList
                piece={props.piece}
                pending={props.pending}
                onEdit={(id) => {
                  props.onSelectAssignment(id);
                  setDevelopmentEditing(true);
                }}
                onAdd={() => {
                  props.onSelectAssignment(null);
                  setDevelopmentEditing(true);
                }}
                onDelete={props.onDeleteDevelopment}
              />
            )}

            {moveRuleEditing ? (
              <MoveRuleEditor
                key={`${moveRuleEditing.section}:${moveRuleEditing.id ?? "new"}:${props.responsePrefill ? "prefill" : ""}`}
                workspace={props.workspace}
                piece={props.piece}
                section={moveRuleEditing.section}
                existing={existingMoveRule}
                initialDraft={moveRuleEditing.id === null ? props.responsePrefill : null}
                suggestions={moveRuleEditing.id === null ? props.responseSuggestions : []}
                pickedTarget={props.pickedTarget}
                pending={props.pending}
                onBeginTargetPick={props.onBeginTargetPick}
                onCancelTargetPick={props.onCancelTargetPick}
                onValidate={props.onValidateRule}
                onApply={props.onApplyRule}
                onCancel={() => {
                  setMoveRuleEditing(null);
                  props.onConsumeResponsePrefill();
                }}
              />
            ) : (
              <>
                <MoveRuleList
                  title="Special responses"
                  empty="No special responses for this piece."
                  rules={props.workspace.rules.responses.filter((item) => item.piece === props.piece?.ref)}
                  pending={props.pending}
                  onEdit={(id) => setMoveRuleEditing({ section: "response", id })}
                  onAdd={() => setMoveRuleEditing({ section: "response", id: null })}
                  onDelete={(id) => props.onDeleteMoveRule("response", id)}
                />
                <MoveRuleList
                  title="Later plans"
                  empty="No continuations for this piece."
                  rules={props.workspace.rules.continuations.filter((item) => item.piece === props.piece?.ref)}
                  pending={props.pending}
                  onEdit={(id) => setMoveRuleEditing({ section: "continuation", id })}
                  onAdd={() => setMoveRuleEditing({ section: "continuation", id: null })}
                  onDelete={(id) => props.onDeleteMoveRule("continuation", id)}
                />
              </>
            )}

            <ExactFixList
              workspace={props.workspace}
              piece={props.piece}
              pending={props.pending}
              onValidate={props.onValidateExactFix}
              onApply={props.onApplyExactFix}
              onDelete={props.onDeleteExactFix}
            />
          </section>
        ) : <p className="muted authoring-empty">Select an original piece to begin a concrete chess-authoring task.</p>}

        <PolicyOrderPanel
          workspace={props.workspace}
          pending={props.pending}
          onInspectPiece={props.onInspectPiece}
          onSelectAssignment={(pieceRef, assignmentId) => {
            props.onInspectPiece(pieceRef);
            props.onSelectAssignment(assignmentId);
            setDevelopmentEditing(true);
          }}
          onReorderDevelopment={props.onReorderDevelopment}
          onReorderSection={props.onReorderSection}
        />
        <StructureManager workspace={props.workspace} pending={props.pending} onValidate={props.onValidateStructure} onApply={props.onApplyStructure} onDelete={props.onDeleteStructure} onReorder={props.onReorderStructures} />
        <ConditionLibrary workspace={props.workspace} pending={props.pending} onValidate={props.onValidateNamedCondition} onApply={props.onApplyNamedCondition} onDelete={props.onDeleteNamedCondition} />
        <PieceHistoryPanel pieces={props.workspace.startingPieces} onInspectPiece={props.onInspectPiece} />
        <section className="policy-details-entry">
          <span className="eyebrow">Policy details</span>
          <p>Runtime state, exact conditions, trace, warnings, and TOML are available when you need them.</p>
          <button type="button" onClick={() => setDetailsOpen(true)}>View policy details</button>
        </section>
      </div>
      <PolicyDetailsDrawer workspace={props.workspace} open={detailsOpen} onClose={() => setDetailsOpen(false)} />
    </aside>
  );
}

function PieceOverview({ workspace, piece }: { workspace: WorkspaceSnapshot; piece: StartingPieceSnapshot | null }) {
  return (
    <section className="piece-overview">
      <span className="eyebrow" id="piece-authoring-heading">Piece authoring</span>
      {!piece ? <p>Click a piece to inspect its development and special behavior.</p> : <>
        <div className="piece-inspector-heading">
          <div><h2>{piece.label}</h2><code>{piece.ref}</code></div>
          <span className="friendly-status">{piece.authorable ? pieceStatus(piece) : "Opponent piece"}</span>
        </div>
        <dl className="piece-facts">
          <div><dt>Starting square</dt><dd>{piece.startingSquare}</dd></div>
          <div><dt>Current square</dt><dd>{piece.currentSquare ?? "Captured"}</dd></div>
          <div><dt>Role</dt><dd>{piece.authorable ? `${workspace.flow.side} policy piece` : "Opponent piece"}</dd></div>
          <div><dt>Piece status</dt><dd>{pieceStatus(piece)}</dd></div>
        </dl>
      </>}
    </section>
  );
}

function OpponentPieceInspector({ piece }: { piece: StartingPieceSnapshot }) {
  return (
    <section className="authoring-card opponent-piece-inspector">
      <span className="eyebrow">Condition reference</span>
      <strong>{piece.label}</strong>
      <p>This piece may be referenced in conditions.</p>
      <p>The controlled policy cannot move or develop it.</p>
    </section>
  );
}

function DevelopmentAssignmentList({
  piece,
  pending,
  onEdit,
  onAdd,
  onDelete,
}: {
  piece: StartingPieceSnapshot;
  pending: boolean;
  onEdit: (id: string) => void;
  onAdd: () => void;
  onDelete: (id: string) => Promise<void>;
}) {
  return (
    <section className="authoring-card development-summary">
      <span className="eyebrow">Development assignments</span>
      {piece.developmentRules.length === 0 ? <p>No development assignment.</p> : (
        <ol className="assignment-list">{piece.developmentRules.map((rule) => (
          <li key={rule.id}>
            <strong>{rule.scopeSummary}</strong>
            <span>Target {rule.target}</span>
            <span>Ready: {rule.readinessSummary}</span>
            <span className={`friendly-status status-${rule.friendlyStatus}`}>{friendlyLabel(rule.friendlyStatus)}</span>
            <p>{rule.reason}</p>
            <div className="button-row">
              <button type="button" onClick={() => onEdit(rule.id)} disabled={pending}>Edit assignment</button>
              <button className="danger-button" type="button" onClick={() => void onDelete(rule.id)} disabled={pending}>Remove assignment</button>
            </div>
          </li>
        ))}</ol>
      )}
      <button className="primary" type="button" onClick={onAdd} disabled={pending || piece.state !== "undeveloped"}>Add assignment</button>
    </section>
  );
}

function DevelopmentAssignmentEditor({
  workspace,
  piece,
  existing,
  pickedTarget,
  pending,
  onBeginTargetPick,
  onCancelTargetPick,
  onValidate,
  onApply,
  onCancel,
}: {
  workspace: WorkspaceSnapshot;
  piece: StartingPieceSnapshot;
  existing: DevelopmentRuleSnapshot | null;
  pickedTarget: string | null;
  pending: boolean;
  onBeginTargetPick: () => void;
  onCancelTargetPick: () => void;
  onValidate: (draft: DevelopmentRuleDraft) => Promise<DevelopmentRuleValidation>;
  onApply: (draft: DevelopmentRuleDraft) => Promise<void>;
  onCancel: () => void;
}) {
  const parsed = readinessFromExpression(existing?.readyWhen?.expression ?? null);
  const [target, setTarget] = useState(existing?.target ?? "");
  const [structures, setStructures] = useState(existing?.structures ?? []);
  const [note, setNote] = useState(existing?.note ?? "");
  const [mode, setMode] = useState<"immediate" | "prerequisites" | "advanced">(parsed.mode);
  const [prerequisites, setPrerequisites] = useState<string[]>(parsed.prerequisites.length ? parsed.prerequisites : [workspace.startingPieces.find((item) => item.authorable)?.ref ?? piece.ref]);
  const [advanced, setAdvanced] = useState<ConditionNode>(parsed.advanced ?? defaultCondition(piece.ref));
  const [validation, setValidation] = useState<DevelopmentRuleValidation | null>(null);
  const [errors, setErrors] = useState<string[]>([]);
  const draft: DevelopmentRuleDraft = {
    id: existing?.id ?? null,
    piece: piece.ref,
    target: pickedTarget ?? target,
    structures,
    note: note.trim() || null,
    readyWhen: readinessExpression(mode, prerequisites, advanced),
  };
  const close = () => {
    onCancelTargetPick();
    onCancel();
  };
  if (validation) {
    return <RuleReview title="Development assignment" validation={validation} applying={pending} onApply={() => void onApply(draft).then(close)} onBack={() => setValidation(null)} onCancel={close} />;
  }
  return (
    <form className="authoring-card guided-editor" onSubmit={(event) => {
      event.preventDefault();
      setErrors([]);
      void onValidate(draft).then((result) => result.valid ? setValidation(result) : setErrors(result.errors));
    }}>
      <span className="eyebrow">{existing ? "Edit assignment" : "Add assignment"}</span>
      <h3>{piece.label}</h3>
      <label>Target<div className="target-input-row"><input aria-label="Development target" value={pickedTarget ?? target} minLength={2} maxLength={2} onChange={(event) => { onCancelTargetPick(); setTarget(event.target.value); }} required /><button type="button" onClick={onBeginTargetPick}>Choose on board</button></div></label>
      <StructureScopePicker structures={workspace.rules.structures} selected={structures} onChange={setStructures} />
      <fieldset><legend>Ready</legend>
        <label><input type="radio" checked={mode === "immediate"} onChange={() => setMode("immediate")} /> Immediately</label>
        <label><input type="radio" checked={mode === "prerequisites"} onChange={() => setMode("prerequisites")} /> After other pieces develop</label>
        <label><input type="radio" checked={mode === "advanced"} onChange={() => setMode("advanced")} /> Advanced condition</label>
      </fieldset>
      {mode === "prerequisites" && <fieldset className="prerequisite-list"><legend>Ready after all</legend>{prerequisites.map((requiredPiece, index) => <div key={`${requiredPiece}-${index}`}><label htmlFor={`prerequisite-${index}`}>Required piece</label><select id={`prerequisite-${index}`} value={requiredPiece} onChange={(event) => setPrerequisites(prerequisites.map((item, itemIndex) => itemIndex === index ? event.target.value : item))}>{workspace.startingPieces.filter((item) => item.authorable).map((item) => <option key={item.ref} value={item.ref}>{item.label}</option>)}</select>{prerequisites.length > 1 && <button type="button" aria-label={`Remove prerequisite ${index + 1}`} onClick={() => setPrerequisites(prerequisites.filter((_, itemIndex) => itemIndex !== index))}>Remove</button>}</div>)}<button type="button" onClick={() => setPrerequisites([...prerequisites, workspace.startingPieces.find((item) => item.authorable)?.ref ?? piece.ref])}>Add prerequisite</button></fieldset>}
      {mode === "advanced" && <ConditionBuilder id="development-condition" label="Advanced readiness condition" value={advanced} pieces={workspace.startingPieces} namedConditions={workspace.namedConditions} onChange={setAdvanced} />}
      <label>Teaching note<textarea value={note} onChange={(event) => setNote(event.target.value)} /></label>
      {errors.length > 0 && <p className="inline-error" role="alert">{errors.join(" ")}</p>}
      <div className="button-row"><button className="primary" type="submit">Review changes</button><button type="button" onClick={close}>Cancel</button></div>
    </form>
  );
}

function MoveRuleList({ title, empty, rules, pending, onEdit, onAdd, onDelete }: {
  title: string; empty: string; rules: RuleRuntimeSnapshot[]; pending: boolean;
  onEdit: (id: string) => void; onAdd: () => void; onDelete: (id: string) => Promise<void>;
}) {
  return (
    <section className="authoring-card related-rules">
      <span className="eyebrow">{title}</span>
      {rules.length === 0 ? <p>{empty}</p> : <ol>{rules.map((rule) => <li key={rule.id}><strong>{rule.title}</strong><span>{rule.structureNames.length ? rule.structureNames.join(", ") : "Global"}</span><span>{rule.triggerSummary}</span><span>→ {rule.moveSan ?? `Move to ${rule.destination}`}</span><span className={`friendly-status status-${rule.friendlyStatus}`}>{friendlyLabel(rule.friendlyStatus)}</span><div className="button-row"><button type="button" onClick={() => onEdit(rule.id)}>Edit {rule.section}</button><button className="danger-button" type="button" disabled={pending} onClick={() => void onDelete(rule.id)}>Remove {rule.section}</button></div></li>)}</ol>}
      <button type="button" onClick={onAdd}>Add {title === "Special responses" ? "special response" : "continuation"}</button>
    </section>
  );
}

function ExactFixList({ workspace, piece, pending, onValidate, onApply, onDelete }: {
  workspace: WorkspaceSnapshot; piece: StartingPieceSnapshot; pending: boolean;
  onValidate: (draft: ExactFixDraft) => Promise<RuleDraftValidation>;
  onApply: (draft: ExactFixDraft) => Promise<void>;
  onDelete: (id: string) => Promise<void>;
}) {
  const [editing, setEditing] = useState<string | "new" | null>(null);
  const fix = editing && editing !== "new" ? piece.exactFixes.find((item) => item.id === editing) ?? null : null;
  const [target, setTarget] = useState("");
  const [note, setNote] = useState("");
  const [validation, setValidation] = useState<RuleDraftValidation | null>(null);
  const [errors, setErrors] = useState<string[]>([]);
  if (editing) {
    const draft: ExactFixDraft = {
      id: fix?.id ?? null,
      afterSan: fix?.afterSan ?? workspace.position.historySan,
      note: note.trim() || null,
      move: { piece: piece.ref, to: target },
    };
    if (validation) {
      return <RuleReview title="Exact fix" validation={validation} applying={pending} onApply={() => void onApply(draft).then(() => { setEditing(null); setValidation(null); })} onBack={() => setValidation(null)} onCancel={() => setEditing(null)} />;
    }
    return <form className="authoring-card guided-editor" onSubmit={(event) => {
      event.preventDefault();
      setErrors([]);
      void onValidate(draft).then((result) => result.valid ? setValidation(result) : setErrors(result.errors));
    }}>
      <span className="eyebrow">{fix ? "Edit exact fix" : "Add exact fix here"}</span>
      <label>Position<input value={numberHistory(draft.afterSan ?? [])} readOnly /></label>
      <label>Move {piece.label} to<input aria-label="Exact fix target" value={target} minLength={2} maxLength={2} onChange={(event) => setTarget(event.target.value)} required /></label>
      <label>Reason<textarea value={note} onChange={(event) => setNote(event.target.value)} /></label>
      {errors.length > 0 && <p className="inline-error" role="alert">{errors.join(" ")}</p>}
      <div className="button-row"><button className="primary" type="submit">Review changes</button><button type="button" onClick={() => setEditing(null)}>Cancel</button></div>
    </form>;
  }
  return (
    <section className="authoring-card exact-fixes">
      <span className="eyebrow">Exact fixes</span>
      {piece.exactFixes.length === 0 ? <p>No exact-position fixes involving this piece.</p> : piece.exactFixes.map((item) => <article key={item.id}><strong>{item.friendlyStatus === "exact-fix-active" ? "Exact fix active" : "Applies in another position"}</strong><dl><div><dt>After</dt><dd>{numberHistory(item.afterSan)}</dd></div><div><dt>Play</dt><dd>{item.moveSan ?? `${piece.label} → ${item.target}`}</dd></div><div><dt>Reason</dt><dd>{item.reason ?? "No reason recorded."}</dd></div></dl><div className="button-row"><button type="button" onClick={() => { setEditing(item.id); setTarget(item.target); setNote(item.reason ?? ""); }}>Edit exact fix</button><button className="danger-button" type="button" disabled={pending} onClick={() => void onDelete(item.id)}>Remove exact fix</button></div></article>)}
      <button type="button" onClick={() => { setEditing("new"); setTarget(""); setNote(""); }}>Create exact fix for this position</button>
    </section>
  );
}

function PolicyOrderPanel({ workspace, pending, onInspectPiece, onSelectAssignment, onReorderDevelopment, onReorderSection }: {
  workspace: WorkspaceSnapshot; pending: boolean;
  onInspectPiece: (piece: string) => void;
  onSelectAssignment: (piece: string, assignment: string) => void;
  onReorderDevelopment: (ids: string[]) => Promise<void>;
  onReorderSection: (section: "response" | "continuation", ids: string[]) => Promise<void>;
}) {
  const development = useMemo(() => workspace.startingPieces.flatMap((piece) => piece.developmentRules.map((rule) => ({ piece, rule }))).sort((a, b) => a.rule.order - b.rule.order), [workspace.startingPieces]);
  return <details className="policy-order-panel"><summary>Change authored order</summary>
    <SectionOrder title="Special responses" section="response" items={workspace.rules.responses} pending={pending} onInspectPiece={onInspectPiece} onReorder={onReorderSection} />
    <h3>Development assignments</h3><ol>{development.map((item, index) => <li key={item.rule.id}><button className="order-piece-button" onClick={() => onSelectAssignment(item.piece.ref, item.rule.id)}>{item.piece.label} → {item.rule.target} · {item.rule.scopeSummary}</button><span className="order-actions"><button aria-label={`Move ${item.piece.label} ${item.rule.target} earlier`} disabled={pending || index === 0} onClick={() => void onReorderDevelopment(reorder(development.map((entry) => ({ id: entry.rule.id })), index, -1))}>Earlier</button><button aria-label={`Move ${item.piece.label} ${item.rule.target} later`} disabled={pending || index === development.length - 1} onClick={() => void onReorderDevelopment(reorder(development.map((entry) => ({ id: entry.rule.id })), index, 1))}>Later</button></span></li>)}</ol>
    <SectionOrder title="Later plans" section="continuation" items={workspace.rules.continuations} pending={pending} onInspectPiece={onInspectPiece} onReorder={onReorderSection} />
  </details>;
}

function SectionOrder({ title, section, items, pending, onInspectPiece, onReorder }: {
  title: string;
  section: "response" | "continuation";
  items: RuleRuntimeSnapshot[];
  pending: boolean;
  onInspectPiece: (piece: string) => void;
  onReorder: (section: "response" | "continuation", ids: string[]) => Promise<void>;
}) {
  return <><h3>{title}</h3><ol>{items.map((item, index) => <li key={item.id}><button className="order-piece-button" onClick={() => onInspectPiece(item.piece)}>{item.title} · {item.structureNames.join(", ") || "Global"}</button><span className="order-actions"><button aria-label={`Move ${item.title} earlier`} disabled={pending || index === 0} onClick={() => void onReorder(section, reorder(items, index, -1))}>Earlier</button><button aria-label={`Move ${item.title} later`} disabled={pending || index === items.length - 1} onClick={() => void onReorder(section, reorder(items, index, 1))}>Later</button></span></li>)}</ol></>;
}

function reorder<T extends { id: string }>(items: T[], index: number, direction: -1 | 1) {
  const next = [...items];
  const destination = index + direction;
  if (destination < 0 || destination >= next.length) return items.map((item) => item.id);
  [next[index], next[destination]] = [next[destination], next[index]];
  return next.map((item) => item.id);
}

function PieceHistoryPanel({ pieces, onInspectPiece }: { pieces: StartingPieceSnapshot[]; onInspectPiece: (piece: string) => void }) {
  const history = pieces.filter((piece) => piece.state !== "undeveloped");
  return <details className="policy-order-panel piece-history-panel"><summary>Piece history</summary>{history.length === 0 ? <p>No original piece has moved or been captured on this line.</p> : <ul>{history.map((piece) => <li key={piece.ref}><button className="order-piece-button" type="button" onClick={() => onInspectPiece(piece.ref)}>{piece.label}</button><span>{pieceStatus(piece)}</span></li>)}</ul>}</details>;
}

function readinessFromExpression(expression: Record<string, unknown> | null): { mode: "immediate" | "prerequisites" | "advanced"; prerequisites: string[]; advanced: ConditionNode | null } {
  if (!expression) return { mode: "immediate", prerequisites: [], advanced: null };
  if (typeof expression.moved === "string") return { mode: "prerequisites", prerequisites: [expression.moved], advanced: null };
  if (Array.isArray(expression.all) && expression.all.every((item) => item && typeof item === "object" && typeof (item as Record<string, unknown>).moved === "string")) return { mode: "prerequisites", prerequisites: expression.all.map((item) => String((item as Record<string, unknown>).moved)), advanced: null };
  return { mode: "advanced", prerequisites: [], advanced: expressionToCondition(expression) };
}

function readinessExpression(mode: string, prerequisites: string[], advanced: ConditionNode) {
  if (mode === "immediate") return null;
  if (mode === "advanced") return conditionToExpression(advanced);
  if (prerequisites.length === 1) return { moved: prerequisites[0] };
  return { all: prerequisites.map((piece) => ({ moved: piece })) };
}

function friendlyLabel(status: string) {
  return ({ "not-ready": "Not ready", ready: "Ready", recommended: "Recommended now", blocked: "Blocked", completed: "Completed", "not-triggered": "Not triggered", available: "Available" } as Record<string, string>)[status] ?? status;
}

function pieceStatus(piece: StartingPieceSnapshot) {
  if (piece.state === "undeveloped") return "Not yet developed";
  if (piece.state === "developed") return `Developed on ply ${piece.firstMovedPly}`;
  if (piece.state === "captured-undeveloped") return `Captured before development on ply ${piece.capturedPly}`;
  return `Captured after development on ply ${piece.capturedPly}`;
}

function numberHistory(history: string[]) {
  if (!history.length) return "Starting position";
  const rows: string[] = [];
  for (let index = 0; index < history.length; index += 2) rows.push(`${index / 2 + 1}.${history[index]}${history[index + 1] ? ` ${history[index + 1]}` : ""}`);
  return rows.join(" ");
}
