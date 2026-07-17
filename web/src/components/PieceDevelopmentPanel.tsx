import { type FormEvent, useMemo, useState } from "react";

import type {
  DevelopmentRuleDraft,
  DevelopmentRuleValidation,
  StartingPieceSnapshot,
  WorkspaceSnapshot,
} from "../types/workspace";
import type { DevelopmentRuleSnapshot } from "../types/workspace";

interface Props {
  workspace: WorkspaceSnapshot;
  piece: StartingPieceSnapshot | null;
  pending: boolean;
  pickedTarget: string | null;
  onBeginTargetPick: () => void;
  onCancelTargetPick: () => void;
  onValidate: (draft: DevelopmentRuleDraft) => Promise<DevelopmentRuleValidation>;
  onApply: (draft: DevelopmentRuleDraft) => Promise<void>;
  onDelete: (ruleId: string) => Promise<void>;
  onReorder: (ruleIds: string[]) => Promise<void>;
  onInspectPiece: (pieceRef: string) => void;
}

export function PieceDevelopmentPanel({
  workspace,
  piece,
  pending,
  pickedTarget,
  onBeginTargetPick,
  onCancelTargetPick,
  onValidate,
  onApply,
  onDelete,
  onReorder,
  onInspectPiece,
}: Props) {
  const initialRule = piece?.developmentRules[0] ?? null;
  const [target, setTarget] = useState(initialRule?.target ?? "");
  const [note, setNote] = useState(initialRule?.note ?? "");
  const [structures, setStructures] = useState(initialRule?.structures.join(", ") ?? "");
  const [readyWhen, setReadyWhen] = useState(
    initialRule?.readyWhen
      ? JSON.stringify(initialRule.readyWhen.expression, null, 2)
      : "",
  );
  const [editing, setEditing] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const orderedRules = useMemo(
    () => workspace.startingPieces
      .flatMap((item) => item.developmentRules.map((rule) => ({ piece: item, rule })))
      .sort((left, right) => left.rule.order - right.rule.order),
    [workspace.startingPieces],
  );
  const resetDraft = () => {
    setTarget(initialRule?.target ?? "");
    setNote(initialRule?.note ?? "");
    setStructures(initialRule?.structures.join(", ") ?? "");
    setReadyWhen(
      initialRule?.readyWhen
        ? JSON.stringify(initialRule.readyWhen.expression, null, 2)
        : "",
    );
    setMessage(null);
    onCancelTargetPick();
  };

  if (!piece) {
    return (
      <section className="piece-development" aria-labelledby="piece-development-heading">
        <span className="eyebrow" id="piece-development-heading">Piece development</span>
        <p className="muted">Click any piece on the board to inspect its original identity and development assignment.</p>
        <DevelopmentOrder pieces={orderedRules} pending={pending} onReorder={onReorder} onInspectPiece={onInspectPiece} />
      </section>
    );
  }

  const rule = piece.developmentRules[0] ?? null;
  const effectiveTarget = pickedTarget ?? target;
  const draft = (): DevelopmentRuleDraft => ({
    id: rule?.id ?? null,
    piece: piece.ref,
    target: effectiveTarget.trim(),
    structures: structures.split(",").map((value) => value.trim()).filter(Boolean),
    note: note.trim() || null,
    readyWhen: parseCondition(readyWhen),
  });
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    try {
      const candidate = draft();
      const validation = await onValidate(candidate);
      if (!validation.valid) {
        setMessage(validation.errors.join("\n"));
        return;
      }
      setMessage(`Valid · development order ${validation.order}. Applying…`);
      await onApply(candidate);
      setMessage("Development rule applied.");
      setEditing(false);
      onCancelTargetPick();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not validate the rule.");
    }
  };

  return (
    <section className="piece-development" aria-labelledby="piece-development-heading">
      <span className="eyebrow" id="piece-development-heading">Piece development</span>
      <div className="piece-inspector-heading">
        <div>
          <h2>{piece.label}</h2>
          <code>{piece.ref}</code>
        </div>
        <span className={`development-state state-${piece.state}`}>{stateLabel(piece)}</span>
      </div>
      <dl className="piece-facts">
        <div><dt>Starting</dt><dd>{piece.startingSquare}</dd></div>
        <div><dt>Current</dt><dd>{piece.currentSquare ?? "Captured"}</dd></div>
        <div><dt>Assignments</dt><dd>{piece.developmentRules.length || "Not assigned"}</dd></div>
        {rule && <div><dt>First order</dt><dd>{rule.order}</dd></div>}
      </dl>

      {!editing ? (
        <div className="piece-rule-summary">
          {rule ? (
            <>
              <strong>Target {rule.target}</strong>
              <p>{rule.structures.length ? `Structures: ${rule.structures.join(", ")}` : "Global assignment"}</p>
              <p>{rule.readyWhen?.explanation ?? "Ready immediately."}</p>
              <p>{rule.note ?? "No note."}</p>
              <p className="muted">{rule.reason}</p>
            </>
          ) : <p className="muted">This starting piece has no development assignment.</p>}
          <button
            className="primary"
            disabled={pending || (!rule && piece.state !== "undeveloped")}
            onClick={() => setEditing(true)}
          >
            {rule ? "Edit development rule" : "Add development rule"}
          </button>
        </div>
      ) : (
        <form className="rule-edit-form development-rule-editor" onSubmit={(event) => void submit(event)}>
          <label>Target
            <div className="target-input-row">
              <input value={effectiveTarget} onChange={(event) => { onCancelTargetPick(); setTarget(event.target.value); }} minLength={2} maxLength={2} required />
              <button type="button" onClick={onBeginTargetPick} disabled={pending}>Choose target</button>
            </div>
          </label>
          {pickedTarget && <p className="target-picking-note">Previewing {pickedTarget}. Apply or cancel the target selection.</p>}
          <label>Ready when (condition JSON)
            <textarea
              value={readyWhen}
              onChange={(event) => setReadyWhen(event.target.value)}
              rows={4}
              placeholder='{"moved":"piece:white:pawn:d"}'
            />
          </label>
          <label>Structure scopes (comma separated)
            <input value={structures} onChange={(event) => setStructures(event.target.value)} placeholder="traditional, active-c4" />
          </label>
          <label>Note<textarea value={note} onChange={(event) => setNote(event.target.value)} rows={2} /></label>
          {message && <p className={message.startsWith("Valid") || message.endsWith("applied.") ? "validation-ok" : "inline-error"} role="status">{message}</p>}
          <div className="button-row">
            <button className="primary" type="submit" disabled={pending}>Validate & apply</button>
            <button type="button" onClick={() => { resetDraft(); setEditing(false); }} disabled={pending}>Cancel</button>
            {rule && <button className="danger-button" type="button" onClick={() => void onDelete(rule.id)} disabled={pending}>Delete</button>}
          </div>
        </form>
      )}
      <DevelopmentOrder pieces={orderedRules} pending={pending} onReorder={onReorder} onInspectPiece={onInspectPiece} />
    </section>
  );
}

function DevelopmentOrder({
  pieces,
  pending,
  onReorder,
  onInspectPiece,
}: {
  pieces: Array<{ piece: StartingPieceSnapshot; rule: DevelopmentRuleSnapshot }>;
  pending: boolean;
  onReorder: (ids: string[]) => Promise<void>;
  onInspectPiece: (pieceRef: string) => void;
}) {
  const move = (index: number, direction: -1 | 1) => {
    const next = [...pieces];
    const destination = index + direction;
    if (destination < 0 || destination >= next.length) return;
    [next[index], next[destination]] = [next[destination], next[index]];
    void onReorder(next.map((item) => item.rule.id));
  };
  return (
    <details className="development-order">
      <summary>Development order <span>{pieces.length}</span></summary>
      <ol>
        {pieces.map((item, index) => (
          <li key={item.rule.id}>
            <button className="order-piece-button" onClick={() => onInspectPiece(item.piece.ref)}>{item.piece.label} → {item.rule.target}</button>
            <span className="order-actions">
              <button aria-label={`Move ${item.piece.label} earlier`} disabled={pending || index === 0} onClick={() => move(index, -1)}>↑</button>
              <button aria-label={`Move ${item.piece.label} later`} disabled={pending || index === pieces.length - 1} onClick={() => move(index, 1)}>↓</button>
            </span>
          </li>
        ))}
      </ol>
    </details>
  );
}

function parseCondition(value: string): Record<string, unknown> | null {
  if (!value.trim()) return null;
  const parsed: unknown = JSON.parse(value);
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("Ready when must be a JSON object.");
  }
  return parsed as Record<string, unknown>;
}

function stateLabel(piece: StartingPieceSnapshot): string {
  if (piece.state === "developed" && piece.firstMovedPly !== null) {
    return `Developed · ply ${piece.firstMovedPly}`;
  }
  if (piece.state === "captured-undeveloped" && piece.capturedPly !== null) {
    return `Captured undeveloped · ply ${piece.capturedPly}`;
  }
  if (piece.state === "captured-developed" && piece.capturedPly !== null) {
    return `Captured developed · ply ${piece.capturedPly}`;
  }
  return "Undeveloped";
}
