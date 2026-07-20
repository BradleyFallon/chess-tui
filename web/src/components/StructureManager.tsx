import { useState } from "react";

import { conditionToExpression, defaultCondition, expressionToCondition, type ConditionNode } from "../authoring/conditionAst";
import type { RuleDraftValidation, StructureDraft, StructureRuntimeSnapshot, WorkspaceSnapshot } from "../types/workspace";
import { ConditionBuilder } from "./ConditionBuilder";
import { RuleReview } from "./RuleReview";

export function StructureManager({
  workspace,
  pending,
  onValidate,
  onApply,
  onDelete,
  onReorder,
}: {
  workspace: WorkspaceSnapshot;
  pending: boolean;
  onValidate: (draft: StructureDraft) => Promise<RuleDraftValidation>;
  onApply: (draft: StructureDraft) => Promise<void>;
  onDelete: (id: string) => Promise<void>;
  onReorder: (ids: string[]) => Promise<void>;
}) {
  const [editing, setEditing] = useState<string | "new" | null>(null);
  const structure = editing && editing !== "new"
    ? workspace.rules.structures.find((item) => item.id === editing) ?? null
    : null;
  if (editing) {
    return <StructureEditor key={editing} workspace={workspace} existing={structure} pending={pending} onValidate={onValidate} onApply={onApply} onCancel={() => setEditing(null)} />;
  }
  const move = (index: number, direction: -1 | 1) => {
    const ids = workspace.rules.structures.map((item) => item.id);
    const destination = index + direction;
    if (destination < 0 || destination >= ids.length) return ids;
    [ids[index], ids[destination]] = [ids[destination], ids[index]];
    return ids;
  };
  return (
    <details className="authoring-card management-section">
      <summary>Plans and structures</summary>
      {workspace.rules.structures.length === 0
        ? <p>No plans defined.</p>
        : <ol>{workspace.rules.structures.map((item, index) => (
          <li key={item.id}>
            <div><strong>{item.name}</strong><span>{item.status} · {item.reason}</span></div>
            {item.affectedPolicyItems.length > 0 && <small>Scopes {item.affectedPolicyItems.join(", ")}</small>}
            <div className="button-row">
              <button type="button" onClick={() => setEditing(item.id)}>Edit plan</button>
              <button type="button" disabled={pending || index === 0} aria-label={`Move ${item.name} earlier`} onClick={() => void onReorder(move(index, -1))}>Earlier</button>
              <button type="button" disabled={pending || index === workspace.rules.structures.length - 1} aria-label={`Move ${item.name} later`} onClick={() => void onReorder(move(index, 1))}>Later</button>
              <button className="danger-button" type="button" disabled={pending} onClick={() => void onDelete(item.id)}>Remove plan</button>
            </div>
          </li>
        ))}</ol>}
      <button type="button" onClick={() => setEditing("new")}>Add plan</button>
    </details>
  );
}

function StructureEditor({
  workspace,
  existing,
  pending,
  onValidate,
  onApply,
  onCancel,
}: {
  workspace: WorkspaceSnapshot;
  existing: StructureRuntimeSnapshot | null;
  pending: boolean;
  onValidate: (draft: StructureDraft) => Promise<RuleDraftValidation>;
  onApply: (draft: StructureDraft) => Promise<void>;
  onCancel: () => void;
}) {
  const firstPiece = workspace.startingPieces[0]?.ref ?? "piece:white:pawn:a";
  const [name, setName] = useState(existing?.name ?? "");
  const [note, setNote] = useState(existing?.note ?? "");
  const [available, setAvailable] = useState<ConditionNode>(existing ? expressionToCondition(existing.availableWhen.expression) : defaultCondition(firstPiece));
  const [selected, setSelected] = useState<ConditionNode>(existing ? expressionToCondition(existing.selectedWhen.expression) : { kind: "piece-at", piece: firstPiece, square: "e4" });
  const [validation, setValidation] = useState<RuleDraftValidation | null>(null);
  const [errors, setErrors] = useState<string[]>([]);
  const draft: StructureDraft = {
    id: existing?.id ?? null,
    name,
    note: note.trim() || null,
    availableWhen: conditionToExpression(available),
    selectedWhen: conditionToExpression(selected),
  };
  if (validation) {
    return <RuleReview title="Plan" validation={validation} applying={pending} onApply={() => void onApply(draft).then(onCancel)} onBack={() => setValidation(null)} onCancel={onCancel} />;
  }
  return (
    <form className="authoring-card guided-editor" onSubmit={(event) => {
      event.preventDefault();
      setErrors([]);
      void onValidate(draft).then((result) => result.valid ? setValidation(result) : setErrors(result.errors));
    }}>
      <span className="eyebrow">{existing ? "Edit plan" : "Add plan"}</span>
      <label>Name<input value={name} onChange={(event) => setName(event.target.value)} required /></label>
      <ConditionBuilder id="plan-available" label="Available when" value={available} pieces={workspace.startingPieces} namedConditions={workspace.namedConditions} onChange={setAvailable} />
      <ConditionBuilder id="plan-selected" label="Selected when" value={selected} pieces={workspace.startingPieces} namedConditions={workspace.namedConditions} onChange={setSelected} />
      <label>Teaching note<textarea value={note} onChange={(event) => setNote(event.target.value)} /></label>
      {errors.length > 0 && <p className="inline-error" role="alert">{errors.join(" ")}</p>}
      <div className="button-row"><button className="primary" type="submit">Review plan</button><button type="button" onClick={onCancel}>Cancel</button></div>
    </form>
  );
}
