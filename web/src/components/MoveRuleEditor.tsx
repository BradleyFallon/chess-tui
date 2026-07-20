import { useState } from "react";

import { conditionToExpression, defaultCondition, expressionToCondition, type ConditionNode } from "../authoring/conditionAst";
import type { RuleDraft, RuleDraftValidation, RuleRuntimeSnapshot, StartingPieceSnapshot, WorkspaceSnapshot } from "../types/workspace";
import { ConditionBuilder } from "./ConditionBuilder";
import { RuleReview } from "./RuleReview";
import { StructureScopePicker } from "./StructureScopePicker";

export function MoveRuleEditor({
  workspace,
  piece,
  section,
  existing,
  initialDraft,
  suggestions,
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
  section: "response" | "continuation";
  existing: RuleRuntimeSnapshot | null;
  initialDraft: RuleDraft | null;
  suggestions: Array<{ label: string; expression: Record<string, unknown> }>;
  pickedTarget: string | null;
  pending: boolean;
  onBeginTargetPick: () => void;
  onCancelTargetPick: () => void;
  onValidate: (draft: RuleDraft) => Promise<RuleDraftValidation>;
  onApply: (draft: RuleDraft) => Promise<void>;
  onCancel: () => void;
}) {
  const [target, setTarget] = useState(existing?.destination ?? initialDraft?.target ?? "");
  const [structures, setStructures] = useState(existing?.structures ?? initialDraft?.structures ?? []);
  const [note, setNote] = useState(existing?.note ?? initialDraft?.note ?? "");
  const [unlockEnabled, setUnlockEnabled] = useState(Boolean(existing?.unlockWhen ?? initialDraft?.unlockWhen));
  const [liveEnabled, setLiveEnabled] = useState(Boolean(existing?.when ?? initialDraft?.when));
  const [expireEnabled, setExpireEnabled] = useState(Boolean(existing?.expireWhen ?? initialDraft?.expireWhen));
  const [unlock, setUnlock] = useState<ConditionNode>(
    existing?.unlockWhen ? expressionToCondition(existing.unlockWhen.expression) : initialDraft?.unlockWhen ? expressionToCondition(initialDraft.unlockWhen) : defaultCondition(piece.ref),
  );
  const [live, setLive] = useState<ConditionNode>(
    existing?.when ? expressionToCondition(existing.when.expression) : initialDraft?.when ? expressionToCondition(initialDraft.when) : { kind: "attacked", piece: piece.ref },
  );
  const [expiration, setExpiration] = useState<ConditionNode>(
    existing?.expireWhen ? expressionToCondition(existing.expireWhen.expression) : initialDraft?.expireWhen ? expressionToCondition(initialDraft.expireWhen) : { kind: "piece-moved", piece: piece.ref },
  );
  const [validation, setValidation] = useState<RuleDraftValidation | null>(null);
  const [errors, setErrors] = useState<string[]>([]);
  const draft: RuleDraft = {
    id: existing?.id ?? null,
    section,
    piece: piece.ref,
    target: pickedTarget ?? target,
    structures,
    note: note.trim() || null,
    unlockWhen: unlockEnabled ? conditionToExpression(unlock) : null,
    when: liveEnabled ? conditionToExpression(live) : null,
    expireWhen: expireEnabled ? conditionToExpression(expiration) : null,
  };
  const close = () => {
    onCancelTargetPick();
    onCancel();
  };
  if (validation) {
    return <RuleReview title={section === "response" ? "Special response" : "Later plan"} validation={validation} applying={pending} onApply={() => void onApply(draft).then(close)} onBack={() => setValidation(null)} onCancel={close} />;
  }
  return (
    <form className="authoring-card guided-editor move-rule-editor" onSubmit={(event) => {
      event.preventDefault();
      setErrors([]);
      if (initialDraft && section === "response" && !liveEnabled) {
        setErrors(["Choose a current trigger for the broader response."]);
        return;
      }
      void onValidate(draft).then((result) => result.valid ? setValidation(result) : setErrors(result.errors));
    }}>
      <span className="eyebrow">{existing ? "Edit" : "Add"} {section === "response" ? "special response" : "later plan"}</span>
      <h3>Move {piece.label}</h3>
      <label>Destination<div className="target-input-row"><input value={pickedTarget ?? target} minLength={2} maxLength={2} onChange={(event) => { onCancelTargetPick(); setTarget(event.target.value); }} required /><button type="button" onClick={onBeginTargetPick}>Choose on board</button></div></label>
      {initialDraft && suggestions.length > 0 && (
        <fieldset className="condition-suggestions">
          <legend>Suggested current triggers</legend>
          <p>Suggestions are optional. Choose one or define a current condition below.</p>
          {suggestions.map((suggestion) => (
            <button
              key={`${suggestion.label}:${JSON.stringify(suggestion.expression)}`}
              type="button"
              onClick={() => {
                setLive(expressionToCondition(suggestion.expression));
                setLiveEnabled(true);
              }}
            >
              Use suggestion: {suggestion.label}
            </button>
          ))}
        </fieldset>
      )}
      <StructureScopePicker structures={workspace.rules.structures} selected={structures} onChange={setStructures} />
      <fieldset>
        <legend>When should it become part of the plan?</legend>
        <label><input type="radio" checked={!unlockEnabled} onChange={() => setUnlockEnabled(false)} /> Available immediately</label>
        <label><input type="radio" checked={unlockEnabled} onChange={() => setUnlockEnabled(true)} /> Unlock after a condition occurs</label>
        <small>Unlocking is historical and stays true for the rest of this line.</small>
      </fieldset>
      {unlockEnabled && <ConditionBuilder id={`${section}-unlock`} label="Historical unlock condition" value={unlock} pieces={workspace.startingPieces} namedConditions={workspace.namedConditions} onChange={setUnlock} />}
      <fieldset>
        <legend>When should it apply now?</legend>
        <label><input type="radio" checked={!liveEnabled} onChange={() => setLiveEnabled(false)} /> Always, once unlocked</label>
        <label><input type="radio" checked={liveEnabled} onChange={() => setLiveEnabled(true)} /> In a current board condition</label>
      </fieldset>
      {liveEnabled && <ConditionBuilder id={`${section}-live`} label="Current applicability" value={live} pieces={workspace.startingPieces} namedConditions={workspace.namedConditions} onChange={setLive} />}
      <fieldset>
        <legend>When should it expire?</legend>
        <label><input type="radio" checked={!expireEnabled} onChange={() => setExpireEnabled(false)} /> After use</label>
        <label><input type="radio" checked={expireEnabled} onChange={() => setExpireEnabled(true)} /> When a condition becomes true</label>
      </fieldset>
      {expireEnabled && <ConditionBuilder id={`${section}-expire`} label="Expiration condition" value={expiration} pieces={workspace.startingPieces} namedConditions={workspace.namedConditions} onChange={setExpiration} />}
      <label>Teaching note<textarea value={note} onChange={(event) => setNote(event.target.value)} /></label>
      {errors.length > 0 && <p className="inline-error" role="alert">{errors.join(" ")}</p>}
      <div className="button-row"><button className="primary" type="submit">Review changes</button><button type="button" onClick={close}>Cancel</button></div>
    </form>
  );
}
