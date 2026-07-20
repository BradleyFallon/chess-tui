import { useState } from "react";
import { Link } from "react-router-dom";

import { BoardPanel } from "../components/BoardPanel";
import { PieceAuthoringPanel } from "../components/PieceAuthoringPanel";
import { useWorkspace } from "./WorkspaceContext";

export function DevelopPage() {
  const context = useWorkspace();
  const { workspace, loading, pending, error, initialize } = context;
  const [selectedAlias, setSelectedAlias] = useState<string | null>(null);

  if (loading) return <main className="center-page"><h1>Loading Rulebook…</h1></main>;
  if (!workspace) return (
    <main className="center-page">
      <h1>Rulebook unavailable</h1>
      <p className="inline-error">{error?.message}</p>
      <button onClick={() => void initialize()}>Try again</button>
    </main>
  );
  const effectiveAlias = selectedAlias
    ?? workspace.pieceScripts.find((piece) => piece.authorable)?.alias
    ?? workspace.pieceScripts[0]?.alias
    ?? null;
  const selected = workspace.pieceScripts.find((piece) => piece.alias === effectiveAlias) ?? null;
  return (
    <main className="develop-page">
      <header className="app-header">
        <div><Link className="brand" to="/">Chess Flow</Link><span className="header-separator">/</span><span>Opening Rule Engine</span></div>
        <div className="flow-title"><strong>{workspace.rulebook.name}</strong><span>Rulebook v{workspace.rulebook.version} · {workspace.rulebook.path}</span></div>
        <div className="header-actions">
          <button disabled={pending || !workspace.navigation.canBack} onClick={() => void context.back()}>Back</button>
          <button disabled={pending || !workspace.navigation.canRestart} onClick={() => void context.restart()}>Restart</button>
          <button disabled={pending} onClick={() => void context.analyse()}>Analyze</button>
        </div>
      </header>
      {error && <div className="global-error" role="alert"><strong>{error.code}</strong><span>{error.message}</span></div>}
      <div className="workspace-grid v4-grid">
        <PieceAuthoringPanel
          key={selected?.alias ?? "none"}
          workspace={workspace}
          piece={selected}
          pending={pending}
          onPreviewDevelopment={context.previewDevelopment}
          onApplyDevelopment={context.applyDevelopment}
          onDeleteDevelopment={context.deleteDevelopment}
          onPreviewInterrupt={context.previewInterrupt}
          onApplyInterrupt={context.applyInterrupt}
          onDeleteInterrupt={context.deleteInterrupt}
          onReorderDevelopment={context.reorderDevelopment}
          onReorderInterrupts={context.reorderInterrupts}
          onSelectPiece={setSelectedAlias}
        />
        <div className="board-and-history">
          <BoardPanel workspace={workspace} pending={pending} selectedAlias={effectiveAlias} onInspect={setSelectedAlias} onMove={(uci) => void context.move(uci)} />
          <section className="panel history-panel">
            <span className="eyebrow">History</span>
            <p>{workspace.position.historySan.join(" ") || "Start position"}</p>
            <p>Turn: {workspace.position.turn}</p>
            {workspace.evaluation.status === "ready" && <p>Evaluation: {workspace.evaluation.mateIn !== null ? `M${workspace.evaluation.mateIn}` : `${(workspace.evaluation.centipawns ?? 0) / 100}`}</p>}
          </section>
        </div>
        <DecisionPanel workspace={workspace} pending={pending} onRetry={context.retry} onContinue={context.continuePolicy} onAccept={context.acceptHere} />
      </div>
    </main>
  );
}

function DecisionPanel({ workspace, pending, onRetry, onContinue, onAccept }: {
  workspace: NonNullable<ReturnType<typeof useWorkspace>["workspace"]>;
  pending: boolean;
  onRetry: () => Promise<void>;
  onContinue: () => Promise<void>;
  onAccept: () => Promise<void>;
}) {
  return (
    <aside className="panel decision-panel">
      <span className="eyebrow">Current decision</span>
      {workspace.decision?.status === "ready" ? (
        <>
          <h2>{workspace.decision.moveSan}</h2>
          <code>{workspace.decision.instructionRef}</code>
          <p>{workspace.decision.why}</p>
        </>
      ) : workspace.decision?.frontier ? (
        <>
          <h2>Frontier</h2>
          <strong>{workspace.decision.frontier.reason}</strong>
          <p>{workspace.decision.frontier.explanation}</p>
        </>
      ) : <p>Choose an opponent move on the board.</p>}
      {workspace.attempt && (
        <section className="attempt-card">
          <h3>{workspace.attempt.result}</h3>
          <p>You played {workspace.attempt.moveSan}; expected {workspace.attempt.expectedSan ?? "a frontier"}.</p>
          <button disabled={pending} onClick={() => void onRetry()}>Retry</button>
          {workspace.attempt.expectedUci && <button disabled={pending} onClick={() => void onContinue()}>Use expected move</button>}
          <button disabled={pending} onClick={() => void onAccept()}>Accept in this position</button>
          <p>Add interrupt rule is available from the owning piece for broader behavior.</p>
        </section>
      )}
      <details><summary>Decision trace</summary><ol>{workspace.decision?.trace.map((line) => <li key={line}>{line}</li>)}</ol></details>
    </aside>
  );
}
