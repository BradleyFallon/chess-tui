import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

import { BoardPanel } from "../components/BoardPanel";
import { EvaluationBar } from "../components/EvaluationBar";
import { PieceAuthoringPanel } from "../components/PieceAuthoringPanel";
import { PolicyDetailsDrawer } from "../components/PolicyDetailsDrawer";
import { StatusFeed } from "../components/StatusFeed";
import { useWorkspace } from "./WorkspaceContext";

const AUTO_RESPOND_KEY = "chess-flow-development-auto-respond";

export function DevelopPage() {
  const context = useWorkspace();
  const { workspace, loading, pending, error, initialize } = context;
  const [selectedAlias, setSelectedAlias] = useState<string | null>(null);
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [autoRespond, setAutoRespond] = useState(
    () => localStorage.getItem(AUTO_RESPOND_KEY) === "true",
  );
  const autoResponsePosition = useRef<string | null>(null);

  useEffect(() => {
    if (
      !workspace
      || !autoRespond
      || workspace.opponent.mode === "manual"
      || workspace.position.turn === workspace.rulebook.side
      || workspace.position.gameOver
    ) {
      autoResponsePosition.current = null;
      return;
    }
    if (pending) return;
    const key = [
      workspace.position.historySan.join(" "),
      workspace.opponent.mode,
    ].join("|");
    if (autoResponsePosition.current === key) return;
    autoResponsePosition.current = key;
    void context.nextOpponent();
  }, [autoRespond, context, pending, workspace]);

  useEffect(() => {
    if (
      !workspace
      || pending
      || workspace.opponent.mode === "manual"
      || workspace.position.turn === workspace.rulebook.side
      || workspace.position.gameOver
    ) return;
    const playOpponentOnEnter = (event: KeyboardEvent) => {
      if (
        event.key !== "Enter"
        || event.repeat
        || event.metaKey
        || event.ctrlKey
        || event.altKey
      ) return;
      const target = event.target;
      const emptyComposer = target instanceof HTMLInputElement
        && target.dataset.moveComposer === "true"
        && !target.value.trim();
      if (
        (target instanceof HTMLInputElement && !target.disabled && !emptyComposer)
        || target instanceof HTMLTextAreaElement
        || target instanceof HTMLButtonElement
        || (target instanceof HTMLElement && target.isContentEditable)
      ) return;
      event.preventDefault();
      void context.nextOpponent();
    };
    window.addEventListener("keydown", playOpponentOnEnter);
    return () => window.removeEventListener("keydown", playOpponentOnEnter);
  }, [context, pending, workspace]);

  const changeAutoRespond = (enabled: boolean) => {
    localStorage.setItem(AUTO_RESPOND_KEY, String(enabled));
    setAutoRespond(enabled);
  };

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
          onOpenDetails={() => setDetailsOpen(true)}
        />
        <div className="board-region">
          <EvaluationBar evaluation={workspace.evaluation} />
          <BoardPanel workspace={workspace} pending={pending} selectedAlias={effectiveAlias} onInspect={setSelectedAlias} onMove={(uci) => void context.move(uci)} />
          <section className="workspace-panel history-panel">
            <div className="section-heading-row">
              <span className="eyebrow">Move history</span>
              <span className="turn-label">{workspace.position.turn} to move</span>
            </div>
            <p>{workspace.position.historySan.join(" ") || "Start position"}</p>
          </section>
        </div>
        <div className="side-region">
          <StatusFeed
            workspace={workspace}
            pending={pending}
            error={error}
            autoRespond={autoRespond}
            onAutoRespondChange={changeAutoRespond}
            onOpponentModeChange={(mode) => void context.updateOpponentMode(mode)}
            onAnalysisProfileChange={(profileId) => void context.updateAnalysisProfile(profileId)}
            onAddOpeningTag={(recordId) => void context.addOpeningTag(recordId)}
            onRemoveOpeningTag={(recordId) => void context.removeOpeningTag(recordId)}
            onAnalyse={() => void context.analyse()}
            onNextOpponent={() => void context.nextOpponent()}
            onSubmit={(text) => void context.sendChat(text)}
            onRetry={() => void context.retry()}
            onContinue={() => void context.continuePolicy()}
            onAcceptHere={() => void context.acceptHere()}
          />
        </div>
      </div>
      <PolicyDetailsDrawer
        workspace={workspace}
        piece={selected}
        open={detailsOpen}
        onClose={() => setDetailsOpen(false)}
      />
    </main>
  );
}
