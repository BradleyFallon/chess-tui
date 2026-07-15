import type { WorkspaceSnapshot } from "../types/workspace";

interface HistoryPanelProps {
  workspace: WorkspaceSnapshot;
  pending: boolean;
  onBack: () => void;
  onRestart: () => void;
}

export function HistoryPanel({ workspace, pending, onBack, onRestart }: HistoryPanelProps) {
  const pairs: Array<{ number: number; white?: string; black?: string }> = [];
  workspace.position.historySan.forEach((move, index) => {
    const pairIndex = Math.floor(index / 2);
    pairs[pairIndex] ??= { number: pairIndex + 1 };
    if (index % 2 === 0) pairs[pairIndex].white = move;
    else pairs[pairIndex].black = move;
  });
  return (
    <aside className="workspace-panel history-panel" aria-labelledby="history-heading">
      <h2 id="history-heading">Current line</h2>
      <dl className="position-meta">
        <div><dt>Ply</dt><dd>{workspace.position.ply}</dd></div>
        <div><dt>Turn</dt><dd>{workspace.position.turn}</dd></div>
      </dl>
      {pairs.length ? (
        <ol className="move-history" aria-label="SAN move history">
          {pairs.map((pair) => (
            <li key={pair.number}>
              <span>{pair.number}.</span>
              <strong>{pair.white ?? "—"}</strong>
              <strong>{pair.black ?? ""}</strong>
            </li>
          ))}
        </ol>
      ) : <p className="muted">Starting position</p>}
      <div className="button-row navigation-buttons">
        <button onClick={onBack} disabled={pending || !workspace.navigation.canBack}>Back</button>
        <button onClick={onRestart} disabled={pending || !workspace.navigation.canRestart}>Restart</button>
      </div>
    </aside>
  );
}
