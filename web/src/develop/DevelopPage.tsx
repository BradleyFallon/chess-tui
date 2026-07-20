import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

import { BoardPanel } from "../components/BoardPanel";
import { EvaluationBar } from "../components/EvaluationBar";
import { PieceAuthoringPanel } from "../components/PieceAuthoringPanel";
import { StatusFeed } from "../components/StatusFeed";
import type { ConditionExpression, RuleDraft } from "../types/workspace";
import { useWorkspace } from "./WorkspaceContext";

const AUTO_RESPOND_KEY = "chess-flow-development-auto-respond";

export function DevelopPage() {
  const {
    workspace,
    loading,
    pending,
    error,
    effects,
    initialize,
    sendChat,
    executeCommand,
    validateRuleDraft,
    applyRuleDraft,
    deleteMoveRule,
    validateDevelopmentRule,
    applyDevelopmentRule,
    deleteDevelopmentRule,
    reorderDevelopmentRules,
    reorderPolicySection,
    validateStructureDraft,
    applyStructureDraft,
    deleteStructure,
    reorderStructures,
    validateNamedCondition,
    applyNamedCondition,
    deleteNamedCondition,
    validateExactFix,
    applyExactFix,
    deleteExactFix,
    addOpeningTag,
    removeOpeningTag,
    updateAnalysisSettings,
  } = useWorkspace();
  const [autoRespond, setAutoRespond] = useState(
    () => localStorage.getItem(AUTO_RESPOND_KEY) === "true",
  );
  const autoRespondedPosition = useRef<string | null>(null);
  const [selectedPieceRef, setSelectedPieceRef] = useState<string | null>(null);
  const [selectedAssignmentId, setSelectedAssignmentId] = useState<string | null>(null);
  const [targetPicking, setTargetPicking] = useState(false);
  const [pickedTarget, setPickedTarget] = useState<string | null>(null);
  const [responsePrefill, setResponsePrefill] = useState<RuleDraft | null>(null);
  const [responseSuggestions, setResponseSuggestions] = useState<
    Array<{ label: string; expression: ConditionExpression }>
  >([]);

  useEffect(() => {
    localStorage.setItem(AUTO_RESPOND_KEY, String(autoRespond));
  }, [autoRespond]);

  useEffect(() => {
    if (!autoRespond || workspace?.phase !== "opponent-ready") {
      autoRespondedPosition.current = null;
      return;
    }
    if (pending) return;
    const position = `${workspace.sessionId}:${workspace.position.fen}`;
    if (autoRespondedPosition.current === position) return;
    autoRespondedPosition.current = position;
    void executeCommand({ command: "next_opponent", source: "ui" });
  }, [
    autoRespond,
    executeCommand,
    pending,
    workspace?.phase,
    workspace?.position.fen,
    workspace?.sessionId,
  ]);

  useEffect(() => {
    if (workspace?.phase !== "opponent-ready" || pending) return;

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
      void executeCommand({ command: "next_opponent", source: "ui" });
    };

    window.addEventListener("keydown", playBlackOnEnter);
    return () => window.removeEventListener("keydown", playBlackOnEnter);
  }, [executeCommand, pending, workspace?.phase]);

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
  const hintMoveUci = effects.find((effect) => effect.kind === "highlight-move")?.uci ?? null;
  const hintVisible = hintMoveUci !== null;
  const selectedPiece = workspace.startingPieces.find(
    (piece) => piece.ref === selectedPieceRef,
  ) ?? null;
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
          {workspace.flow.openingTags.length > 0 && (
            <div className="flow-tags" aria-label="Opening labels">
              {workspace.flow.openingTags.map((tag) => (
                <button
                  className="flow-tag"
                  key={`${tag.eco}-${tag.name}`}
                  type="button"
                  disabled={pending || tag.recordId === null}
                  onClick={() => {
                    if (tag.recordId !== null) void removeOpeningTag(tag.recordId);
                  }}
                  title={`Remove ${tag.name} label`}
                >
                  {shortOpeningName(tag.name)}
                  <span aria-hidden="true">×</span>
                </button>
              ))}
            </div>
          )}
          <span>{workspace.flow.path}</span>
        </div>
        <div className="header-actions">
          <button onClick={() => void executeCommand({ command: "go_back", source: "ui" })} disabled={pending || !workspace.navigation.canBack}>Back</button>
          <button onClick={() => void executeCommand({ command: "restart", source: "ui" })} disabled={pending || !workspace.navigation.canRestart}>Restart</button>
        </div>
      </header>
      {error && (
        <div className="global-error" role="alert">
          <strong>{error.code}</strong>
          <span>{error.message}</span>
        </div>
      )}
      <div className="workspace-grid">
        <PieceAuthoringPanel
          key={`${selectedPiece?.ref ?? "no-piece"}:${responsePrefill ? "prefill" : "idle"}`}
          workspace={workspace}
          piece={selectedPiece}
          selectedAssignmentId={selectedAssignmentId}
          pending={pending}
          pickedTarget={pickedTarget}
          responsePrefill={responsePrefill}
          responseSuggestions={responseSuggestions}
          onConsumeResponsePrefill={() => {
            setResponsePrefill(null);
            setResponseSuggestions([]);
          }}
          onSelectAssignment={setSelectedAssignmentId}
          onBeginTargetPick={() => {
            setPickedTarget(null);
            setTargetPicking(true);
          }}
          onCancelTargetPick={() => {
            setTargetPicking(false);
            setPickedTarget(null);
          }}
          onValidateDevelopment={validateDevelopmentRule}
          onApplyDevelopment={applyDevelopmentRule}
          onDeleteDevelopment={deleteDevelopmentRule}
          onReorderDevelopment={reorderDevelopmentRules}
          onValidateRule={validateRuleDraft}
          onApplyRule={applyRuleDraft}
          onDeleteMoveRule={deleteMoveRule}
          onReorderSection={(section, ids) => reorderPolicySection(section, ids)}
          onValidateExactFix={validateExactFix}
          onApplyExactFix={applyExactFix}
          onDeleteExactFix={deleteExactFix}
          onValidateStructure={validateStructureDraft}
          onApplyStructure={applyStructureDraft}
          onDeleteStructure={deleteStructure}
          onReorderStructures={reorderStructures}
          onValidateNamedCondition={validateNamedCondition}
          onApplyNamedCondition={applyNamedCondition}
          onDeleteNamedCondition={deleteNamedCondition}
          onInspectPiece={(pieceRef) => setSelectedPieceRef(pieceRef)}
          onExplain={() => void executeCommand({ command: "explain_decision", source: "ui" })}
        />
        <div className="board-region">
          <EvaluationBar
            evaluation={workspace.evaluation}
          />
          <BoardPanel
            workspace={workspace}
            pending={pending}
            hintMoveUci={hintMoveUci}
            selectedPieceRef={selectedPieceRef}
            onInspectPiece={(pieceRef) => {
              setSelectedPieceRef(pieceRef);
              setSelectedAssignmentId(null);
              setTargetPicking(false);
              setPickedTarget(null);
            }}
            targetPicking={targetPicking}
            pickedTarget={pickedTarget}
            onPickTarget={(square) => {
              setPickedTarget(square);
              setTargetPicking(false);
            }}
            onMove={(uci) => {
              void executeCommand({ command: "play_move", source: "ui", notation: "uci", move: uci });
            }}
          />
        </div>
        <div className="side-region">
          <StatusFeed
            workspace={workspace}
            pending={pending}
            hintVisible={hintVisible}
            autoRespond={autoRespond}
            onAutoRespondChange={setAutoRespond}
            onAnalysisProfileChange={(profileId) => void updateAnalysisSettings(profileId)}
            onSubmit={(text) => void sendChat(text)}
            onExecute={(command) => void executeCommand(command)}
            onAcceptHere={() => void executeCommand({ command: "accept_attempt_as_override", source: "ui" })}
            onCreateBroaderResponse={() => {
              const prefill = workspace.attempt?.authoringPrefill;
              if (!prefill) return;
              setSelectedPieceRef(prefill.piece);
              setResponseSuggestions(prefill.suggestions);
              setResponsePrefill({
                id: null,
                section: "response",
                piece: prefill.piece,
                target: prefill.target,
                structures: [],
                note: null,
                unlockWhen: null,
                when: null,
                expireWhen: null,
              });
            }}
            onAddOpeningTag={(recordId) => void addOpeningTag(recordId)}
            onRemoveOpeningTag={(recordId) => void removeOpeningTag(recordId)}
          />
        </div>
      </div>
    </main>
  );
}

function LoadingScreen() {
  return <main className="center-page"><p>Loading Development Mode…</p></main>;
}

function shortOpeningName(name: string): string {
  return name.includes(":") ? name.split(":").at(-1)?.trim() ?? name : name;
}
