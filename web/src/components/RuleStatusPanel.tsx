import { type FormEvent, type ReactNode, useState } from "react";

import { workspaceApi, type FlowSourceResponse } from "../api/client";
import type {
  OverrideUpdate,
  PolicyItemSnapshot,
  RuleRuntimeSnapshot,
  RuleUpdate,
  WorkspaceSnapshot,
} from "../types/workspace";

interface Props {
  workspace: WorkspaceSnapshot;
  pending: boolean;
  onUpdateRule: (id: string, update: RuleUpdate) => void;
  onUpdateOverride: (id: string, update: OverrideUpdate) => void;
  onBack: () => void;
  onRestart: () => void;
  inspector: ReactNode;
}

export function RuleStatusPanel({ workspace, pending, onUpdateRule, onUpdateOverride, onBack, onRestart, inspector }: Props) {
  const [editing, setEditing] = useState<string | null>(null);
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

  const selected = workspace.rules.selected;
  const groups: Array<[string, RuleRuntimeSnapshot[]]> = [
    ["Applies now", workspace.rules.appliesNow],
    ["Active · waiting", workspace.rules.waiting],
    ["Dormant", workspace.rules.dormant],
    ["Retired", workspace.rules.retired],
    ["Disabled", workspace.rules.disabled],
  ];
  const otherOverrides = workspace.rules.overrides.filter((item) => !item.selected);

  return (
    <aside className="workspace-panel rules-panel" aria-labelledby="rules-heading">
      <div className="rule-status-scroll development-left-scroll">
        {inspector}
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
        <h2 id="rules-heading">Rule status</h2>
        <span className="status-chip">{workspace.flow.policyModel}</span>
      </div>
      <div className="rules-tabs" role="tablist" aria-label="Rule panel views">
        <button id="rule-status-tab" role="tab" aria-selected={activeTab === "status"} aria-controls="rule-status-panel" className={activeTab === "status" ? "active" : ""} onClick={() => setActiveTab("status")}>Rules</button>
        <button id="rule-toml-tab" role="tab" aria-selected={activeTab === "toml"} aria-controls="rule-toml-panel" className={activeTab === "toml" ? "active" : ""} onClick={() => void loadToml()}>TOML</button>
      </div>
      {activeTab === "status" ? (
        <div id="rule-status-panel" role="tabpanel" aria-labelledby="rule-status-tab">
          <RuleGroup title="Selected" count={selected ? 1 : 0} open>
            {selected ? <PolicyCard item={selected} pending={pending} editing={editing === keyFor(selected)} onEdit={() => setEditing(keyFor(selected))} onCancel={() => setEditing(null)} onUpdateRule={onUpdateRule} onUpdateOverride={onUpdateOverride} /> : <p className="muted">No policy action is selected.</p>}
          </RuleGroup>
          {groups.map(([title, items]) => (
            <RuleGroup key={title} title={title} count={items.length} open={items.length > 0 && title === "Applies now"}>
              {items.map((item) => <PolicyCard key={keyFor(item)} item={item} pending={pending} editing={editing === keyFor(item)} onEdit={() => setEditing(keyFor(item))} onCancel={() => setEditing(null)} onUpdateRule={onUpdateRule} onUpdateOverride={onUpdateOverride} />)}
            </RuleGroup>
          ))}
          <RuleGroup title="Exact overrides" count={otherOverrides.length}>
            {otherOverrides.map((item) => <PolicyCard key={keyFor(item)} item={item} pending={pending} editing={editing === keyFor(item)} onEdit={() => setEditing(keyFor(item))} onCancel={() => setEditing(null)} onUpdateRule={onUpdateRule} onUpdateOverride={onUpdateOverride} />)}
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

function PolicyCard({ item, pending, editing, onEdit, onCancel, onUpdateRule, onUpdateOverride }: {
  item: PolicyItemSnapshot; pending: boolean; editing: boolean; onEdit: () => void; onCancel: () => void;
  onUpdateRule: (id: string, update: RuleUpdate) => void; onUpdateOverride: (id: string, update: OverrideUpdate) => void;
}) {
  return (
    <section className={`rule-card rule-card-${item.selected ? "selected" : item.kind === "rule" ? item.status : item.matched ? "active" : "dormant"}`}>
      <div className="rule-card-heading"><span className="rule-kind">{item.id}</span><span className="rule-state">{item.kind === "rule" ? item.status : item.selected ? "selected" : item.matched ? "matched" : "override"}</span></div>
      {editing ? <PolicyEditor item={item} pending={pending} onCancel={onCancel} onUpdateRule={(update) => { onCancel(); onUpdateRule(item.id, update); }} onUpdateOverride={(update) => { onCancel(); onUpdateOverride(item.id, update); }} /> : <>
        <strong className="rule-move">{item.moveSan ?? `${item.piece} → ${item.destination}`}</strong>
        {item.kind === "rule" && <span className="rule-step">Priority {item.priority} · {item.lifecycle}</span>}
        <p>{item.note ?? "No reason recorded."}</p>
        <p className="rule-after">{item.reason}</p>
        {item.kind === "exact-override" && <p className="rule-after">After: {item.afterSan.join(" ") || "starting position"}</p>}
        {item.kind === "rule" && <RuleDiagnostics item={item} />}
        {item.kind !== "rule" || item.authoredKind === "generic" ? (
          <button className="rule-edit-button" onClick={onEdit} disabled={pending}>Edit {item.kind === "rule" ? "rule" : "override"}</button>
        ) : <span className="rule-edit-disabled">Edit this development rule from its piece inspector.</span>}
      </>}
    </section>
  );
}

function RuleDiagnostics({ item }: { item: RuleRuntimeSnapshot }) {
  return <details className="rule-diagnostics"><summary>Conditions and lifecycle</summary>
    <p>Action: {item.piece} → {item.destination}{item.moveUci ? ` (${item.moveUci})` : ""}</p>
    <ConditionLine label="Activate" condition={item.activateWhen} fallback="Active from start" />
    <ConditionLine label="Retire" condition={item.retireWhen} fallback="On execution" />
    <p>Activated: {item.activatedAtPly === null ? "not yet" : `ply ${item.activatedAtPly}`} · Retired: {item.retiredAtPly === null ? "not yet" : `ply ${item.retiredAtPly}`}</p>
  </details>;
}

function ConditionLine({ label, condition, fallback }: { label: string; condition: RuleRuntimeSnapshot["activateWhen"]; fallback: string }) {
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
  const [enabled, setEnabled] = useState(item.enabled);
  const [priority, setPriority] = useState(item.kind === "rule" ? String(item.priority) : "");
  const [activate, setActivate] = useState(item.kind === "rule" && item.activateWhen ? JSON.stringify(item.activateWhen.expression, null, 2) : "");
  const [retire, setRetire] = useState(item.kind === "rule" && item.retireWhen ? JSON.stringify(item.retireWhen.expression, null, 2) : "");
  const [after, setAfter] = useState(item.kind === "exact-override" ? JSON.stringify(item.afterSan) : "");
  const [error, setError] = useState<string | null>(null);
  const submit = (event: FormEvent) => {
    event.preventDefault();
    try {
      if (item.kind === "rule") {
        const parsedPriority = Number(priority);
        if (!Number.isInteger(parsedPriority)) throw new Error("Priority must be an integer.");
        onUpdateRule({ priority: parsedPriority, enabled, note: note.trim() || null, move: { piece: piece.trim(), to: destination.trim() }, activateWhen: parseObject(activate, "Activation"), retireWhen: parseObject(retire, "Retirement") });
      } else {
        const history: unknown = JSON.parse(after);
        if (!Array.isArray(history) || !history.every((move) => typeof move === "string")) throw new Error("After must be a JSON array of SAN strings.");
        onUpdateOverride({ afterSan: history, enabled, note: note.trim() || null, move: { piece: piece.trim(), to: destination.trim() } });
      }
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Invalid editor value."); }
  };
  return <form className="rule-edit-form" onSubmit={submit}>
    <label className="checkbox-label"><input type="checkbox" checked={enabled} onChange={(event) => setEnabled(event.target.checked)} /> Enabled</label>
    {item.kind === "rule" && <label>Priority<input type="number" value={priority} onChange={(event) => setPriority(event.target.value)} required /></label>}
    <label>Original piece ID<input value={piece} onChange={(event) => setPiece(event.target.value)} required /></label>
    <label>Destination<input value={destination} onChange={(event) => setDestination(event.target.value)} minLength={2} maxLength={2} required /></label>
    <label>Reason / note<textarea value={note} onChange={(event) => setNote(event.target.value)} rows={2} /></label>
    {item.kind === "rule" ? <>
      <label>Activation condition (JSON)<textarea value={activate} onChange={(event) => setActivate(event.target.value)} rows={4} placeholder='{"moved":"piece:white:pawn:d"}' /></label>
      <label>Retirement condition (JSON)<textarea value={retire} onChange={(event) => setRetire(event.target.value)} rows={4} placeholder='{"moved":"piece:white:bishop:queenside"}' /></label>
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
