import { useEffect, useRef, useState } from "react";

import {
  AuthoringSidebar,
  type AuthoringTab,
} from "../components/AuthoringSidebar";
import { BoardStage } from "../components/BoardStage";
import { CoachPanel } from "../components/CoachPanel";
import { CommandBar } from "../components/CommandBar";
import {
  DetailsDrawer,
  type DetailsTab,
} from "../components/DetailsDrawer";
import { useWorkspace } from "./WorkspaceContext";

const AUTO_RESPOND_KEY = "chess-flow-development-auto-respond";

export function DevelopPage() {
  const context = useWorkspace();
  const { workspace, loading, pending, error, initialize } = context;
  const [selectedAlias, setSelectedAlias] = useState<string | null>(null);
  const [authoringTab, setAuthoringTab] = useState<AuthoringTab>("piece");
  const [focusInterruptRef, setFocusInterruptRef] = useState<string | null>(null);
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [detailsTab, setDetailsTab] = useState<DetailsTab>("decision");
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
  const inspectPiece = (alias: string) => {
    setSelectedAlias(alias);
    setFocusInterruptRef(null);
    setAuthoringTab("piece");
  };
  const focusInterrupt = (reference: string) => {
    setSelectedAlias(reference.split(".")[0]);
    setFocusInterruptRef(reference);
    setAuthoringTab("piece");
  };
  const openDetails = (tab: DetailsTab) => {
    setDetailsTab(tab);
    setDetailsOpen(true);
  };
  return (
    <main className="develop-page">
      <CommandBar
        workspace={workspace}
        pending={pending}
        autoRespond={autoRespond}
        onAutoRespondChange={changeAutoRespond}
        onOpponentModeChange={(mode) => void context.updateOpponentMode(mode)}
        onAnalysisProfileChange={(profileId) => void context.updateAnalysisProfile(profileId)}
        onAnalyse={() => void context.analyse()}
        onBack={() => void context.back()}
        onRestart={() => void context.restart()}
      />
      <div className="development-workspace">
        <AuthoringSidebar
          key={`${selected?.alias ?? "none"}:${focusInterruptRef ?? "summary"}`}
          workspace={workspace}
          piece={selected}
          pending={pending}
          tab={authoringTab}
          focusInterruptRef={focusInterruptRef}
          onTabChange={setAuthoringTab}
          onFocusHandled={() => setFocusInterruptRef(null)}
          onPreviewDevelopment={context.previewDevelopment}
          onApplyDevelopment={context.applyDevelopment}
          onDeleteDevelopment={context.deleteDevelopment}
          onPreviewInterrupt={context.previewInterrupt}
          onApplyInterrupt={context.applyInterrupt}
          onDeleteInterrupt={context.deleteInterrupt}
          onReorderDevelopment={context.reorderDevelopment}
          onReorderInterrupts={context.reorderInterrupts}
          onSelectPiece={inspectPiece}
          onFocusInterrupt={focusInterrupt}
          onOpenDetails={openDetails}
        />
        <BoardStage
          workspace={workspace}
          pending={pending}
          selectedAlias={effectiveAlias}
          onInspect={inspectPiece}
          onMove={(uci) => void context.move(uci)}
          onOpenDetails={openDetails}
          onNextOpponent={() => void context.nextOpponent()}
          onRetry={() => void context.retry()}
          onContinue={() => void context.continuePolicy()}
          onAcceptHere={() => void context.acceptHere()}
        />
        <CoachPanel
          workspace={workspace}
          pending={pending}
          error={error}
          onAddOpeningTag={(recordId) => void context.addOpeningTag(recordId)}
          onRemoveOpeningTag={(recordId) => void context.removeOpeningTag(recordId)}
          onSubmit={(text) => void context.sendChat(text)}
          onOpenDetails={openDetails}
        />
      </div>
      {detailsOpen && (
        <DetailsDrawer
          workspace={workspace}
          piece={selected}
          open
          tab={detailsTab}
          onTabChange={setDetailsTab}
          onClose={() => setDetailsOpen(false)}
        />
      )}
    </main>
  );
}
