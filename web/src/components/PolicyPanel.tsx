import type { WorkspaceSnapshot } from "../types/workspace";

export function PolicyPanel({ workspace }: { workspace: WorkspaceSnapshot }) {
  const decision = workspace.decision;
  return (
    <aside className="workspace-panel policy-panel" aria-labelledby="policy-heading">
      <div className="section-heading-row">
        <h2 id="policy-heading">Policy</h2>
        <span className="status-chip">legacy v1</span>
      </div>
      {decision ? (
        <section className="decision-card">
          <span className="eyebrow">Current recommendation</span>
          <strong className="expected-move">{decision.moveSan ?? "Flow frontier"}</strong>
          <dl className="policy-details">
            <div><dt>Status</dt><dd>{decision.status}</dd></div>
            <div><dt>Source</dt><dd>{decision.source}</dd></div>
            <div><dt>Step</dt><dd>{decision.step}</dd></div>
          </dl>
          {decision.note && <p>{decision.note}</p>}
          {decision.unavailableReason && <p className="inline-error">{decision.unavailableReason}</p>}
          {decision.status === "frontier" && (
            <p className="notice">No current rule exists. Continue authoring in the TUI or edit the TOML manually.</p>
          )}
        </section>
      ) : (
        <p className="muted">
          {workspace.phase === "black-ready" ? "Choose Black’s legal response on the board." : "No decision after game over."}
        </p>
      )}
      <section className="lifecycle-groups">
        {(["active", "dormant", "retired"] as const).map((group) => (
          <div key={group}>
            <h3>{group}</h3>
            <p className="muted">{workspace.rules[group].length ? `${workspace.rules[group].length} rules` : "No lifecycle rules"}</p>
          </div>
        ))}
      </section>
      <p className="model-explanation">{workspace.rules.modelMessage}</p>
    </aside>
  );
}
