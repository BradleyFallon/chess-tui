import { useState } from "react";

import type {
  ActionAttemptDraft,
  DevelopmentDraft,
  InterruptDraft,
  MutationPreview,
  PieceScript,
  WorkspaceSnapshot,
} from "../types/workspace";
import { ConditionBuilder } from "./ConditionBuilder";

interface Props {
  workspace: WorkspaceSnapshot;
  piece: PieceScript | null;
  pending: boolean;
  onPreviewDevelopment: (draft: DevelopmentDraft) => Promise<MutationPreview>;
  onApplyDevelopment: (draft: DevelopmentDraft) => Promise<void>;
  onDeleteDevelopment: (alias: string) => Promise<void>;
  onPreviewInterrupt: (draft: InterruptDraft) => Promise<MutationPreview>;
  onApplyInterrupt: (draft: InterruptDraft) => Promise<void>;
  onDeleteInterrupt: (alias: string, id: string) => Promise<void>;
  onReorderDevelopment: (aliases: string[]) => Promise<void>;
  onReorderInterrupts: (refs: string[]) => Promise<void>;
  onSelectPiece: (alias: string) => void;
}

export function PieceAuthoringPanel(props: Props) {
  const { workspace, piece, pending } = props;
  return (
    <aside className="panel authoring-panel" aria-label="Rulebook authoring">
      <div className="authoring-scroll">
        <section className="authoring-section">
          <span className="eyebrow">Piece</span>
          <label>
            Inspect piece
            <select
              aria-label="Inspect piece"
              value={piece?.alias ?? ""}
              onChange={(event) => props.onSelectPiece(event.target.value)}
            >
              {workspace.pieceScripts.map((item) => (
                <option key={item.alias} value={item.alias}>{item.label}</option>
              ))}
            </select>
          </label>
          {piece ? (
            <>
              <h2>{piece.label}</h2>
              <code>{piece.ref}</code>
              <span className={`friendly-status status-${piece.mechanicalState}`}>{piece.mechanicalState}</span>
              <p>Current square: {piece.currentSquare ?? "captured"}</p>
            </>
          ) : <p>Select a board piece or an ordered alias.</p>}
        </section>

        <CurrentDecision workspace={workspace} />

        {piece && piece.authorable ? (
          <>
            <DevelopmentEditor {...props} piece={piece} />
            <InterruptList {...props} piece={piece} />
          </>
        ) : piece ? <OpponentPiece piece={piece} /> : null}

        {piece && <RelationshipPanel piece={piece} />}
        <OrderEditor title="Development order" values={workspace.developmentOrder} pending={pending} onSelect={props.onSelectPiece} onChange={props.onReorderDevelopment} />
        <OrderEditor title="Interrupt order" values={workspace.interruptOrder} pending={pending} onSelect={(ref) => props.onSelectPiece(ref.split(".")[0])} onChange={props.onReorderInterrupts} />
        <details className="policy-details-entry">
          <summary>Policy details</summary>
          <p>Rulebook v{workspace.rulebook.version} · {workspace.rulebook.path}</p>
          <pre>{JSON.stringify(workspace.decision?.trace ?? [], null, 2)}</pre>
          {workspace.rulebook.warnings.map((warning) => <p key={warning}>{warning}</p>)}
        </details>
      </div>
    </aside>
  );
}

function CurrentDecision({ workspace }: { workspace: WorkspaceSnapshot }) {
  const decision = workspace.decision;
  return (
    <section className="authoring-card current-decision-card">
      <span className="eyebrow">Current decision</span>
      {decision?.status === "ready" ? (
        <>
          <strong>{decision.moveSan}</strong>
          <code>{decision.instructionRef}</code>
          <p>{decision.why}</p>
        </>
      ) : decision?.frontier ? (
        <>
          <strong>{decision.frontier.reason}</strong>
          <p>{decision.frontier.explanation}</p>
        </>
      ) : <p>Waiting for the opponent.</p>}
    </section>
  );
}

function DevelopmentEditor(props: Props & { piece: PieceScript }) {
  const { piece, pending, onPreviewDevelopment, onApplyDevelopment, onDeleteDevelopment } = props;
  const existing = piece.development;
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<DevelopmentDraft>(() => ({
    alias: piece.alias,
    to: existing?.to ?? piece.currentSquare ?? "e4",
    requires: existing?.requires ?? [],
    when: existing?.when ?? null,
    why: existing?.why ?? "",
  }));
  const [preview, setPreview] = useState<MutationPreview | null>(null);
  return (
    <section className="authoring-section">
      <span className="eyebrow">Default development</span>
      {existing && !editing ? (
        <article className="authoring-card">
          <strong>Move to {existing.to}</strong>
          <span className={`friendly-status status-${existing.status}`}>{existing.status}</span>
          <p>{existing.why}</p>
          <small>{existing.explanation}</small>
          <button type="button" onClick={() => setEditing(true)}>Edit development</button>
        </article>
      ) : editing || !existing ? (
        <div className="guided-editor">
          <label>Move to<input value={draft.to} maxLength={2} onChange={(event) => setDraft({ ...draft, to: event.target.value })} /></label>
          <label>Requires<input value={draft.requires.join(", ")} onChange={(event) => setDraft({ ...draft, requires: splitList(event.target.value) })} /></label>
          <ConditionBuilder value={draft.when} pieces={props.workspace.pieceScripts} onChange={(when) => setDraft({ ...draft, when })} />
          <label>Why<textarea required value={draft.why} onChange={(event) => setDraft({ ...draft, why: event.target.value })} /></label>
          <button disabled={pending} type="button" onClick={() => void onPreviewDevelopment(draft).then(setPreview)}>Validate and review</button>
          {preview && <Review preview={preview} onApply={() => void onApplyDevelopment(draft)} pending={pending} />}
          {existing && <button className="danger-button" type="button" onClick={() => void onDeleteDevelopment(piece.alias)}>Delete development</button>}
        </div>
      ) : (
        <button type="button" onClick={() => setEditing(true)}>Add development</button>
      )}
    </section>
  );
}

function InterruptList(props: Props & { piece: PieceScript }) {
  const [adding, setAdding] = useState(false);
  return (
    <section className="authoring-section">
      <span className="eyebrow">Interrupting rules</span>
      {props.piece.interrupts.map((rule) => (
        <article className="authoring-card" key={rule.reference}>
          <strong>{rule.id}</strong>
          <span className={`friendly-status status-${rule.status}`}>{rule.status}</span>
          <p>{rule.why}</p>
          <ol>{rule.attempts.map((attempt, index) => <li key={index}>{attempt.kind}: {attempt.value} · {attempt.status}</li>)}</ol>
          <small>{rule.explanation}</small>
          <button className="danger-button" type="button" disabled={props.pending} onClick={() => void props.onDeleteInterrupt(props.piece.alias, rule.id)}>Delete</button>
        </article>
      ))}
      <button type="button" onClick={() => setAdding(true)}>Add interrupt</button>
      {adding && <InterruptWizard {...props} piece={props.piece} onClose={() => setAdding(false)} />}
    </section>
  );
}

function InterruptWizard(props: Props & { piece: PieceScript; onClose: () => void }) {
  const [step, setStep] = useState(1);
  const [draft, setDraft] = useState<InterruptDraft>({
    alias: props.piece.alias,
    id: null,
    requires: [],
    afterSan: null,
    when: null,
    required: false,
    attempts: [{ move: props.piece.currentSquare ?? "e4" }],
    why: "",
  });
  const [preview, setPreview] = useState<MutationPreview | null>(null);
  return (
    <div className="guided-editor interrupt-wizard" role="dialog" aria-label={`Add interrupt for ${props.piece.label}`}>
      <h3>Step {step} of 5</h3>
      {step === 1 && (
        <>
          <ConditionBuilder value={draft.when} pieces={props.workspace.pieceScripts} onChange={(when) => setDraft({ ...draft, when, afterSan: null })} />
          <button type="button" onClick={() => setDraft({ ...draft, when: null, afterSan: props.workspace.position.historySan })}>Exact position only</button>
          {draft.afterSan && <small>Exact after: {draft.afterSan.join(" ") || "start"}</small>}
        </>
      )}
      {step === 2 && (
        <fieldset>
          <legend>If triggered and no response works</legend>
          <label><input type="radio" checked={!draft.required} onChange={() => setDraft({ ...draft, required: false })} /> Continue checking other rules</label>
          <label><input type="radio" checked={draft.required} onChange={() => setDraft({ ...draft, required: true })} /> Stop with an unhandled-rule frontier</label>
        </fieldset>
      )}
      {step === 3 && <AttemptEditor attempts={draft.attempts} pieces={props.workspace.pieceScripts} onChange={(attempts) => setDraft({ ...draft, attempts })} />}
      {step === 4 && <label>Why<textarea required value={draft.why} onChange={(event) => setDraft({ ...draft, why: event.target.value })} /></label>}
      {step === 5 && (
        <>
          <button type="button" disabled={props.pending} onClick={() => void props.onPreviewInterrupt(draft).then(setPreview)}>Validate and review</button>
          {preview && <Review preview={preview} pending={props.pending} onApply={() => void props.onApplyInterrupt(draft).then(props.onClose)} />}
        </>
      )}
      <div className="button-row">
        <button type="button" disabled={step === 1} onClick={() => setStep(step - 1)}>Earlier step</button>
        <button type="button" disabled={step === 5} onClick={() => setStep(step + 1)}>Later step</button>
        <button type="button" onClick={props.onClose}>Cancel</button>
      </div>
    </div>
  );
}

function AttemptEditor({ attempts, pieces, onChange }: { attempts: ActionAttemptDraft[]; pieces: PieceScript[]; onChange: (attempts: ActionAttemptDraft[]) => void }) {
  const replaceAttempt = (index: number, attempt: ActionAttemptDraft) => onChange(attempts.map((item, itemIndex) => itemIndex === index ? attempt : item));
  return (
    <fieldset>
      <legend>Ordered attempts</legend>
      {attempts.map((attempt, index) => {
        const kind = attempt.move ? "move" : attempt.captureType ? "captureType" : "capture";
        return (
          <div className="attempt-row" key={index}>
            <select value={kind} onChange={(event) => replaceAttempt(index, event.target.value === "move" ? { move: "e4" } : event.target.value === "captureType" ? { captureType: "bishop" } : { capture: "attacker" })}>
              <option value="move">Move to a square</option>
              <option value="capture">Capture attacker/piece</option>
              <option value="captureType">Capture by type</option>
            </select>
            {kind === "move" && <input aria-label="Move square" value={attempt.move} onChange={(event) => replaceAttempt(index, { move: event.target.value })} />}
            {kind === "capture" && <select aria-label="Capture target" value={attempt.capture} onChange={(event) => replaceAttempt(index, { capture: event.target.value })}><option value="attacker">Triggering attacker</option>{pieces.filter((piece) => !piece.authorable).map((piece) => <option key={piece.alias} value={piece.alias}>{piece.label}</option>)}</select>}
            {kind === "captureType" && <select aria-label="Capture type" value={attempt.captureType} onChange={(event) => replaceAttempt(index, { captureType: event.target.value as ActionAttemptDraft["captureType"] })}>{["pawn", "knight", "bishop", "rook", "queen", "king"].map((type) => <option key={type}>{type}</option>)}</select>}
            <button type="button" disabled={index === 0} onClick={() => onChange(moveItem(attempts, index, index - 1))}>Earlier</button>
            <button type="button" disabled={index === attempts.length - 1} onClick={() => onChange(moveItem(attempts, index, index + 1))}>Later</button>
            <button type="button" disabled={attempts.length === 1} onClick={() => onChange(attempts.filter((_, itemIndex) => itemIndex !== index))}>Remove</button>
          </div>
        );
      })}
      <button type="button" onClick={() => onChange([...attempts, { move: "e4" }])}>Add attempt</button>
    </fieldset>
  );
}

function RelationshipPanel({ piece }: { piece: PieceScript }) {
  const facts = piece.relationships;
  return (
    <details className="authoring-card relationship-panel">
      <summary>Current board relationships</summary>
      <dl className="piece-facts">
        <div><dt>Attackers</dt><dd>{facts.attackerCount}</dd></div>
        <div><dt>Defenders</dt><dd>{facts.defenderCount}</dd></div>
        <div><dt>Status</dt><dd>{facts.underDefended ? "Under-defended" : facts.undefended ? "Undefended" : facts.attacked ? "Attacked" : "Quiet"}</dd></div>
        <div><dt>King pin</dt><dd>{facts.kingPinned ? "Yes" : "No"}</dd></div>
      </dl>
      <h4>Attackers</h4>
      <ul>{facts.attackers.map((item) => <li key={item.moveUci}>{item.alias ?? item.piece} via {item.moveUci}</li>)}</ul>
      {facts.defendersByAttacker.map((group) => (
        <section key={group.attacker}>
          <h4>Defenders after {group.attackerAlias ?? group.attacker} captures</h4>
          <ul>{group.defenders.map((item) => <li key={item.moveUci}>{item.alias ?? item.piece} via {item.moveUci}</li>)}</ul>
        </section>
      ))}
    </details>
  );
}

function OpponentPiece({ piece }: { piece: PieceScript }) {
  return (
    <section className="authoring-card">
      <strong>Read-only opponent piece</strong>
      <p>{piece.label} is currently on {piece.currentSquare ?? "a captured square"}.</p>
      <p>This piece may be referenced by conditions and capture actions. The Rulebook cannot move it.</p>
    </section>
  );
}

function OrderEditor({ title, values, pending, onSelect, onChange }: { title: string; values: string[]; pending: boolean; onSelect: (value: string) => void; onChange: (values: string[]) => Promise<void> }) {
  return (
    <details className="policy-order-panel">
      <summary>{title}</summary>
      <ol>{values.map((value, index) => <li key={value}><button className="order-piece-button" type="button" onClick={() => onSelect(value)}>{value}</button><span className="order-actions"><button disabled={pending || index === 0} onClick={() => void onChange(moveItem(values, index, index - 1))}>Earlier</button><button disabled={pending || index === values.length - 1} onClick={() => void onChange(moveItem(values, index, index + 1))}>Later</button></span></li>)}</ol>
    </details>
  );
}

function Review({ preview, pending, onApply }: { preview: MutationPreview; pending: boolean; onApply: () => void }) {
  return (
    <section className="rule-review" aria-label="Review change">
      <strong>{preview.valid ? "Ready to apply" : "Validation failed"}</strong>
      <p>Current: {preview.currentDecision ?? "none"}</p>
      <p>Preview: {preview.previewDecision ?? "none"}</p>
      {preview.errors.map((error) => <p className="inline-error" key={error}>{error}</p>)}
      {preview.generatedToml && <details><summary>Generated TOML under Advanced</summary><pre>{preview.generatedToml}</pre></details>}
      <button type="button" disabled={!preview.valid || pending} onClick={onApply}>Apply</button>
    </section>
  );
}

function splitList(value: string) { return value.split(",").map((item) => item.trim()).filter(Boolean); }
function moveItem<T>(items: T[], from: number, to: number): T[] { const next = [...items]; const [item] = next.splice(from, 1); next.splice(to, 0, item); return next; }
