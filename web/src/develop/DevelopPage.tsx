import { useState } from "react";
import { Link } from "react-router-dom";

import { BoardPanel } from "../components/BoardPanel";
import { EvaluationBar } from "../components/EvaluationBar";
import { HistoryPanel } from "../components/HistoryPanel";
import { StatusFeed } from "../components/StatusFeed";
import { useWorkspace } from "./WorkspaceContext";

export function DevelopPage() {
  const {
    workspace,
    loading,
    pending,
    error,
    initialize,
    submitMove,
    retryWhite,
    keepWhite,
    continueWhite,
    playNextBlack,
    back,
    restart,
  } = useWorkspace();
  const [hintedFen, setHintedFen] = useState<string | null>(null);

  if (loading) return <LoadingScreen />;
  if (!workspace) {
    return (
      <main className="center-page">
        <h1>Development workspace unavailable</h1>
        <p className="inline-error">{error?.message ?? "The workspace could not be loaded."}</p>
        <button onClick={() => void initialize()}>Try again</button>
      </main>
    );
  }
  const hintVisible = hintedFen === workspace.position.fen;
  return (
    <main className="develop-page">
      <header className="app-header">
        <div>
          <Link className="brand" to="/">Chess Flow</Link>
          <span className="header-separator">/</span>
          <span>Develop</span>
        </div>
        <div className="flow-title">
          <strong>{workspace.flow.name}</strong>
          <span>{workspace.flow.path}</span>
        </div>
      </header>
      {error && (
        <div className="global-error" role="alert">
          <strong>{error.code}</strong>
          <span>{error.message}</span>
        </div>
      )}
      <div className="workspace-grid">
        <HistoryPanel
          workspace={workspace}
          pending={pending}
          onBack={() => void back()}
          onRestart={() => void restart()}
        />
        <div className="board-region">
          <EvaluationBar evaluation={workspace.evaluation} />
          <BoardPanel
            workspace={workspace}
            pending={pending}
            hintMoveUci={hintVisible ? workspace.decision?.moveUci ?? null : null}
            onMove={(uci) => {
              setHintedFen(null);
              void submitMove(uci);
            }}
          />
        </div>
        <div className="side-region">
          <StatusFeed
            workspace={workspace}
            pending={pending}
            hintVisible={hintVisible}
            onHint={() => setHintedFen(workspace.position.fen)}
            onRetry={() => void retryWhite()}
            onKeep={() => void keepWhite()}
            onContinue={() => void continueWhite()}
            onNextBlack={() => void playNextBlack()}
          />
        </div>
      </div>
    </main>
  );
}

function LoadingScreen() {
  return <main className="center-page"><p>Loading Development Mode…</p></main>;
}
