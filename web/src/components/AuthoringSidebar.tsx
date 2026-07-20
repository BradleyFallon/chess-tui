import { useState } from "react";

import type {
  ActionAttemptDraft,
  DevelopmentDraft,
  InterruptDraft,
  InterruptRule,
  MutationPreview,
  PieceScript,
  WorkspaceSnapshot,
} from "../types/workspace";
import { ConditionBuilder } from "./ConditionBuilder";

export type AuthoringTab = "piece" | "rulebook";
type FocusedEditor =
  | { kind: "development" }
  | { kind: "interrupt"; rule: InterruptRule | null; duplicate?: boolean }
  | null;

interface Props {
  workspace: WorkspaceSnapshot;
  piece: PieceScript | null;
  pending: boolean;
  tab: AuthoringTab;
  focusInterruptRef: string | null;
  onTabChange: (tab: AuthoringTab) => void;
  onSelectPiece: (alias: string) => void;
  onFocusInterrupt: (reference: string) => void;
  onFocusHandled: () => void;
  onOpenDetails: (tab: "decision" | "relations" | "engine" | "source") => void;
  onPreviewDevelopment: (draft: DevelopmentDraft) => Promise<MutationPreview>;
  onApplyDevelopment: (draft: DevelopmentDraft) => Promise<void>;
  onDeleteDevelopment: (alias: string) => Promise<void>;
  onPreviewInterrupt: (draft: InterruptDraft) => Promise<MutationPreview>;
  onApplyInterrupt: (draft: InterruptDraft) => Promise<void>;
  onDeleteInterrupt: (alias: string, id: string) => Promise<void>;
  onReorderDevelopment: (aliases: string[]) => Promise<void>;
  onReorderInterrupts: (refs: string[]) => Promise<void>;
}

export function AuthoringSidebar(props: Props) {
  const [editor, setEditor] = useState<FocusedEditor>(() => {
    if (!props.focusInterruptRef || !props.piece) return null;
    const rule = props.piece.interrupts.find(
      (item) => item.reference === props.focusInterruptRef,
    );
    return rule ? { kind: "interrupt", rule } : null;
  });

  const closeEditor = () => {
    setEditor(null);
    props.onFocusHandled();
  };

  return (
    <aside className="authoring-sidebar" aria-label="Authoring Sidebar">
      <nav className="authoring-tabs" aria-label="Authoring views">
        <button
          className={props.tab === "piece" ? "active" : undefined}
          aria-selected={props.tab === "piece"}
          onClick={() => props.onTabChange("piece")}
        >
          Piece
        </button>
        <button
          className={props.tab === "rulebook" ? "active" : undefined}
          aria-selected={props.tab === "rulebook"}
          onClick={() => {
            closeEditor();
            props.onTabChange("rulebook");
          }}
        >
          Rulebook
        </button>
      </nav>
      <div className="authoring-sidebar-body">
        {props.tab === "rulebook" ? (
          <RulebookOutline {...props} />
        ) : editor?.kind === "development" && props.piece ? (
          <DevelopmentEditor {...props} piece={props.piece} onClose={closeEditor} />
        ) : editor?.kind === "interrupt" && props.piece ? (
          <InterruptEditor
            {...props}
            piece={props.piece}
            existing={editor.rule}
            duplicate={editor.duplicate}
            onClose={closeEditor}
          />
        ) : (
          <PieceInspector
            {...props}
            onEditDevelopment={() => setEditor({ kind: "development" })}
            onEditInterrupt={(rule) => setEditor({ kind: "interrupt", rule })}
            onDuplicateInterrupt={(rule) =>
              setEditor({ kind: "interrupt", rule, duplicate: true })}
            onAddInterrupt={() => setEditor({ kind: "interrupt", rule: null })}
          />
        )}
      </div>
    </aside>
  );
}

function PieceInspector(
  props: Props & {
    onEditDevelopment: () => void;
    onEditInterrupt: (rule: InterruptRule) => void;
    onDuplicateInterrupt: (rule: InterruptRule) => void;
    onAddInterrupt: () => void;
  },
) {
  const piece = props.piece;
  if (!piece) {
    return (
      <section className="empty-inspector">
        <span className="piece-glyph">◇</span>
        <strong>Select a piece</strong>
        <p>Choose an original piece on the board or in the Rulebook outline.</p>
      </section>
    );
  }
  const relationshipState = piece.relationships.undefended
    ? "Undefended"
    : piece.relationships.underDefended
      ? "Under-defended"
      : piece.relationships.attacked
        ? "Attacked"
        : "Quiet";
  return (
    <section className="piece-inspector" aria-label="Piece Inspector">
      <header className="piece-header">
        <span className="piece-glyph" aria-hidden="true">{pieceIcon(piece)}</span>
        <div>
          <h2>{friendlyName(piece)}</h2>
          <p>{piece.currentSquare ?? "Captured"} · {formatState(piece.mechanicalState)}</p>
          <code title={piece.ref}>{piece.ref}</code>
        </div>
      </header>

      {!piece.authorable ? (
        <div className="opponent-notice">
          <strong>Read-only opponent piece</strong>
          <p>May be referenced by conditions and capture actions.</p>
        </div>
      ) : (
        <>
          <section className="compact-section">
            <h3>Default development</h3>
            <button
              className="inspector-row development-row"
              type="button"
              aria-label={`Edit default development, ${piece.development?.to ?? "not assigned"}, ${piece.development?.status ?? "unassigned"}`}
              onClick={props.onEditDevelopment}
            >
              <span>Default development</span>
              <strong>{piece.development?.to ?? "Not assigned"}</strong>
              <StatusBadge value={piece.development?.status ?? "+"} />
            </button>
          </section>
          <section className="compact-section">
            <h3>Interrupts</h3>
            <div className="compact-list">
              {piece.interrupts.length ? piece.interrupts.map((rule) => (
                <div className="interrupt-row-shell" key={rule.reference}>
                  <button
                    className="inspector-row interrupt-row"
                    type="button"
                    onClick={() => props.onEditInterrupt(rule)}
                  >
                    <span>
                      <strong>{humanize(rule.id)}</strong>
                      <small>{rule.required ? "Required" : rule.afterSan ? "Exact" : "Conditional"}</small>
                    </span>
                    <StatusBadge value={rule.status} />
                  </button>
                  <details className="overflow-menu">
                    <summary aria-label={`More actions for ${humanize(rule.id)}`}>⋮</summary>
                    <div>
                      <button type="button" onClick={() => props.onEditInterrupt(rule)}>Edit</button>
                      <button type="button" onClick={() => props.onDuplicateInterrupt(rule)}>Duplicate</button>
                      <button
                        type="button"
                        className="danger-text"
                        disabled={props.pending}
                        onClick={() => void props.onDeleteInterrupt(piece.alias, rule.id)}
                      >
                        Delete
                      </button>
                    </div>
                  </details>
                </div>
              )) : <p className="empty-row">No interrupt rules.</p>}
            </div>
            <button className="compact-add" type="button" onClick={props.onAddInterrupt}>
              + Add interrupt
            </button>
          </section>
        </>
      )}

      <button
        className="relationship-summary"
        type="button"
        onClick={() => props.onOpenDetails("relations")}
      >
        <span>
          <strong>Relationships</strong>
          <small>
            {piece.relationships.attackerCount} attacker{piece.relationships.attackerCount === 1 ? "" : "s"}
            {" · "}
            {piece.relationships.defenderCount} defender{piece.relationships.defenderCount === 1 ? "" : "s"}
          </small>
        </span>
        <StatusBadge value={relationshipState} />
      </button>
    </section>
  );
}

function RulebookOutline(props: Props) {
  return (
    <section className="rulebook-outline" aria-label="Rulebook Outline">
      <header className="outline-heading">
        <div>
          <span className="eyebrow">Rulebook Outline</span>
          <h2>{props.workspace.rulebook.name}</h2>
        </div>
        <button
          type="button"
          className="text-button"
          onClick={() => props.onOpenDetails("source")}
        >
          Source
        </button>
      </header>
      <OrderList
        title="Development order"
        kind="development"
        workspace={props.workspace}
        values={props.workspace.developmentOrder}
        pending={props.pending}
        onSelect={(alias) => {
          props.onSelectPiece(alias);
          props.onTabChange("piece");
        }}
        onChange={props.onReorderDevelopment}
      />
      <OrderList
        title="Interrupt order"
        kind="interrupt"
        workspace={props.workspace}
        values={props.workspace.interruptOrder}
        pending={props.pending}
        onSelect={(reference) => {
          props.onSelectPiece(reference.split(".")[0]);
          props.onTabChange("piece");
        }}
        onFocusInterrupt={(reference) => {
          props.onFocusInterrupt(reference);
        }}
        onChange={props.onReorderInterrupts}
      />
      <section className="outline-metadata">
        <div className="section-title-row">
          <h3>Opening metadata</h3>
          <span>{props.workspace.rulebook.openingTags.length}</span>
        </div>
        {props.workspace.rulebook.openingTags.length ? (
          <ul>
            {props.workspace.rulebook.openingTags.map((tag) => (
              <li key={`${tag.eco}-${tag.name}`}>
                <strong>{tag.eco}</strong><span>{tag.name}</span>
              </li>
            ))}
          </ul>
        ) : <p>No authored opening labels.</p>}
      </section>
      <section className="outline-metadata">
        <div className="section-title-row">
          <h3>Warnings</h3>
          <span>{props.workspace.rulebook.warnings.length}</span>
        </div>
        {props.workspace.rulebook.warnings.length ? (
          <ul>{props.workspace.rulebook.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul>
        ) : <p>No Rulebook warnings.</p>}
      </section>
    </section>
  );
}

function OrderList({
  title,
  kind,
  workspace,
  values,
  pending,
  onSelect,
  onFocusInterrupt,
  onChange,
}: {
  title: string;
  kind: "development" | "interrupt";
  workspace: WorkspaceSnapshot;
  values: string[];
  pending: boolean;
  onSelect: (value: string) => void;
  onFocusInterrupt?: (value: string) => void;
  onChange: (values: string[]) => Promise<void>;
}) {
  const [dragIndex, setDragIndex] = useState<number | null>(null);
  const move = (from: number, to: number) => {
    if (from === to || to < 0 || to >= values.length) return;
    void onChange(moveItem(values, from, to));
  };
  return (
    <section className="order-section">
      <div className="section-title-row">
        <h3>{title}</h3>
        <span>{values.length}</span>
      </div>
      <ol aria-label={title}>
        {values.map((value, index) => {
          const alias = kind === "interrupt" ? value.split(".")[0] : value;
          const piece = workspace.pieceScripts.find((item) => item.alias === alias);
          const rule = kind === "interrupt"
            ? piece?.interrupts.find((item) => item.reference === value)
            : null;
          const destination = kind === "development" ? piece?.development?.to : null;
          return (
            <li
              key={value}
              className={dragIndex === index ? "dragging" : undefined}
              draggable={!pending}
              onDragStart={() => setDragIndex(index)}
              onDragEnd={() => setDragIndex(null)}
              onDragOver={(event) => event.preventDefault()}
              onDrop={(event) => {
                event.preventDefault();
                if (dragIndex !== null) move(dragIndex, index);
                setDragIndex(null);
              }}
            >
              <span className="drag-handle" aria-hidden="true">⠿</span>
              <span className="order-icon" aria-hidden="true">{piece ? pieceIcon(piece) : "◇"}</span>
              <button
                className="order-main"
                type="button"
                onClick={() => {
                  onSelect(value);
                  onFocusInterrupt?.(value);
                }}
              >
                <strong>{kind === "interrupt" ? humanize(rule?.id ?? value.split(".").at(-1) ?? value) : friendlyName(piece)}</strong>
                {kind === "interrupt" && (
                  <small>{rule?.afterSan ? "Exact" : rule?.required ? "Required" : "Conditional"}</small>
                )}
              </button>
              {destination && <code>{destination}</code>}
              <details className="overflow-menu order-overflow">
                <summary aria-label={`Reorder ${value}`}>⋮</summary>
                <div>
                  <button type="button" disabled={pending || index === 0} onClick={() => move(index, index - 1)}>Move earlier</button>
                  <button type="button" disabled={pending || index === values.length - 1} onClick={() => move(index, index + 1)}>Move later</button>
                  <button type="button" disabled={pending || index === 0} onClick={() => move(index, 0)}>Move to top</button>
                  <button type="button" disabled={pending || index === values.length - 1} onClick={() => move(index, values.length - 1)}>Move to bottom</button>
                </div>
              </details>
            </li>
          );
        })}
      </ol>
    </section>
  );
}

function DevelopmentEditor(
  props: Props & { piece: PieceScript; onClose: () => void },
) {
  const existing = props.piece.development;
  const [draft, setDraft] = useState<DevelopmentDraft>({
    alias: props.piece.alias,
    to: existing?.to ?? props.piece.currentSquare ?? "e4",
    requires: existing?.requires ?? [],
    when: existing?.when ?? null,
    why: existing?.why ?? "",
  });
  const [preview, setPreview] = useState<MutationPreview | null>(null);
  return (
    <section className="focused-editor" aria-label="Development editor">
      <EditorBack piece={props.piece} onClose={props.onClose} />
      <span className="eyebrow">{existing ? "Edit" : "Add"} development</span>
      <h2>Default development</h2>
      <label>Destination<input aria-label="Destination" maxLength={2} value={draft.to} onChange={(event) => setDraft({ ...draft, to: event.target.value })} /></label>
      <label>Prerequisites<input aria-label="Prerequisites" value={draft.requires.join(", ")} onChange={(event) => setDraft({ ...draft, requires: splitList(event.target.value) })} /></label>
      <ConditionBuilder value={draft.when} pieces={props.workspace.pieceScripts} onChange={(when) => setDraft({ ...draft, when })} />
      <label>Why<textarea aria-label="Why" required value={draft.why} onChange={(event) => setDraft({ ...draft, why: event.target.value })} /></label>
      {preview && <Review preview={preview} />}
      <div className="editor-actions">
        <button type="button" disabled={props.pending} onClick={() => void props.onPreviewDevelopment(draft).then(setPreview)}>Review</button>
        <button className="primary" type="button" disabled={!preview?.valid || props.pending} onClick={() => void props.onApplyDevelopment(draft).then(props.onClose)}>Apply</button>
        <button type="button" onClick={props.onClose}>Cancel</button>
      </div>
      {existing && (
        <button className="danger-link" type="button" disabled={props.pending} onClick={() => void props.onDeleteDevelopment(props.piece.alias).then(props.onClose)}>
          Delete development
        </button>
      )}
    </section>
  );
}

function InterruptEditor(
  props: Props & {
    piece: PieceScript;
    existing: InterruptRule | null;
    duplicate?: boolean;
    onClose: () => void;
  },
) {
  const source = props.existing;
  const isExisting = Boolean(source && !props.duplicate);
  const [draft, setDraft] = useState<InterruptDraft>({
    alias: props.piece.alias,
    id: isExisting ? source?.id ?? null : null,
    requires: source?.requires ?? [],
    afterSan: source?.afterSan ?? null,
    when: source?.when ?? null,
    required: source?.required ?? false,
    attempts: source
      ? source.attempts.map(attemptToDraft)
      : [{ move: props.piece.currentSquare ?? "e4" }],
    why: source?.why ?? "",
  });
  const [preview, setPreview] = useState<MutationPreview | null>(null);
  return (
    <section className="focused-editor" aria-label="Interrupt editor">
      <EditorBack piece={props.piece} onClose={props.onClose} />
      <span className="eyebrow">{isExisting ? "Edit" : "Add"} interrupt</span>
      <h2>{isExisting ? humanize(source?.id ?? "") : "New interrupt"}</h2>
      <label>
        Rule name
        <input aria-label="Rule name" value={draft.id ?? ""} placeholder="Generated from the explanation" onChange={(event) => setDraft({ ...draft, id: event.target.value || null })} />
      </label>
      <div className="exact-toggle">
        <label>
          <input
            type="checkbox"
            checked={draft.afterSan !== null}
            onChange={(event) => setDraft({
              ...draft,
              afterSan: event.target.checked
                ? props.workspace.position.historySan
                : null,
              when: event.target.checked ? null : draft.when,
            })}
          />
          Exact position
        </label>
        {draft.afterSan && <small>After {draft.afterSan.join(" ") || "start position"}</small>}
      </div>
      {!draft.afterSan && (
        <ConditionBuilder value={draft.when} pieces={props.workspace.pieceScripts} onChange={(when) => setDraft({ ...draft, when })} />
      )}
      <label className="required-toggle">
        <input type="checkbox" checked={draft.required} onChange={(event) => setDraft({ ...draft, required: event.target.checked })} />
        <span><strong>Required</strong><small>Stop if no attempt resolves.</small></span>
      </label>
      <AttemptEditor
        attempts={draft.attempts}
        pieces={props.workspace.pieceScripts}
        onChange={(attempts) => setDraft({ ...draft, attempts })}
      />
      <label>Prerequisites<input aria-label="Prerequisites" value={draft.requires.join(", ")} onChange={(event) => setDraft({ ...draft, requires: splitList(event.target.value) })} /></label>
      <label>Why<textarea aria-label="Why" required value={draft.why} onChange={(event) => setDraft({ ...draft, why: event.target.value })} /></label>
      {preview && <Review preview={preview} />}
      <div className="editor-actions">
        <button type="button" disabled={props.pending} onClick={() => void props.onPreviewInterrupt(draft).then(setPreview)}>Review</button>
        <button className="primary" type="button" disabled={!preview?.valid || props.pending} onClick={() => void props.onApplyInterrupt(draft).then(props.onClose)}>Apply</button>
        <button type="button" onClick={props.onClose}>Cancel</button>
      </div>
      {isExisting && source && (
        <button className="danger-link" type="button" disabled={props.pending} onClick={() => void props.onDeleteInterrupt(props.piece.alias, source.id).then(props.onClose)}>
          Delete interrupt
        </button>
      )}
    </section>
  );
}

function AttemptEditor({
  attempts,
  pieces,
  onChange,
}: {
  attempts: ActionAttemptDraft[];
  pieces: PieceScript[];
  onChange: (attempts: ActionAttemptDraft[]) => void;
}) {
  const [dragIndex, setDragIndex] = useState<number | null>(null);
  const replace = (index: number, attempt: ActionAttemptDraft) =>
    onChange(attempts.map((item, itemIndex) => itemIndex === index ? attempt : item));
  return (
    <fieldset className="attempt-editor">
      <legend>Ordered attempts</legend>
      {attempts.map((attempt, index) => {
        const kind = attempt.move ? "move" : attempt.captureType ? "captureType" : "capture";
        return (
          <div
            className="editor-attempt-row"
            key={index}
            draggable
            onDragStart={() => setDragIndex(index)}
            onDragOver={(event) => event.preventDefault()}
            onDrop={() => {
              if (dragIndex !== null) onChange(moveItem(attempts, dragIndex, index));
              setDragIndex(null);
            }}
          >
            <span className="drag-handle" aria-hidden="true">⠿</span>
            <select aria-label={`Attempt ${index + 1} type`} value={kind} onChange={(event) => replace(index, event.target.value === "move" ? { move: "e4" } : event.target.value === "captureType" ? { captureType: "bishop" } : { capture: "attacker" })}>
              <option value="move">Move</option>
              <option value="capture">Capture</option>
              <option value="captureType">Capture type</option>
            </select>
            {kind === "move" && <input aria-label={`Attempt ${index + 1} square`} value={attempt.move} onChange={(event) => replace(index, { move: event.target.value })} />}
            {kind === "capture" && (
              <select aria-label={`Attempt ${index + 1} target`} value={attempt.capture} onChange={(event) => replace(index, { capture: event.target.value })}>
                <option value="attacker">Triggering attacker</option>
                {pieces.filter((piece) => !piece.authorable).map((piece) => <option key={piece.alias} value={piece.alias}>{friendlyName(piece)}</option>)}
              </select>
            )}
            {kind === "captureType" && (
              <select aria-label="Capture type" value={attempt.captureType} onChange={(event) => replace(index, { captureType: event.target.value as ActionAttemptDraft["captureType"] })}>
                {["pawn", "knight", "bishop", "rook", "queen", "king"].map((type) => <option key={type}>{type}</option>)}
              </select>
            )}
            <button type="button" aria-label={`Remove attempt ${index + 1}`} disabled={attempts.length === 1} onClick={() => onChange(attempts.filter((_, itemIndex) => itemIndex !== index))}>×</button>
          </div>
        );
      })}
      <button className="compact-add" type="button" onClick={() => onChange([...attempts, { move: "e4" }])}>+ Add attempt</button>
    </fieldset>
  );
}

function Review({ preview }: { preview: MutationPreview }) {
  return (
    <section className={`compact-review ${preview.valid ? "valid" : "invalid"}`} aria-label="Review change">
      <strong>{preview.valid ? "Ready to apply" : "Validation failed"}</strong>
      <dl>
        <div><dt>Current</dt><dd>{preview.currentDecision ?? "None"}</dd></div>
        <div><dt>Preview</dt><dd>{preview.previewDecision ?? "None"}</dd></div>
      </dl>
      {preview.errors.map((error) => <p className="inline-error" key={error}>{error}</p>)}
      {preview.warnings.map((warning) => <p key={warning}>{warning}</p>)}
    </section>
  );
}

function EditorBack({ piece, onClose }: { piece: PieceScript; onClose: () => void }) {
  return (
    <button className="editor-back" type="button" onClick={onClose}>
      ← {friendlyName(piece)}
    </button>
  );
}

function StatusBadge({ value }: { value: string }) {
  return <span className={`compact-badge badge-${value.toLowerCase().replaceAll(" ", "-")}`}>{humanize(value)}</span>;
}

function pieceIcon(piece: PieceScript) {
  const color = piece.ref.includes(":black:") ? "black" : "white";
  const type = piece.ref.split(":")[2] ?? "pawn";
  const icons: Record<string, Record<string, string>> = {
    white: { pawn: "♙", knight: "♘", bishop: "♗", rook: "♖", queen: "♕", king: "♔" },
    black: { pawn: "♟", knight: "♞", bishop: "♝", rook: "♜", queen: "♛", king: "♚" },
  };
  return icons[color]?.[type] ?? "◇";
}

function friendlyName(piece?: PieceScript | null) {
  if (!piece) return "Unknown piece";
  return humanize(piece.label.replace(/^(White|Black)\s+/i, ""));
}

function formatState(value: string) {
  return humanize(value);
}

function humanize(value: string) {
  return value.replaceAll("-", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function splitList(value: string) {
  return value.split(",").map((item) => item.trim()).filter(Boolean);
}

function moveItem<T>(items: T[], from: number, to: number): T[] {
  const next = [...items];
  const [item] = next.splice(from, 1);
  next.splice(to, 0, item);
  return next;
}

function attemptToDraft(attempt: InterruptRule["attempts"][number]): ActionAttemptDraft {
  if (attempt.kind === "move") return { move: attempt.value };
  if (attempt.kind === "capture-type") {
    return { captureType: attempt.value as ActionAttemptDraft["captureType"] };
  }
  return {
    capture: attempt.kind === "capture-attacker" ? "attacker" : attempt.value,
  };
}
