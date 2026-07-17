import { type FormEvent, type ReactNode, useState } from "react";

import { workspaceApi, type FlowSourceResponse } from "../api/client";
import type {
  OverrideUpdate,
  PolicyItemSnapshot,
  RuleRuntimeSnapshot,
  RuleUpdate,
  StructureRuntimeSnapshot,
  StructureUpdate,
  WorkspaceSnapshot,
} from "../types/workspace";

interface Props {
  workspace: WorkspaceSnapshot;
  pending: boolean;
  onUpdateRule: (id: string, update: RuleUpdate) => void;
  onUpdateOverride: (id: string, update: OverrideUpdate) => void;
  onReorderPolicy: (
    section: "response" | "development" | "continuation",
    itemIds: string[],
  ) => void;
  onUpdateStructure: (id: string, update: StructureUpdate) => void;
  onReorderStructures: (structureIds: string[]) => void;
  onBack: () => void;
  onRestart: () => void;
  inspector: ReactNode;
}

export function RuleStatusPanel({ workspace, pending, onUpdateRule, onUpdateOverride, onReorderPolicy, onUpdateStructure, onReorderStructures, onBack, onRestart, inspector }: Props) {
  const [editing, setEditing] = useState<string | null>(null);
  const [editingStructure, setEditingStructure] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"status" | "toml">("status");
  const [flowSource, setFlowSource] = useState<FlowSourceResponse | null>(null);
  const [sourceLoading, setSourceLoading] = useState(false);
  const [sourceError, setSourceError] = useState<string | null>(null);

  const loadToml = async () => {
    setActiveTab("toml");
    setSourceLoading(true);
    setSourceError(null);
    try { setFlowSource(await workspaceApi.getFlowSource(workspace.sessionId)); }
    catch (error) { setSourceError(error instanceof Error ? error.message : "Could not load the flow TOML."); }
    finally { setSourceLoading(false); }
  };

  const groups: Array<[string, "response" | "development" | "continuation", RuleRuntimeSnapshot[]]> = [
    ["Responses", "response", workspace.rules.responses],
    ["Development", "development", workspace.rules.development],
    ["Continuations", "continuation", workspace.rules.continuations],
  ];
  const moveItem = (
    section: "response" | "development" | "continuation",
    items: RuleRuntimeSnapshot[],
    index: number,
    direction: -1 | 1,
  ) => {
    const destination = index + direction;
    if (destination < 0 || destination >= items.length) return;
    const next = [...items];
    [next[index], next[destination]] = [next[destination], next[index]];
    onReorderPolicy(section, next.map((item) => item.id));
  };

  return (
    <aside className="workspace-panel rules-panel" aria-labelledby="rules-heading">
      <div className="rule-status-scroll development-left-scroll">
        {inspector}
        <section className="structure-panel" aria-labelledby="structure-heading">
          <span className="eyebrow" id="structure-heading">Structure</span>
          {workspace.rules.structures.length ? workspace.rules.structures.map((structure, index) => (
            <details className={`rule-card structure-${structure.status}`} key={structure.id} open={structure.status === "selected" || structure.status === "available"}>
              <summary><strong>{structure.name}</strong><span className="rule-state">{structure.status}</span></summary>
              {editingStructure === structure.id ? (
                <StructureEditor
                  structure={structure}
                  pending={pending}
                  onCancel={() => setEditingStructure(null)}
                  onSave={(update) => {
                    setEditingStructure(null);
                    onUpdateStructure(structure.id, update);
                  }}
                />
              ) : (
                <>
                  <p>{structure.note ?? structure.reason}</p>
                  <p className="rule-after">{structure.reason}</p>
                  <ConditionLine label="Available" condition={structure.availableWhen} fallback="" />
                  <ConditionLine label="Select" condition={structure.selectedWhen} fallback="" />
                  <div className="button-row">
                    <button onClick={() => setEditingStructure(structure.id)} disabled={pending}>Edit structure</button>
                    <button aria-label={`Move ${structure.name} earlier`} disabled={pending || index === 0} onClick={() => onReorderStructures(moveId(workspace.rules.structures, index, -1))}>↑</button>
                    <button aria-label={`Move ${structure.name} later`} disabled={pending || index === workspace.rules.structures.length - 1} onClick={() => onReorderStructures(moveId(workspace.rules.structures, index, 1))}>↓</button>
                  </div>
                </>
              )}
            </details>
          )) : <p className="muted">This flow has no structure alternatives.</p>}
        </section>
        <section className="current-decision-compact" aria-labelledby="current-decision-heading">
          <span className="eyebrow" id="current-decision-heading">Current decision</span>
          {workspace.decision ? (
            <>
              <strong>{workspace.decision.moveSan ?? "Flow frontier"}</strong>
              <span>{workspace.decision.sourceId ?? workspace.decision.source}</span>
              {workspace.decision.note && <p>{workspace.decision.note}</p>}
            </>
          ) : <p className="muted">No controlled-side decision on this turn.</p>}
        </section>
      <div className="section-heading-row">
        <h2 id="rules-heading">Policy order</h2>
        <span className="status-chip">{workspace.flow.policyModel}</span>
      </div>
      {workspace.flow.warnings.length > 0 && (
        <details className="validation-warning">
          <summary>Flow warnings <span>{workspace.flow.warnings.length}</span></summary>
          <ul>{workspace.flow.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul>
        </details>
      )}
      <div className="rules-tabs" role="tablist" aria-label="Rule panel views">
        <button id="rule-status-tab" role="tab" aria-selected={activeTab === "status"} aria-controls="rule-status-panel" className={activeTab === "status" ? "active" : ""} onClick={() => setActiveTab("status")}>Rules</button>
        <button id="rule-toml-tab" role="tab" aria-selected={activeTab === "toml"} aria-controls="rule-toml-panel" className={activeTab === "toml" ? "active" : ""} onClick={() => void loadToml()}>TOML</button>
      </div>
      {activeTab === "status" ? (
        <div id="rule-status-panel" role="tabpanel" aria-labelledby="rule-status-tab">
          {groups.map(([title, section, items]) => (
            <RuleGroup key={title} title={title} count={items.length} open={items.length > 0}>
              {items.map((item, index) => <PolicyCard key={keyFor(item)} item={item} pending={pending} editing={editing === keyFor(item)} onEdit={() => setEditing(keyFor(item))} onCancel={() => setEditing(null)} onUpdateRule={onUpdateRule} onUpdateOverride={onUpdateOverride} onEarlier={() => moveItem(section, items, index, -1)} onLater={() => moveItem(section, items, index, 1)} canMoveEarlier={index > 0} canMoveLater={index < items.length - 1} />)}
            </RuleGroup>
          ))}
          <RuleGroup title="Exact overrides" count={workspace.rules.overrides.length}>
            {workspace.rules.overrides.map((item) => <PolicyCard key={keyFor(item)} item={item} pending={pending} editing={editing === keyFor(item)} onEdit={() => setEditing(keyFor(item))} onCancel={() => setEditing(null)} onUpdateRule={onUpdateRule} onUpdateOverride={onUpdateOverride} />)}
          </RuleGroup>
          <div className="rules-line-summary"><span className="eyebrow">Current line</span><p>{workspace.position.historySan.join(" ") || "Starting position"}</p></div>
        </div>
      ) : (
        <div id="rule-toml-panel" role="tabpanel" aria-labelledby="rule-toml-tab" className="toml-panel">
          <div className="toml-toolbar"><span>{flowSource?.path ?? workspace.flow.path}</span><button onClick={() => void loadToml()} disabled={sourceLoading}>Refresh</button></div>
          {sourceLoading && !flowSource && <p className="muted">Loading TOML…</p>}
          {sourceError && <p className="inline-error" role="alert">{sourceError}</p>}
          {flowSource && <pre aria-label="Flow TOML source"><code>{flowSource.content}</code></pre>}
        </div>
      )}
      </div>
      <div className="button-row rules-navigation">
        <button onClick={onBack} disabled={pending || !workspace.navigation.canBack}>Back</button>
        <button onClick={onRestart} disabled={pending || !workspace.navigation.canRestart}>Restart</button>
      </div>
    </aside>
  );
}

function RuleGroup({ title, count, open = false, children }: { title: string; count: number; open?: boolean; children: React.ReactNode }) {
  return <details className="rule-group" open={open}><summary><span>{title}</span><span className="rule-count">{count}</span></summary><div className="rule-group-body">{children}</div></details>;
}

function StructureEditor({
  structure,
  pending,
  onCancel,
  onSave,
}: {
  structure: StructureRuntimeSnapshot;
  pending: boolean;
  onCancel: () => void;
  onSave: (update: StructureUpdate) => void;
}) {
  const [name, setName] = useState(structure.name);
  const [note, setNote] = useState(structure.note ?? "");
  const [available, setAvailable] = useState(JSON.stringify(structure.availableWhen.expression, null, 2));
  const [selected, setSelected] = useState(JSON.stringify(structure.selectedWhen.expression, null, 2));
  const [error, setError] = useState<string | null>(null);
  const submit = (event: FormEvent) => {
    event.preventDefault();
    try {
      const availableWhen = parseObject(available, "Availability");
      const selectedWhen = parseObject(selected, "Selection");
      if (!availableWhen || !selectedWhen) throw new Error("Both structure conditions are required.");
      onSave({ name: name.trim(), note: note.trim() || null, availableWhen, selectedWhen });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Invalid structure.");
    }
  };
  return (
    <form className="rule-edit-form" onSubmit={submit}>
      <label>Name<input value={name} onChange={(event) => setName(event.target.value)} required /></label>
      <label>Available when (JSON)<textarea value={available} onChange={(event) => setAvailable(event.target.value)} rows={4} required /></label>
      <label>Selected when (JSON)<textarea value={selected} onChange={(event) => setSelected(event.target.value)} rows={4} required /></label>
      <label>Note<textarea value={note} onChange={(event) => setNote(event.target.value)} rows={2} /></label>
      {error && <p className="inline-error" role="alert">{error}</p>}
      <div className="button-row"><button className="primary" type="submit" disabled={pending}>Save</button><button type="button" onClick={onCancel} disabled={pending}>Cancel</button></div>
    </form>
  );
}

function PolicyCard({ item, pending, editing, onEdit, onCancel, onUpdateRule, onUpdateOverride, onEarlier, onLater, canMoveEarlier, canMoveLater }: {
  item: PolicyItemSnapshot; pending: boolean; editing: boolean; onEdit: () => void; onCancel: () => void;
  onUpdateRule: (id: string, update: RuleUpdate) => void; onUpdateOverride: (id: string, update: OverrideUpdate) => void;
  onEarlier?: () => void; onLater?: () => void;
  canMoveEarlier?: boolean; canMoveLater?: boolean;
}) {
  return (
    <section className={`rule-card rule-card-${item.selected ? "selected" : item.kind === "rule" ? item.status : item.matched ? "active" : "dormant"}`}>
      <div className="rule-card-heading"><span className="rule-kind">{item.id}</span><span className="rule-state">{item.kind === "rule" ? item.status : item.selected ? "selected" : item.matched ? "matched" : "override"}</span></div>
      {editing ? <PolicyEditor item={item} pending={pending} onCancel={onCancel} onUpdateRule={(update) => { onCancel(); onUpdateRule(item.id, update); }} onUpdateOverride={(update) => { onCancel(); onUpdateOverride(item.id, update); }} /> : <>
        <strong className="rule-move">{item.moveSan ?? `${item.piece} → ${item.destination}`}</strong>
        {item.kind === "rule" && <span className="rule-step">{item.section} #{item.order} · {item.lifecycle}{item.structures.length ? ` · ${item.structures.join(", ")}` : " · global"}</span>}
        <p>{item.note ?? "No reason recorded."}</p>
        <p className="rule-after">{item.reason}</p>
        {item.kind === "exact-override" && <p className="rule-after">After: {item.afterSan.join(" ") || "starting position"}</p>}
        {item.kind === "rule" && <RuleDiagnostics item={item} />}
        {item.kind === "rule" && (
          <div className="order-actions" aria-label={`Order ${item.id}`}>
            <button aria-label={`Move ${item.id} earlier`} onClick={onEarlier} disabled={pending || !canMoveEarlier}>↑</button>
            <button aria-label={`Move ${item.id} later`} onClick={onLater} disabled={pending || !canMoveLater}>↓</button>
          </div>
        )}
        {item.kind !== "rule" || item.section !== "development" ? (
          <button className="rule-edit-button" onClick={onEdit} disabled={pending}>Edit {item.kind === "rule" ? "rule" : "override"}</button>
        ) : <span className="rule-edit-disabled">Edit this development rule from its piece inspector.</span>}
      </>}
    </section>
  );
}

function RuleDiagnostics({ item }: { item: RuleRuntimeSnapshot }) {
  return <details className="rule-diagnostics"><summary>Conditions and lifecycle</summary>
    <p>Action: {item.piece} → {item.destination}{item.moveUci ? ` (${item.moveUci})` : ""}</p>
    <ConditionLine label="Unlock" condition={item.unlockWhen} fallback="Unlocked from start" />
    <ConditionLine label="When" condition={item.when} fallback="No live condition" />
    <ConditionLine label="Expire" condition={item.expireWhen} fallback="On execution only" />
    <p>Unlocked: {item.unlockedAtPly === null ? "not yet" : `ply ${item.unlockedAtPly}`} · Retired: {item.retiredAtPly === null ? "not yet" : `ply ${item.retiredAtPly}`}</p>
  </details>;
}

function ConditionLine({ label, condition, fallback }: { label: string; condition: RuleRuntimeSnapshot["unlockWhen"]; fallback: string }) {
  if (!condition) return <p>{label}: {fallback}</p>;
  return <p>{label}: <strong>{condition.value ? "true" : "false"}</strong> · {condition.explanation}</p>;
}

function PolicyEditor({ item, pending, onCancel, onUpdateRule, onUpdateOverride }: {
  item: PolicyItemSnapshot; pending: boolean; onCancel: () => void;
  onUpdateRule: (update: RuleUpdate) => void; onUpdateOverride: (update: OverrideUpdate) => void;
}) {
  const [piece, setPiece] = useState(item.piece);
  const [destination, setDestination] = useState(item.destination);
  const [note, setNote] = useState(item.note ?? "");
  const [structures, setStructures] = useState(item.kind === "rule" ? item.structures.join(", ") : "");
  const [unlock, setUnlock] = useState(item.kind === "rule" && item.unlockWhen ? JSON.stringify(item.unlockWhen.expression, null, 2) : "");
  const [live, setLive] = useState(item.kind === "rule" && item.when ? JSON.stringify(item.when.expression, null, 2) : "");
  const [expire, setExpire] = useState(item.kind === "rule" && item.expireWhen ? JSON.stringify(item.expireWhen.expression, null, 2) : "");
  const [after, setAfter] = useState(item.kind === "exact-override" ? JSON.stringify(item.afterSan) : "");
  const [error, setError] = useState<string | null>(null);
  const submit = (event: FormEvent) => {
    event.preventDefault();
    try {
      if (item.kind === "rule") {
        onUpdateRule({
          note: note.trim() || null,
          structures: structures.split(",").map((value) => value.trim()).filter(Boolean),
          move: { piece: piece.trim(), to: destination.trim() },
          unlockWhen: parseObject(unlock, "Unlock"),
          when: parseObject(live, "Live condition"),
          expireWhen: parseObject(expire, "Expiration"),
        });
      } else {
        const history: unknown = JSON.parse(after);
        if (!Array.isArray(history) || !history.every((move) => typeof move === "string")) throw new Error("After must be a JSON array of SAN strings.");
        onUpdateOverride({ afterSan: history, note: note.trim() || null, move: { piece: piece.trim(), to: destination.trim() } });
      }
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Invalid editor value."); }
  };
  return <form className="rule-edit-form" onSubmit={submit}>
    <label>Original piece ID<input value={piece} onChange={(event) => setPiece(event.target.value)} required /></label>
    <label>Destination<input value={destination} onChange={(event) => setDestination(event.target.value)} minLength={2} maxLength={2} required /></label>
    <label>Reason / note<textarea value={note} onChange={(event) => setNote(event.target.value)} rows={2} /></label>
    {item.kind === "rule" ? <>
      <label>Structure scopes (comma separated)<input value={structures} onChange={(event) => setStructures(event.target.value)} /></label>
      <label>Unlock when (JSON)<textarea value={unlock} onChange={(event) => setUnlock(event.target.value)} rows={3} placeholder='{"last_move":{"piece":"piece:black:pawn:c","to":"c5"}}' /></label>
      <label>When (JSON)<textarea value={live} onChange={(event) => setLive(event.target.value)} rows={3} placeholder='{"attacked":"piece:white:bishop:queenside"}' /></label>
      <label>Expire when (JSON)<textarea value={expire} onChange={(event) => setExpire(event.target.value)} rows={3} placeholder='{"captured":"piece:white:bishop:queenside"}' /></label>
    </> : <label>Exact SAN prefix (JSON)<textarea value={after} onChange={(event) => setAfter(event.target.value)} rows={4} required /></label>}
    {error && <p className="inline-error" role="alert">{error}</p>}
    <div className="button-row"><button className="primary" type="submit" disabled={pending}>Save</button><button type="button" onClick={onCancel} disabled={pending}>Cancel</button></div>
  </form>;
}

function parseObject(value: string, label: string): Record<string, unknown> | null {
  if (!value.trim()) return null;
  const parsed: unknown = JSON.parse(value);
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error(`${label} must be a JSON object.`);
  return parsed as Record<string, unknown>;
}

function keyFor(item: PolicyItemSnapshot): string { return `${item.kind}:${item.id}`; }

function moveId(
  items: StructureRuntimeSnapshot[],
  index: number,
  direction: -1 | 1,
): string[] {
  const next = [...items];
  const destination = index + direction;
  if (destination < 0 || destination >= next.length) return next.map((item) => item.id);
  [next[index], next[destination]] = [next[destination], next[index]];
  return next.map((item) => item.id);
}
