import type { WorkspaceSnapshot } from "../types/workspace";

export function CurrentDecisionCard({
  workspace,
  onExplain,
  onOpenDetails,
}: {
  workspace: WorkspaceSnapshot;
  onExplain: () => void;
  onOpenDetails: () => void;
}) {
  const attempt = workspace.attempt;
  return (
    <section className="authoring-card current-decision-card" aria-labelledby="current-decision-heading">
      <span className="eyebrow" id="current-decision-heading">Current decision</span>
      {attempt ? (
        <>
          <strong>{attempt.result === "mismatch" ? `Expected ${attempt.expectedSan}` : "No authored move"}</strong>
          <p>You played {attempt.playedSan}.</p>
        </>
      ) : workspace.decision ? (
        <>
          <strong>{workspace.decision.moveSan ?? "No authored move"}</strong>
          <p>{workspace.decision.reason}</p>
        </>
      ) : (
        <p className="muted">The opponent is choosing a reply.</p>
      )}
      <div className="button-row">
        {workspace.decision && <button type="button" onClick={onExplain}>Explain</button>}
        <button type="button" onClick={onOpenDetails}>Policy details</button>
      </div>
    </section>
  );
}
