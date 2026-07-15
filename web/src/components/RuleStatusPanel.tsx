import { type FormEvent, useState } from "react";

import { workspaceApi, type FlowSourceResponse } from "../api/client";
import type { ApplicableRuleSnapshot, WorkspaceSnapshot } from "../types/workspace";

interface RuleStatusPanelProps {
  workspace: WorkspaceSnapshot;
  pending: boolean;
  onUpdateRule: (
    ruleId: string,
    kind: ApplicableRuleSnapshot["kind"],
    moveSan: string,
    note: string | null,
  ) => void;
  onBack: () => void;
  onRestart: () => void;
}

export function RuleStatusPanel({
  workspace,
  pending,
  onUpdateRule,
  onBack,
  onRestart,
}: RuleStatusPanelProps) {
  const rules = workspace.rules.applicable ?? [];
  const [editingId, setEditingId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"status" | "toml">("status");
  const [flowSource, setFlowSource] = useState<FlowSourceResponse | null>(null);
  const [sourceLoading, setSourceLoading] = useState(false);
  const [sourceError, setSourceError] = useState<string | null>(null);

  const loadToml = async () => {
    setActiveTab("toml");
    setSourceLoading(true);
    setSourceError(null);
    try {
      setFlowSource(await workspaceApi.getFlowSource(workspace.sessionId));
    } catch (error) {
      setSourceError(error instanceof Error ? error.message : "Could not load the flow TOML.");
    } finally {
      setSourceLoading(false);
    }
  };

  return (
    <aside className="workspace-panel rules-panel" aria-labelledby="rules-heading">
      <div className="section-heading-row">
        <h2 id="rules-heading">Rule status</h2>
        <span className="status-chip">{ruleContext(workspace)}</span>
      </div>
      <div className="rules-tabs" role="tablist" aria-label="Rule panel views">
        <button
          id="rule-status-tab"
          role="tab"
          aria-selected={activeTab === "status"}
          aria-controls="rule-status-panel"
          className={activeTab === "status" ? "active" : ""}
          onClick={() => setActiveTab("status")}
        >
          Rules
        </button>
        <button
          id="rule-toml-tab"
          role="tab"
          aria-selected={activeTab === "toml"}
          aria-controls="rule-toml-panel"
          className={activeTab === "toml" ? "active" : ""}
          onClick={() => void loadToml()}
        >
          TOML
        </button>
      </div>
      {activeTab === "status" ? (
        <div id="rule-status-panel" role="tabpanel" aria-labelledby="rule-status-tab">
          <p className="rules-intro">Rules that apply to the board’s current decision.</p>
          <div className="applicable-rules">
            {rules.length ? rules.map((rule) => (
              <RuleCard
                key={`${rule.kind}:${rule.id}:${rule.moveSan}:${rule.note ?? ""}`}
                rule={rule}
                pending={pending}
                editing={editingId === rule.id}
                onEdit={() => setEditingId(rule.id)}
                onCancel={() => setEditingId(null)}
                onSave={(moveSan, note) => {
                  setEditingId(null);
                  onUpdateRule(rule.id, rule.kind, moveSan, note);
                }}
              />
            )) : (
              <div className="empty-rule-state">
                <strong>No saved rule applies here</strong>
                <p>Add a rule in the TUI or directly in the flow TOML.</p>
              </div>
            )}
          </div>
          <div className="rules-line-summary">
            <span className="eyebrow">Current line</span>
            <p>{workspace.position.historySan.join(" ") || "Starting position"}</p>
          </div>
        </div>
      ) : (
        <div id="rule-toml-panel" role="tabpanel" aria-labelledby="rule-toml-tab" className="toml-panel">
          <div className="toml-toolbar">
            <span>{flowSource?.path ?? workspace.flow.path}</span>
            <button onClick={() => void loadToml()} disabled={sourceLoading}>
              Refresh
            </button>
          </div>
          {sourceLoading && !flowSource && <p className="muted">Loading TOML…</p>}
          {sourceError && <p className="inline-error" role="alert">{sourceError}</p>}
          {flowSource && <pre aria-label="Flow TOML source"><code>{flowSource.content}</code></pre>}
        </div>
      )}
      <div className="button-row rules-navigation">
        <button onClick={onBack} disabled={pending || !workspace.navigation.canBack}>Back</button>
        <button onClick={onRestart} disabled={pending || !workspace.navigation.canRestart}>Restart</button>
      </div>
    </aside>
  );
}

function RuleCard({
  rule,
  pending,
  editing,
  onEdit,
  onCancel,
  onSave,
}: {
  rule: ApplicableRuleSnapshot;
  pending: boolean;
  editing: boolean;
  onEdit: () => void;
  onCancel: () => void;
  onSave: (moveSan: string, note: string | null) => void;
}) {
  const [moveSan, setMoveSan] = useState(rule.moveSan);
  const [note, setNote] = useState(rule.note ?? "");

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    onSave(moveSan, note.trim() || null);
  };

  return (
    <section className={`rule-card rule-card-${rule.status}`}>
      <div className="rule-card-heading">
        <span className="rule-kind">{rule.kind.replace("-", " ")}</span>
        <span className={`rule-state rule-state-${rule.status}`}>{rule.status}</span>
      </div>
      {editing ? (
        <form className="rule-edit-form" onSubmit={submit}>
          <label>
            Move in SAN
            <input value={moveSan} onChange={(event) => setMoveSan(event.target.value)} required />
          </label>
          <label>
            Reason / note
            <textarea value={note} onChange={(event) => setNote(event.target.value)} rows={3} />
          </label>
          <div className="button-row">
            <button className="primary" type="submit" disabled={pending}>Save rule</button>
            <button type="button" onClick={onCancel} disabled={pending}>Cancel</button>
          </div>
        </form>
      ) : (
        <>
          <strong className="rule-move">{rule.moveSan}</strong>
          <span className="rule-step">Step {rule.step}</span>
          <p>{rule.note ?? "No reason recorded."}</p>
          {rule.afterSan.length > 0 && <p className="rule-after">After: {rule.afterSan.join(" ")}</p>}
          {rule.editable ? (
            <button className="rule-edit-button" onClick={onEdit} disabled={pending}>Edit rule</button>
          ) : (
            <span className="rule-edit-disabled">Resolve the current result before editing.</span>
          )}
        </>
      )}
    </section>
  );
}

function ruleContext(workspace: WorkspaceSnapshot): string {
  if (workspace.phase === "black-ready") return "Black replies";
  if (workspace.decision) return `White step ${workspace.decision.step}`;
  return workspace.phase.replaceAll("-", " ");
}
