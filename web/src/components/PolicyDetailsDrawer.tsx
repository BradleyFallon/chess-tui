import { useEffect, useRef } from "react";
import type { ReactNode } from "react";

import type { PieceScript, WorkspaceSnapshot } from "../types/workspace";

export function PolicyDetailsDrawer({
  workspace,
  piece,
  open,
  onClose,
}: {
  workspace: WorkspaceSnapshot;
  piece: PieceScript | null;
  open: boolean;
  onClose: () => void;
}) {
  const closeRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (open) closeRef.current?.focus();
  }, [open]);
  if (!open) return null;
  return (
    <div
      className="drawer-backdrop"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <aside
        className="policy-details-drawer"
        role="dialog"
        aria-modal="true"
        aria-label="Policy details"
      >
        <div className="drawer-heading">
          <div>
            <span className="eyebrow">Advanced</span>
            <h2>Policy details</h2>
          </div>
          <button ref={closeRef} onClick={onClose}>Close</button>
        </div>
        <Diagnostic title="Current decision" open>
          <p>
            {workspace.decision?.instructionRef
              ?? workspace.decision?.frontier?.reason
              ?? "Waiting for opponent"}
          </p>
          <p>{workspace.decision?.why}</p>
        </Diagnostic>
        <Diagnostic title="Decision trace" open>
          <ol>
            {workspace.decision?.trace.map((line, index) => (
              <li key={`${index}-${line}`}>{line}</li>
            ))}
          </ol>
        </Diagnostic>
        <Diagnostic title="Frontier and attempt diagnostics">
          <pre>{JSON.stringify({
            frontier: workspace.decision?.frontier,
            attempt: workspace.attempt,
          }, null, 2)}</pre>
        </Diagnostic>
        <Diagnostic title="Current trigger and ordered attempts">
          <pre>{JSON.stringify(
            piece?.interrupts.map((rule) => ({
              reference: rule.reference,
              status: rule.status,
              trigger: rule.trigger,
              attempts: rule.attempts,
            })) ?? [],
            null,
            2,
          )}</pre>
        </Diagnostic>
        <Diagnostic title="Attackers and defenders">
          <pre>{JSON.stringify(piece?.relationships ?? null, null, 2)}</pre>
        </Diagnostic>
        <Diagnostic title="Rulebook warnings" open>
          {workspace.rulebook.warnings.length
            ? workspace.rulebook.warnings.map((warning) => (
                <p key={warning}>{warning}</p>
              ))
            : <p>No Rulebook warnings.</p>}
        </Diagnostic>
        <Diagnostic title="Engine diagnostics">
          <pre>{JSON.stringify({
            evaluation: workspace.evaluation,
            settings: workspace.analysisSettings,
          }, null, 2)}</pre>
        </Diagnostic>
        <Diagnostic title="Generated Rulebook TOML">
          <pre>{workspace.rulebookSource}</pre>
        </Diagnostic>
      </aside>
    </div>
  );
}

function Diagnostic({
  title,
  open = false,
  children,
}: {
  title: string;
  open?: boolean;
  children: ReactNode;
}) {
  return (
    <details className="diagnostic-group" open={open}>
      <summary>{title}</summary>
      <div className="diagnostic-item">{children}</div>
    </details>
  );
}
