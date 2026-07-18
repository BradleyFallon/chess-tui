import { type FormEvent, useMemo, useState } from "react";

import {
  conditionToExpression,
  defaultCondition,
  expressionToCondition,
  type ConditionNode,
} from "../authoring/conditionAst";
import type {
  DevelopmentRuleDraft,
  DevelopmentRuleValidation,
  OverrideUpdate,
  RuleDraft,
  RuleDraftValidation,
  StartingPieceSnapshot,
  WorkspaceSnapshot,
} from "../types/workspace";
import { ConditionBuilder } from "./ConditionBuilder";
import { CurrentDecisionCard } from "./CurrentDecisionCard";
import { PolicyDetailsDrawer } from "./PolicyDetailsDrawer";
import { RuleReview } from "./RuleReview";

interface Props {
  workspace: WorkspaceSnapshot;
  piece: StartingPieceSnapshot | null;
  pending: boolean;
  pickedTarget: string | null;
  responsePrefill: RuleDraft | null;
  onConsumeResponsePrefill: () => void;
  onBeginTargetPick: () => void;
  onCancelTargetPick: () => void;
  onValidateDevelopment: (draft: DevelopmentRuleDraft) => Promise<DevelopmentRuleValidation>;
  onApplyDevelopment: (draft: DevelopmentRuleDraft) => Promise<void>;
  onDeleteDevelopment: (ruleId: string) => Promise<void>;
  onReorderDevelopment: (ruleIds: string[]) => Promise<void>;
  onValidateRule: (draft: RuleDraft) => Promise<RuleDraftValidation>;
  onApplyRule: (draft: RuleDraft) => Promise<void>;
  onDeleteRule: (ruleId: string) => Promise<void>;
  onReorderResponses: (ruleIds: string[]) => Promise<void>;
  onValidateOverride: (id: string, update: OverrideUpdate) => Promise<RuleDraftValidation>;
  onUpdateOverride: (id: string, update: OverrideUpdate) => Promise<void>;
  onInspectPiece: (pieceRef: string) => void;
  onExplain: () => void;
}

export function PieceAuthoringPanel(props: Props) {
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [developmentEditing, setDevelopmentEditing] = useState(false);
  const [responseDraft, setResponseDraft] = useState<RuleDraft | null>(
    props.responsePrefill,
  );

  return (
    <aside className="workspace-panel authoring-panel" aria-labelledby="piece-authoring-heading">
      <div className="authoring-scroll">
        <section className="piece-overview">
          <span className="eyebrow" id="piece-authoring-heading">Piece authoring</span>
          {!props.piece ? (
            <p>Click a piece to inspect its development and special behavior.</p>
          ) : (
            <>
              <div className="piece-inspector-heading">
                <div><h2>{props.piece.label}</h2><code>{props.piece.ref}</code></div>
                <span className="friendly-status">{pieceStatus(props.piece)}</span>
              </div>
              <dl className="piece-facts">
                <div><dt>Starting square</dt><dd>{props.piece.startingSquare}</dd></div>
                <div><dt>Current square</dt><dd>{props.piece.currentSquare ?? "Captured"}</dd></div>
                <div><dt>Piece status</dt><dd>{pieceStatus(props.piece)}</dd></div>
              </dl>
            </>
          )}
        </section>
        <CurrentDecisionCard
          workspace={props.workspace}
          onExplain={props.onExplain}
          onOpenDetails={() => setDetailsOpen(true)}
        />
        <section className="authoring-section" aria-labelledby="authoring-actions-heading">
          <span className="eyebrow" id="authoring-actions-heading">Authoring</span>
          {props.piece ? (
            <>
              {developmentEditing ? (
                <DevelopmentEditor
                  workspace={props.workspace}
                  piece={props.piece}
                  pickedTarget={props.pickedTarget}
                  pending={props.pending}
                  onBeginTargetPick={props.onBeginTargetPick}
                  onCancelTargetPick={props.onCancelTargetPick}
                  onValidate={props.onValidateDevelopment}
                  onApply={props.onApplyDevelopment}
                  onCancel={() => setDevelopmentEditing(false)}
                />
              ) : (
                <DevelopmentSummary
                  piece={props.piece}
                  pending={props.pending}
                  onEdit={() => setDevelopmentEditing(true)}
                  onDelete={props.onDeleteDevelopment}
                />
              )}
              {responseDraft ? (
                <ResponseWizard
                  workspace={props.workspace}
                  initial={responseDraft}
                  pending={props.pending}
                  pickedTarget={props.pickedTarget}
                  onBeginTargetPick={props.onBeginTargetPick}
                  onCancelTargetPick={props.onCancelTargetPick}
                  onValidate={props.onValidateRule}
                  onApply={props.onApplyRule}
                  onCancel={() => {
                    setResponseDraft(null);
                    props.onConsumeResponsePrefill();
                  }}
                />
              ) : (
                <RelatedRuleList
                  piece={props.piece}
                  pending={props.pending}
                  onAdd={() => setResponseDraft({
                    id: null,
                    piece: props.piece!.ref,
                    target: props.piece!.currentSquare ?? props.piece!.startingSquare,
                    note: null,
                    trigger: { attacked: props.piece!.ref },
                    expireWhen: null,
                  })}
                  onEdit={(ruleId) => {
                    const rule = props.workspace.rules.responses.find((item) => item.id === ruleId);
                    if (!rule) return;
                    setResponseDraft({
                      id: rule.id,
                      piece: rule.piece,
                      target: rule.destination,
                      note: rule.note,
                      trigger: rule.when?.expression ?? null,
                      expireWhen: rule.expireWhen?.expression ?? null,
                    });
                  }}
                  onDelete={props.onDeleteRule}
                />
              )}
              <ExactFixes
                piece={props.piece}
                workspace={props.workspace}
                pending={props.pending}
                onValidate={props.onValidateOverride}
                onApply={props.onUpdateOverride}
              />
            </>
          ) : (
            <p className="muted">Select an original piece to begin a concrete chess-authoring task.</p>
          )}
          <PolicyOrderPanel
            workspace={props.workspace}
            pending={props.pending}
            onInspectPiece={props.onInspectPiece}
            onReorderDevelopment={props.onReorderDevelopment}
            onReorderResponses={props.onReorderResponses}
          />
          <PieceHistoryPanel
            pieces={props.workspace.startingPieces}
            onInspectPiece={props.onInspectPiece}
          />
        </section>
        <section className="policy-details-entry">
          <span className="eyebrow">Policy details</span>
          <p>Runtime state, exact conditions, trace, and TOML are available when you need them.</p>
          <button type="button" onClick={() => setDetailsOpen(true)}>View policy details</button>
        </section>
      </div>
      <PolicyDetailsDrawer workspace={props.workspace} open={detailsOpen} onClose={() => setDetailsOpen(false)} />
    </aside>
  );
}

function DevelopmentSummary({ piece, pending, onEdit, onDelete }: { piece: StartingPieceSnapshot; pending: boolean; onEdit: () => void; onDelete: (id: string) => Promise<void> }) {
  const rule = piece.developmentRules[0] ?? null;
  return (
    <section className="authoring-card development-summary">
      <span className="eyebrow">Normal development</span>
      {rule ? (
        <>
          <strong>Move {piece.label} to {rule.target}</strong>
          <p>Ready: {rule.readinessSummary}</p>
          <span className={`friendly-status status-${rule.friendlyStatus}`}>{friendlyLabel(rule.friendlyStatus)}</span>
          {piece.state === "developed" && <p>Completed on ply {piece.firstMovedPly} · authored target: {rule.target}</p>}
          {piece.state === "captured-undeveloped" && <p>Captured before development on ply {piece.capturedPly}</p>}
          <div className="button-row">
            <button type="button" onClick={onEdit} disabled={pending}>Edit development</button>
            <button className="danger-button" type="button" onClick={() => void onDelete(rule.id)} disabled={pending}>Remove development</button>
          </div>
        </>
      ) : (
        <>
          <p>No development assignment.</p>
          <button className="primary" type="button" onClick={onEdit} disabled={pending || piece.state !== "undeveloped"}>Set normal development</button>
        </>
      )}
    </section>
  );
}

function DevelopmentEditor({ workspace, piece, pickedTarget, pending, onBeginTargetPick, onCancelTargetPick, onValidate, onApply, onCancel }: {
  workspace: WorkspaceSnapshot; piece: StartingPieceSnapshot; pickedTarget: string | null; pending: boolean;
  onBeginTargetPick: () => void; onCancelTargetPick: () => void;
  onValidate: (draft: DevelopmentRuleDraft) => Promise<DevelopmentRuleValidation>;
  onApply: (draft: DevelopmentRuleDraft) => Promise<void>; onCancel: () => void;
}) {
  const existing = piece.developmentRules[0] ?? null;
  const parsed = readinessFromExpression(existing?.readyWhen?.expression ?? null);
  const [target, setTarget] = useState(existing?.target ?? "");
  const [note, setNote] = useState(existing?.note ?? "");
  const [mode, setMode] = useState<"immediate" | "prerequisites" | "advanced">(parsed.mode);
  const [prerequisites, setPrerequisites] = useState<string[]>(parsed.prerequisites.length ? parsed.prerequisites : [workspace.startingPieces[0]?.ref ?? piece.ref]);
  const [advanced, setAdvanced] = useState<ConditionNode>(parsed.advanced ?? defaultCondition(piece.ref));
  const [validation, setValidation] = useState<DevelopmentRuleValidation | null>(null);
  const [errors, setErrors] = useState<string[]>([]);
  const effectiveTarget = pickedTarget ?? target;
  const draft: DevelopmentRuleDraft = {
    id: existing?.id ?? null,
    piece: piece.ref,
    target: effectiveTarget,
    structures: existing?.structures ?? [],
    note: note.trim() || null,
    readyWhen: readinessExpression(mode, prerequisites, advanced),
  };
  const cancel = () => {
    onCancelTargetPick();
    onCancel();
  };
  if (validation) {
    return <RuleReview title="Normal development" validation={validation} applying={pending} onApply={() => { void onApply(draft).then(cancel); }} onBack={() => setValidation(null)} onCancel={cancel} />;
  }
  return (
    <form className="authoring-card guided-editor" onSubmit={(event) => {
      event.preventDefault();
      setErrors([]);
      void onValidate(draft).then((result) => {
        if (result.valid) setValidation(result);
        else setErrors(result.errors);
      }).catch((error: unknown) => setErrors([error instanceof Error ? error.message : "Validation failed."]));
    }}>
      <span className="eyebrow">Edit development</span>
      <h3>{piece.label}</h3>
      <label>Target<div className="target-input-row"><input aria-label="Development target" value={effectiveTarget} minLength={2} maxLength={2} onChange={(event) => { onCancelTargetPick(); setTarget(event.target.value); }} required /><button type="button" onClick={onBeginTargetPick}>Choose on board</button></div></label>
      <fieldset><legend>Ready</legend>
        <label><input type="radio" checked={mode === "immediate"} onChange={() => setMode("immediate")} /> Immediately</label>
        <label><input type="radio" checked={mode === "prerequisites"} onChange={() => setMode("prerequisites")} /> After another piece develops</label>
        <label><input type="radio" checked={mode === "advanced"} onChange={() => setMode("advanced")} /> Advanced condition</label>
      </fieldset>
      {mode === "prerequisites" && <fieldset className="prerequisite-list"><legend>Ready after all</legend>{prerequisites.map((requiredPiece, index) => <div key={`${requiredPiece}-${index}`}><label htmlFor={`prerequisite-${index}`}>Required piece</label><select id={`prerequisite-${index}`} value={requiredPiece} onChange={(event) => setPrerequisites(prerequisites.map((item, itemIndex) => itemIndex === index ? event.target.value : item))}>{workspace.startingPieces.map((item) => <option key={item.ref} value={item.ref}>{item.label}</option>)}</select>{prerequisites.length > 1 && <button type="button" aria-label={`Remove prerequisite ${index + 1}`} onClick={() => setPrerequisites(prerequisites.filter((_, itemIndex) => itemIndex !== index))}>Remove</button>}</div>)}<button type="button" onClick={() => setPrerequisites([...prerequisites, workspace.startingPieces[0]?.ref ?? piece.ref])}>Add prerequisite</button></fieldset>}
      {mode === "advanced" && <ConditionBuilder id="development-condition" label="Advanced readiness condition" value={advanced} pieces={workspace.startingPieces} namedConditions={workspace.namedConditions} onChange={setAdvanced} />}
      <label>Reason<textarea value={note} rows={2} onChange={(event) => setNote(event.target.value)} /></label>
      {errors.length > 0 && <div className="inline-error" role="alert">{errors.join(" ")}</div>}
      <div className="button-row"><button className="primary" type="submit" disabled={pending}>Review changes</button><button type="button" onClick={cancel}>Cancel</button></div>
    </form>
  );
}

function RelatedRuleList({ piece, pending, onAdd, onEdit, onDelete }: { piece: StartingPieceSnapshot; pending: boolean; onAdd: () => void; onEdit: (id: string) => void; onDelete: (id: string) => Promise<void> }) {
  const responses = piece.relatedRules.filter((rule) => rule.role === "response");
  return (
    <section className="authoring-card related-rules">
      <span className="eyebrow">Special responses</span>
      {responses.length === 0 ? <p>No special responses for this piece.</p> : <ol>{responses.map((rule) => <li key={rule.id}><strong>{rule.triggerSummary}</strong><span>→ {rule.moveSan ?? `Move to ${rule.target}`}</span><span className={`friendly-status status-${rule.friendlyStatus}`}>{friendlyLabel(rule.friendlyStatus)}</span><div className="button-row"><button type="button" onClick={() => onEdit(rule.id)} disabled={pending}>Edit response</button><button className="danger-button" type="button" onClick={() => void onDelete(rule.id)} disabled={pending}>Remove response</button></div></li>)}</ol>}
      <button type="button" onClick={onAdd} disabled={pending}>Add special response</button>
    </section>
  );
}

function ResponseWizard({ workspace, initial, pending, pickedTarget, onBeginTargetPick, onCancelTargetPick, onValidate, onApply, onCancel }: {
  workspace: WorkspaceSnapshot; initial: RuleDraft; pending: boolean; pickedTarget: string | null;
  onBeginTargetPick: () => void; onCancelTargetPick: () => void;
  onValidate: (draft: RuleDraft) => Promise<RuleDraftValidation>; onApply: (draft: RuleDraft) => Promise<void>; onCancel: () => void;
}) {
  const piece = workspace.startingPieces.find((item) => item.ref === initial.piece) ?? workspace.startingPieces[0];
  const [step, setStep] = useState(1);
  const [target, setTarget] = useState(initial.target);
  const [note, setNote] = useState(initial.note ?? "");
  const initialTrigger = initial.trigger ? safeCondition(initial.trigger, piece.ref) : { kind: "attacked", piece: piece.ref } as ConditionNode;
  const [triggerMode, setTriggerMode] = useState<"attacked" | "piece-at" | "moved" | "advanced">(triggerModeFor(initialTrigger));
  const [triggerPiece, setTriggerPiece] = useState(triggerPieceFor(initialTrigger, piece.ref));
  const [triggerSquare, setTriggerSquare] = useState(triggerSquareFor(initialTrigger));
  const [advancedTrigger, setAdvancedTrigger] = useState(initialTrigger);
  const [expirationMode, setExpirationMode] = useState<"used" | "piece-moves" | "advanced">(initial.expireWhen ? "advanced" : "used");
  const [advancedExpiration, setAdvancedExpiration] = useState<ConditionNode>(initial.expireWhen ? safeCondition(initial.expireWhen, piece.ref) : defaultCondition(piece.ref));
  const [validation, setValidation] = useState<RuleDraftValidation | null>(null);
  const [errors, setErrors] = useState<string[]>([]);
  const effectiveTarget = pickedTarget ?? target;
  const trigger = triggerExpression(triggerMode, piece.ref, triggerPiece, triggerSquare, advancedTrigger);
  const expireWhen = expirationMode === "used" ? null : expirationMode === "piece-moves" ? { moved: piece.ref } : conditionToExpression(advancedExpiration);
  const draft: RuleDraft = { ...initial, target: effectiveTarget, note: note.trim() || null, trigger, expireWhen };
  const cancel = () => {
    onCancelTargetPick();
    onCancel();
  };
  if (validation) return <RuleReview title="Special response" validation={validation} applying={pending} onApply={() => { void onApply(draft).then(cancel); }} onBack={() => setValidation(null)} onCancel={cancel} />;
  return (
    <form className="authoring-card guided-editor response-wizard" onSubmit={(event: FormEvent) => {
      event.preventDefault();
      if (step < 3) { setStep(step + 1); return; }
      setErrors([]);
      void onValidate(draft).then((result) => result.valid ? setValidation(result) : setErrors(result.errors)).catch((error: unknown) => setErrors([error instanceof Error ? error.message : "Validation failed."]));
    }}>
      <span className="eyebrow">{initial.id ? "Edit special response" : "Add special response"} · Step {step} of 3</span>
      {step === 1 && <><h3>What should happen?</h3><p>Move {piece.label}</p><label>To<div className="target-input-row"><input aria-label="Response target" value={effectiveTarget} minLength={2} maxLength={2} onChange={(event) => { onCancelTargetPick(); setTarget(event.target.value); }} required /><button type="button" onClick={onBeginTargetPick}>Choose on board</button></div></label></>}
      {step === 2 && <><h3>When should this happen?</h3><fieldset><legend>Trigger</legend><label><input type="radio" checked={triggerMode === "attacked"} onChange={() => setTriggerMode("attacked")} /> When this piece is attacked</label><label><input type="radio" checked={triggerMode === "piece-at"} onChange={() => setTriggerMode("piece-at")} /> When another piece reaches a square</label><label><input type="radio" checked={triggerMode === "moved"} onChange={() => setTriggerMode("moved")} /> After another piece moves</label><label><input type="radio" checked={triggerMode === "advanced"} onChange={() => setTriggerMode("advanced")} /> In a specific board condition</label></fieldset>{triggerMode === "piece-at" && <><label>Piece<select value={triggerPiece} onChange={(event) => setTriggerPiece(event.target.value)}>{workspace.startingPieces.map((item) => <option key={item.ref} value={item.ref}>{item.label}</option>)}</select></label><label>Square<input value={triggerSquare} minLength={2} maxLength={2} onChange={(event) => setTriggerSquare(event.target.value)} /></label></>}{triggerMode === "moved" && <label>Required piece<select value={triggerPiece} onChange={(event) => setTriggerPiece(event.target.value)}>{workspace.startingPieces.map((item) => <option key={item.ref} value={item.ref}>{item.label}</option>)}</select></label>}{triggerMode === "advanced" && <ConditionBuilder id="response-trigger" label="Board condition" value={advancedTrigger} pieces={workspace.startingPieces} namedConditions={workspace.namedConditions} onChange={setAdvancedTrigger} />}</>}
      {step === 3 && <><h3>When should this response stop applying?</h3><fieldset><legend>Expiration</legend><label><input type="radio" checked={expirationMode === "used"} onChange={() => setExpirationMode("used")} /> After the move is used</label><label><input type="radio" checked={expirationMode === "piece-moves"} onChange={() => setExpirationMode("piece-moves")} /> When this piece moves for any reason</label><label><input type="radio" checked={expirationMode === "advanced"} onChange={() => setExpirationMode("advanced")} /> Advanced condition</label></fieldset>{expirationMode === "advanced" && <ConditionBuilder id="response-expiration" label="Expiration condition" value={advancedExpiration} pieces={workspace.startingPieces} namedConditions={workspace.namedConditions} onChange={setAdvancedExpiration} />}<label>Reason<textarea rows={2} value={note} onChange={(event) => setNote(event.target.value)} /></label></>}
      {errors.length > 0 && <div className="inline-error" role="alert">{errors.join(" ")}</div>}
      <div className="button-row">{step > 1 && <button type="button" onClick={() => setStep(step - 1)}>Back</button>}<button className="primary" type="submit">{step === 3 ? "Review response" : "Next"}</button><button type="button" onClick={cancel}>Cancel</button></div>
    </form>
  );
}

function ExactFixes({ piece, workspace, pending, onValidate, onApply }: {
  piece: StartingPieceSnapshot; workspace: WorkspaceSnapshot; pending: boolean;
  onValidate: (id: string, update: OverrideUpdate) => Promise<RuleDraftValidation>;
  onApply: (id: string, update: OverrideUpdate) => Promise<void>;
}) {
  const [editing, setEditing] = useState<string | null>(null);
  const [target, setTarget] = useState("");
  const [reason, setReason] = useState("");
  const [validation, setValidation] = useState<RuleDraftValidation | null>(null);
  const [errors, setErrors] = useState<string[]>([]);
  const fix = piece.exactFixes.find((item) => item.id === editing) ?? null;
  if (fix) {
    const update: OverrideUpdate = {
      afterSan: fix.afterSan,
      note: reason.trim() || null,
      move: { piece: fix.piece, to: target },
    };
    if (validation) {
      return <RuleReview title="Exact fix" validation={validation} applying={pending} onApply={() => void onApply(fix.id, update).then(() => { setEditing(null); setValidation(null); })} onBack={() => setValidation(null)} onCancel={() => { setEditing(null); setValidation(null); }} />;
    }
    return (
      <form className="authoring-card guided-editor" onSubmit={(event) => {
        event.preventDefault();
        setErrors([]);
        void onValidate(fix.id, update).then((result) => result.valid ? setValidation(result) : setErrors(result.errors)).catch((error: unknown) => setErrors([error instanceof Error ? error.message : "Validation failed."]));
      }}>
        <span className="eyebrow">Edit exact fix</span>
        <label>Position<input value={numberHistory(fix.afterSan)} readOnly /></label>
        <label>Move<span>{piece.label}</span><input aria-label="Exact fix target" value={target} minLength={2} maxLength={2} onChange={(event) => setTarget(event.target.value)} /></label>
        <label>Reason<textarea value={reason} rows={2} onChange={(event) => setReason(event.target.value)} /></label>
        {errors.length > 0 && <p className="inline-error" role="alert">{errors.join(" ")}</p>}
        <div className="button-row"><button className="primary" type="submit">Review changes</button><button type="button" onClick={() => setEditing(null)}>Cancel</button></div>
      </form>
    );
  }
  return (
    <section className="authoring-card exact-fixes">
      <span className="eyebrow">Exact fixes</span>
      {piece.exactFixes.length === 0 ? <p>No exact-position fixes involving this piece.</p> : piece.exactFixes.map((fix) => <article key={fix.id}><strong>{fix.friendlyStatus === "exact-fix-active" ? "Exact fix active" : "Applies in another position"}</strong><dl><div><dt>After</dt><dd>{numberHistory(fix.afterSan)}</dd></div><div><dt>Play</dt><dd>{fix.moveSan ?? `${piece.label} → ${fix.target}`}</dd></div><div><dt>Reason</dt><dd>{fix.reason ?? "No reason recorded."}</dd></div></dl><button type="button" disabled={pending} onClick={() => { setEditing(fix.id); setTarget(fix.target); setReason(fix.reason ?? ""); }}>Edit exact fix</button></article>)}
      {workspace.attempt?.authoringPrefill.piece === piece.ref && <p className="muted">The pending move can be accepted here from the attempt card.</p>}
    </section>
  );
}

function PolicyOrderPanel({ workspace, pending, onInspectPiece, onReorderDevelopment, onReorderResponses }: {
  workspace: WorkspaceSnapshot; pending: boolean; onInspectPiece: (piece: string) => void;
  onReorderDevelopment: (ids: string[]) => Promise<void>; onReorderResponses: (ids: string[]) => Promise<void>;
}) {
  const development = useMemo(() => workspace.startingPieces.flatMap((piece) => piece.developmentRules.map((rule) => ({ piece, rule }))).sort((a, b) => a.rule.order - b.rule.order), [workspace.startingPieces]);
  const move = <T extends { id: string }>(items: T[], index: number, direction: -1 | 1) => {
    const next = [...items]; const destination = index + direction;
    if (destination < 0 || destination >= next.length) return items.map((item) => item.id);
    [next[index], next[destination]] = [next[destination], next[index]];
    return next.map((item) => item.id);
  };
  return <details className="policy-order-panel"><summary>Change rule order</summary>
    <h3>Special responses</h3><ol>{workspace.rules.responses.map((item, index) => <li key={item.id}><span>{item.title}</span><span className="order-actions"><button aria-label={`Move ${item.title} earlier`} disabled={pending || index === 0} onClick={() => void onReorderResponses(move(workspace.rules.responses, index, -1))}>Earlier</button><button aria-label={`Move ${item.title} later`} disabled={pending || index === workspace.rules.responses.length - 1} onClick={() => void onReorderResponses(move(workspace.rules.responses, index, 1))}>Later</button></span></li>)}</ol>
    <h3>Normal development order</h3><ol>{development.map((item, index) => <li key={item.rule.id}><button className="order-piece-button" onClick={() => onInspectPiece(item.piece.ref)}>{item.piece.label} → {item.rule.target}</button><span className="order-actions"><button aria-label={`Move ${item.piece.label} earlier`} disabled={pending || index === 0} onClick={() => void onReorderDevelopment(move(development.map((entry) => ({ id: entry.rule.id })), index, -1))}>Earlier</button><button aria-label={`Move ${item.piece.label} later`} disabled={pending || index === development.length - 1} onClick={() => void onReorderDevelopment(move(development.map((entry) => ({ id: entry.rule.id })), index, 1))}>Later</button></span></li>)}</ol>
  </details>;
}

function PieceHistoryPanel({
  pieces,
  onInspectPiece,
}: {
  pieces: StartingPieceSnapshot[];
  onInspectPiece: (piece: string) => void;
}) {
  const history = pieces.filter((piece) => piece.state !== "undeveloped");
  return (
    <details className="policy-order-panel piece-history-panel">
      <summary>Piece history</summary>
      {history.length === 0
        ? <p>No original piece has moved or been captured on this line.</p>
        : <ul>
          {history.map((piece) => (
            <li key={piece.ref}>
              <button
                className="order-piece-button"
                type="button"
                onClick={() => onInspectPiece(piece.ref)}
              >
                {piece.label}
              </button>
              <span>{pieceStatus(piece)}</span>
            </li>
          ))}
        </ul>}
    </details>
  );
}

function readinessFromExpression(expression: Record<string, unknown> | null): { mode: "immediate" | "prerequisites" | "advanced"; prerequisites: string[]; advanced: ConditionNode | null } {
  if (!expression) return { mode: "immediate", prerequisites: [], advanced: null };
  if (typeof expression.moved === "string") return { mode: "prerequisites", prerequisites: [expression.moved], advanced: null };
  if (Array.isArray(expression.all) && expression.all.every((item) => item && typeof item === "object" && typeof (item as Record<string, unknown>).moved === "string")) return { mode: "prerequisites", prerequisites: expression.all.map((item) => String((item as Record<string, unknown>).moved)), advanced: null };
  return { mode: "advanced", prerequisites: [], advanced: safeCondition(expression, "piece:white:pawn:a") };
}

function readinessExpression(mode: string, prerequisites: string[], advanced: ConditionNode) {
  if (mode === "immediate") return null;
  if (mode === "advanced") return conditionToExpression(advanced);
  if (prerequisites.length === 1) return { moved: prerequisites[0] };
  return { all: prerequisites.map((piece) => ({ moved: piece })) };
}

function safeCondition(expression: Record<string, unknown>, fallbackPiece: string): ConditionNode {
  try { return expressionToCondition(expression); } catch { return defaultCondition(fallbackPiece); }
}
function triggerModeFor(node: ConditionNode): "attacked" | "piece-at" | "moved" | "advanced" {
  if (node.kind === "attacked") return "attacked";
  if (node.kind === "piece-at") return "piece-at";
  if (node.kind === "piece-moved" && !node.negated) return "moved";
  return "advanced";
}
function triggerPieceFor(node: ConditionNode, fallback: string) { return node.kind === "piece-at" || node.kind === "attacked" || node.kind === "piece-moved" ? node.piece : fallback; }
function triggerSquareFor(node: ConditionNode) { return node.kind === "piece-at" ? node.square : "e4"; }
function triggerExpression(mode: string, selected: string, piece: string, square: string, advanced: ConditionNode) {
  if (mode === "attacked") return { attacked: selected };
  if (mode === "piece-at") return { at: { piece, square } };
  if (mode === "moved") return { moved: piece };
  return conditionToExpression(advanced);
}
function friendlyLabel(status: string) { return ({ "not-ready": "Not ready", ready: "Ready", recommended: "Recommended now", blocked: "Blocked", completed: "Completed", "not-triggered": "Not triggered", available: "Available" } as Record<string, string>)[status] ?? status; }
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
