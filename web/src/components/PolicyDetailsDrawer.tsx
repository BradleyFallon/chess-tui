import { useEffect, useRef, useState } from "react";

import { workspaceApi } from "../api/client";
import type { PolicyItemSnapshot, WorkspaceSnapshot } from "../types/workspace";

export function PolicyDetailsDrawer({
  workspace,
  open,
  onClose,
}: {
  workspace: WorkspaceSnapshot;
  open: boolean;
  onClose: () => void;
}) {
  const closeRef = useRef<HTMLButtonElement>(null);
  const drawerRef = useRef<HTMLElement>(null);
  const returnFocusRef = useRef<HTMLElement | null>(null);
  const [source, setSource] = useState<string | null>(null);
  const [sourceError, setSourceError] = useState<string | null>(null);
  useEffect(() => {
    if (!open) return;
    returnFocusRef.current = document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null;
    closeRef.current?.focus();
    void workspaceApi.getFlowSource(workspace.sessionId)
      .then((result) => setSource(result.content))
      .catch((error: unknown) => setSourceError(error instanceof Error ? error.message : "Could not load flow source."));
    return () => returnFocusRef.current?.focus();
  }, [open, workspace.sessionId]);
  useEffect(() => {
    if (!open) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [onClose, open]);
  if (!open) return null;
  const items: PolicyItemSnapshot[] = [
    ...workspace.rules.responses,
    ...workspace.rules.development,
    ...workspace.rules.continuations,
    ...workspace.rules.overrides,
  ];
  return (
    <div className="drawer-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <aside
        className="policy-details-drawer"
        ref={drawerRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="policy-details-heading"
        onKeyDown={(event) => {
          if (event.key !== "Tab") return;
          const focusable = drawerRef.current?.querySelectorAll<HTMLElement>(
            "button:not(:disabled), summary, input:not(:disabled), textarea:not(:disabled), select:not(:disabled), [tabindex]:not([tabindex='-1'])",
          );
          if (!focusable?.length) return;
          const first = focusable[0];
          const last = focusable[focusable.length - 1];
          if (event.shiftKey && document.activeElement === first) {
            event.preventDefault();
            last.focus();
          } else if (!event.shiftKey && document.activeElement === last) {
            event.preventDefault();
            first.focus();
          }
        }}
      >
        <div className="drawer-heading">
          <div><span className="eyebrow">Advanced diagnostics</span><h2 id="policy-details-heading">Policy details</h2></div>
          <button ref={closeRef} type="button" onClick={onClose}>Close policy details</button>
        </div>
        <DiagnosticGroup title="Selected item" items={workspace.rules.selected ? [workspace.rules.selected] : []} />
        <details className="diagnostic-group"><summary>Structures <span>{workspace.rules.structures.length}</span></summary>{workspace.rules.structures.map((item) => <section className="diagnostic-item" key={item.id}><strong>{item.id} · {item.name}</strong><dl><dt>Authored order</dt><dd>{item.order}</dd><dt>Runtime status</dt><dd>{item.status}</dd><dt>Reason</dt><dd>{item.reason}</dd><dt>Policy dependencies</dt><dd>{item.affectedPolicyItems.join(", ") || "None"}</dd></dl><pre><code>{JSON.stringify({ availableWhen: item.availableWhen.expression, selectedWhen: item.selectedWhen.expression }, null, 2)}</code></pre></section>)}</details>
        <DiagnosticGroup title="Responses" items={workspace.rules.responses} />
        <DiagnosticGroup title="Development" items={workspace.rules.development} />
        <DiagnosticGroup title="Continuations" items={workspace.rules.continuations} />
        <DiagnosticGroup title="Completed" items={items.filter((item) => item.kind === "rule" && item.friendlyStatus === "completed")} />
        <DiagnosticGroup title="Waiting / blocked" items={items.filter((item) => item.kind === "rule" && item.status === "waiting")} />
        <DiagnosticGroup title="Out of scope" items={items.filter((item) => item.kind === "rule" && item.status === "out-of-scope")} />
        <DiagnosticGroup title="Exact fixes" items={workspace.rules.overrides} />
        <details className="diagnostic-group"><summary>Decision trace <span>{workspace.decision?.trace.length ?? 0}</span></summary><ol>{workspace.decision?.trace.map((line) => <li key={line}>{line}</li>)}</ol></details>
        <details className="diagnostic-group"><summary>Flow warnings <span>{workspace.flow.warnings.length}</span></summary>{workspace.flow.warnings.length ? <ul>{workspace.flow.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul> : <p>None.</p>}</details>
        <details className="diagnostic-group"><summary>Named conditions <span>{workspace.namedConditions.length}</span></summary>{workspace.namedConditions.map((condition) => <section className="diagnostic-item" key={condition.id}><strong>{condition.id}</strong><p>{condition.summary}</p><p>References: {condition.references.join(", ") || "None"}</p><pre><code>{JSON.stringify(condition.expression, null, 2)}</code></pre></section>)}</details>
        <details className="diagnostic-group"><summary>Flow TOML</summary>{sourceError && <p role="alert">{sourceError}</p>}{source ? <pre aria-label="Flow TOML source"><code>{source}</code></pre> : <p>Loading source…</p>}</details>
      </aside>
    </div>
  );
}

function DiagnosticGroup({ title, items }: { title: string; items: PolicyItemSnapshot[] }) {
  return (
    <details className="diagnostic-group" open={title === "Selected item"}>
      <summary>{title} <span>{items.length}</span></summary>
      {items.length === 0 ? <p className="muted">None.</p> : items.map((item) => (
        <section className="diagnostic-item" key={`${item.kind}-${item.id}`}>
          <strong>{item.id}</strong>
          <dl>
            {"order" in item && <><dt>Authored order</dt><dd>{item.section} #{item.order}</dd><dt>Lifecycle</dt><dd>{item.lifecycle}</dd><dt>Runtime status</dt><dd>{item.status}</dd><dt>Move legality</dt><dd>{item.legal ? "Legal" : "Not legal"}</dd></>}
            {"afterSan" in item && <><dt>Normalized source line</dt><dd>{item.afterSan.join(" ") || "starting position"}</dd><dt>Matched</dt><dd>{String(item.matched)}</dd></>}
            <dt>Reason</dt><dd>{item.reason}</dd>
          </dl>
          {"unlockWhen" in item && <pre><code>{JSON.stringify({ unlockWhen: item.unlockWhen?.expression ?? null, when: item.when?.expression ?? null, expireWhen: item.expireWhen?.expression ?? null }, null, 2)}</code></pre>}
        </section>
      ))}
    </details>
  );
}
