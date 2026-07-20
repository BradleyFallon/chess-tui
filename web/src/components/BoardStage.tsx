import type { PieceScript, WorkspaceSnapshot } from "../types/workspace";
import { BoardPanel } from "./BoardPanel";
import { EvaluationBar } from "./EvaluationBar";

interface Props {
  workspace: WorkspaceSnapshot;
  pending: boolean;
  selectedAlias: string | null;
  onInspect: (alias: string) => void;
  onMove: (uci: string) => void;
  onOpenDetails: (tab: "decision" | "relations" | "engine" | "source") => void;
  onNextOpponent: () => void;
  onRetry: () => void;
  onContinue: () => void;
  onAcceptHere: () => void;
}

export function BoardStage(props: Props) {
  const { workspace } = props;
  const instructionPiece = findInstructionPiece(
    workspace.pieceScripts,
    workspace.decision?.instructionRef,
  );
  const opponentTurn = workspace.position.turn !== workspace.rulebook.side;

  return (
    <section className="board-stage" aria-label="Board Stage">
      <button
        className={`recommendation-strip ${workspace.decision?.status === "frontier" ? "frontier" : ""}`}
        type="button"
        onClick={() => {
          if (instructionPiece) props.onInspect(instructionPiece.alias);
          else props.onOpenDetails("decision");
        }}
      >
        {workspace.decision?.status === "ready" ? (
          <>
            <span>Recommended</span>
            <strong>{workspace.decision.moveSan}</strong>
            <small>· {workspace.decision.source === "development" ? "Default development" : "Interrupt"}</small>
          </>
        ) : workspace.decision?.frontier ? (
          <>
            <span>Frontier</span>
            <strong>{humanize(workspace.decision.frontier.reason)}</strong>
          </>
        ) : (
          <>
            <span>Position</span>
            <strong>{capitalize(workspace.position.turn)} to move</strong>
          </>
        )}
        <span className="recommendation-arrow" aria-hidden="true">›</span>
      </button>

      <div className="board-stage-center">
        <EvaluationBar
          evaluation={workspace.evaluation}
          onOpenDetails={() => props.onOpenDetails("engine")}
        />
        <BoardPanel
          workspace={workspace}
          pending={props.pending}
          selectedAlias={props.selectedAlias}
          onInspect={props.onInspect}
          onMove={props.onMove}
        />
      </div>

      <div className="board-action-row" aria-label="Immediate board actions">
        {workspace.attempt ? (
          <>
            <span>
              <strong>{humanize(workspace.attempt.result)}</strong>
              {" · "}{workspace.attempt.moveSan}
              {workspace.attempt.expectedSan && ` / expected ${workspace.attempt.expectedSan}`}
            </span>
            <button disabled={props.pending} onClick={props.onRetry}>Retry</button>
            {workspace.attempt.expectedUci && (
              <button className="primary" disabled={props.pending} onClick={props.onContinue}>
                Use expected move
              </button>
            )}
            <button disabled={props.pending} onClick={props.onAcceptHere}>
              Accept in this position
            </button>
          </>
        ) : opponentTurn && workspace.opponent.mode !== "manual" ? (
          <>
            <span>{capitalize(workspace.position.turn)} to move via {workspace.opponent.mode}</span>
            <button className="primary" disabled={props.pending} onClick={props.onNextOpponent}>
              Play opponent
            </button>
          </>
        ) : (
          <span className="move-history-line">
            {workspace.position.historySan.join(" ") || "Start position"}
          </span>
        )}
      </div>
    </section>
  );
}

function findInstructionPiece(
  pieces: PieceScript[],
  reference: string | null | undefined,
) {
  if (!reference) return null;
  const alias = reference.split(".")[0];
  return pieces.find((piece) => piece.alias === alias) ?? null;
}

function humanize(value: string) {
  return value.replaceAll("-", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function capitalize(value: string) {
  return value.charAt(0).toUpperCase() + value.slice(1);
}
