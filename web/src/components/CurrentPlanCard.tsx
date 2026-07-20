import type { WorkspaceSnapshot } from "../types/workspace";

export function CurrentPlanCard({ workspace }: { workspace: WorkspaceSnapshot }) {
  const selected = workspace.rules.structures.find((item) => item.status === "selected");
  const available = workspace.rules.structures.filter((item) => item.status === "available");
  const other = workspace.rules.structures.filter((item) => item.status !== "selected" && item.status !== "available");
  return (
    <section className="authoring-card current-plan-card">
      <span className="eyebrow">Current plan</span>
      {selected ? (
        <>
          <strong>{selected.name}</strong>
          <p>Selected when {selected.selectedWhen.explanation}.</p>
        </>
      ) : (
        <>
          <strong>No plan selected</strong>
          <p>{available.length ? "These plans are currently available." : "No authored plan is currently available."}</p>
        </>
      )}
      {available.length > 0 && <dl><dt>Available</dt><dd>{available.map((item) => item.name).join(", ")}</dd></dl>}
      {other.length > 0 && <dl><dt>Other plans</dt><dd>{other.map((item) => `${item.name} — ${item.status}`).join(", ")}</dd></dl>}
    </section>
  );
}
