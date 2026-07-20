import { useState } from "react";

import { conditionToExpression, defaultCondition, expressionToCondition, type ConditionNode } from "../authoring/conditionAst";
import type { NamedConditionDraft, RuleDraftValidation, WorkspaceSnapshot } from "../types/workspace";
import { ConditionBuilder } from "./ConditionBuilder";
import { RuleReview } from "./RuleReview";

export function ConditionLibrary({
  workspace,
  pending,
  onValidate,
  onApply,
  onDelete,
}: {
  workspace: WorkspaceSnapshot;
  pending: boolean;
  onValidate: (draft: NamedConditionDraft) => Promise<RuleDraftValidation>;
  onApply: (draft: NamedConditionDraft) => Promise<void>;
  onDelete: (id: string) => Promise<void>;
}) {
  const [editing, setEditing] = useState<string | "new" | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const existing = editing && editing !== "new"
    ? workspace.namedConditions.find((item) => item.id === editing) ?? null
    : null;
  if (editing) {
    return (
      <NamedConditionEditor
        key={editing}
        workspace={workspace}
        existing={existing}
        pending={pending}
        onValidate={onValidate}
        onApply={onApply}
        onCancel={() => setEditing(null)}
      />
    );
  }
  return (
    <details className="authoring-card management-section">
      <summary>Condition library</summary>
      {workspace.namedConditions.length === 0
        ? <p>No reusable conditions.</p>
        : <ul>{workspace.namedConditions.map((condition) => (
          <li key={condition.id}>
            <div><strong>{condition.id}</strong><span>{condition.summary}</span></div>
            {condition.references.length > 0 && <small>Used by {condition.references.join(", ")}</small>}
            <div className="button-row">
              <button type="button" onClick={() => setEditing(condition.id)}>Edit condition</button>
              <button
                className="danger-button"
                type="button"
                disabled={pending}
                title={condition.references.length ? `Referenced by ${condition.references.join(", ")}` : undefined}
                onClick={() => {
                  if (condition.references.length) {
                    setConfirmDelete(condition.id);
                  } else {
                    void onDelete(condition.id);
                  }
                }}
              >
                Remove condition
              </button>
            </div>
            {confirmDelete === condition.id && (
              <div className="dependency-warning" role="alert">
                <p>Referenced by {condition.references.join(", ")}. Removal will fail until those references are changed.</p>
                <div className="button-row">
                  <button type="button" onClick={() => void onDelete(condition.id)}>Try removal</button>
                  <button type="button" onClick={() => setConfirmDelete(null)}>Cancel</button>
                </div>
              </div>
            )}
          </li>
        ))}</ul>}
      <button type="button" onClick={() => setEditing("new")}>Add named condition</button>
    </details>
  );
}

function NamedConditionEditor({
  workspace,
  existing,
  pending,
  onValidate,
  onApply,
  onCancel,
}: {
  workspace: WorkspaceSnapshot;
  existing: WorkspaceSnapshot["namedConditions"][number] | null;
  pending: boolean;
  onValidate: (draft: NamedConditionDraft) => Promise<RuleDraftValidation>;
  onApply: (draft: NamedConditionDraft) => Promise<void>;
  onCancel: () => void;
}) {
  const fallback = workspace.startingPieces[0]?.ref ?? "piece:white:pawn:a";
  const [name, setName] = useState(existing?.id ?? "");
  const id = slug(name);
  const [condition, setCondition] = useState<ConditionNode>(
    existing ? expressionToCondition(existing.expression) : defaultCondition(fallback),
  );
  const [validation, setValidation] = useState<RuleDraftValidation | null>(null);
  const [errors, setErrors] = useState<string[]>([]);
  const draft: NamedConditionDraft = {
    id,
    originalId: existing?.id ?? null,
    condition: conditionToExpression(condition),
  };
  if (validation) {
    return <RuleReview title="Named condition" validation={validation} applying={pending} onApply={() => void onApply(draft).then(onCancel)} onBack={() => setValidation(null)} onCancel={onCancel} />;
  }
  return (
    <form className="authoring-card guided-editor" onSubmit={(event) => {
      event.preventDefault();
      setErrors([]);
      void onValidate(draft).then((result) => result.valid ? setValidation(result) : setErrors(result.errors));
    }}>
      <span className="eyebrow">{existing ? "Edit named condition" : "Add named condition"}</span>
      <label>Name / ID<input value={name} onChange={(event) => setName(event.target.value)} required /></label>
      <small>Saved ID: <code>{id || "enter-a-name"}</code></small>
      <ConditionBuilder id="named-condition" label="Condition" value={condition} pieces={workspace.startingPieces} namedConditions={workspace.namedConditions.filter((item) => item.id !== existing?.id)} onChange={setCondition} />
      {errors.length > 0 && <p className="inline-error" role="alert">{errors.join(" ")}</p>}
      <div className="button-row"><button className="primary" type="submit" disabled={!id}>Review condition</button><button type="button" onClick={onCancel}>Cancel</button></div>
    </form>
  );
}

function slug(value: string) {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
}
