import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { BoardPanel } from "../components/BoardPanel";
import { EvaluationBar } from "../components/EvaluationBar";
import { RuleStatusPanel } from "../components/RuleStatusPanel";
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
    submitSanMove,
    retryWhite,
    keepWhite,
    playNextBlack,
    updateRule,
    back,
    restart,
  } = useWorkspace();
  const [hintedFen, setHintedFen] = useState<string | null>(null);

  useEffect(() => {
    if (workspace?.phase !== "black-ready" || pending) return;

    const playBlackOnEnter = (event: KeyboardEvent) => {
      if (event.key !== "Enter" || event.repeat || event.metaKey || event.ctrlKey || event.altKey) return;
      const target = event.target;
      const emptyMoveComposer =
        target instanceof HTMLInputElement
        && target.dataset.moveComposer === "true"
        && !target.value.trim();
      if (
        (target instanceof HTMLInputElement && !target.disabled && !emptyMoveComposer)
        || target instanceof HTMLTextAreaElement
        || target instanceof HTMLButtonElement
        || (target instanceof HTMLElement && target.isContentEditable)
      ) return;
      event.preventDefault();
      void playNextBlack();
    };

    window.addEventListener("keydown", playBlackOnEnter);
    return () => window.removeEventListener("keydown", playBlackOnEnter);
  }, [pending, playNextBlack, workspace?.phase]);

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
        <RuleStatusPanel
          workspace={workspace}
          pending={pending}
          onUpdateRule={(ruleId, kind, moveSan, note) => void updateRule(ruleId, kind, moveSan, note)}
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
            onNextBlack={() => void playNextBlack()}
            onSubmitSan={(san) => void submitSanMove(san)}
          />
        </div>
      </div>
    </main>
  );
}

function LoadingScreen() {
  return <main className="center-page"><p>Loading Development Mode…</p></main>;
}
