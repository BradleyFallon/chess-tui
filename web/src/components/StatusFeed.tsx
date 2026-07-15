import { type FormEvent, useEffect, useRef, useState } from "react";

import type { AttemptSnapshot, WorkspaceSnapshot } from "../types/workspace";

interface StatusFeedProps {
  workspace: WorkspaceSnapshot;
  pending: boolean;
  hintVisible: boolean;
  onHint: () => void;
  onRetry: () => void;
  onKeep: () => void;
  onNextBlack: () => void;
  onSubmitSan: (san: string) => void;
}

export function StatusFeed({
  workspace,
  pending,
  hintVisible,
  onHint,
  onRetry,
  onKeep,
  onNextBlack,
  onSubmitSan,
}: StatusFeedProps) {
  const feedRef = useRef<HTMLDivElement>(null);
  const [showEditHelp, setShowEditHelp] = useState(false);
  const [moveText, setMoveText] = useState("");
  const activity = workspace.activity ?? [];
  const moveEntryDisabled = pending || workspace.phase === "white-result" || workspace.phase === "game-over";

  const submitMove = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const san = moveText.trim();
    if (!san || moveEntryDisabled) return;
    setMoveText("");
    onSubmitSan(san);
  };

  useEffect(() => {
    const feed = feedRef.current;
    if (feed) feed.scrollTop = feed.scrollHeight;
  }, [activity.length, workspace.phase]);

  return (
    <aside className="workspace-panel status-panel" aria-labelledby="status-heading">
      <div className="section-heading-row status-heading-row">
        <h2 id="status-heading">Game status</h2>
        <span className="status-chip">live</span>
      </div>
      <div className="status-feed" role="log" aria-live="polite" ref={feedRef}>
        {activity.map((item) => (
          <article className={`status-note status-note-${item.kind}`} key={item.id}>
            <span className="status-note-marker" aria-hidden="true" />
            <div>
              <strong>{item.title}</strong>
              <p>{item.message}</p>
            </div>
          </article>
        ))}
        <CurrentStatus
          workspace={workspace}
          pending={pending}
          hintVisible={hintVisible}
          showEditHelp={showEditHelp}
          onHint={onHint}
          onRetry={onRetry}
          onKeep={onKeep}
          onNextBlack={onNextBlack}
          onToggleEditHelp={() => setShowEditHelp((visible) => !visible)}
        />
      </div>
      <p className="status-model-note">{workspace.rules.modelMessage}</p>
      <form className="status-composer" onSubmit={submitMove}>
        <input
          aria-label="Enter move in SAN"
          value={moveText}
          onChange={(event) => setMoveText(event.target.value)}
          placeholder={moveEntryDisabled ? "Resolve the current result first" : "Type a move in SAN…"}
          disabled={moveEntryDisabled}
          autoComplete="off"
          spellCheck={false}
          enterKeyHint="send"
          data-move-composer="true"
        />
        <button type="submit" aria-label="Submit move" disabled={moveEntryDisabled || !moveText.trim()}>
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path d="m5 12 14-7-4 14-3-6-7-1Z" />
            <path d="m12 13 7-8" />
          </svg>
        </button>
      </form>
    </aside>
  );
}

interface CurrentStatusProps extends Omit<StatusFeedProps, "onSubmitSan"> {
  showEditHelp: boolean;
  onToggleEditHelp: () => void;
}

function CurrentStatus({
  workspace,
  pending,
  hintVisible,
  showEditHelp,
  onHint,
  onRetry,
  onKeep,
  onNextBlack,
  onToggleEditHelp,
}: CurrentStatusProps) {
  if (workspace.phase === "white-ready") {
    const decision = workspace.decision;
    const message = decisionMessage(workspace);
    return (
      <article className="status-note status-note-prompt status-note-current">
        <span className="status-note-marker" aria-hidden="true" />
        <div>
          <strong>White to move</strong>
          <p>{message}</p>
          {decision?.note && <p className="status-reason">Reason: {decision.note}</p>}
          {decision?.moveUci && (
            <button
              className="hint-button"
              onClick={onHint}
              disabled={pending || hintVisible}
              aria-label={hintVisible ? "Hint shown" : "Hint"}
              title={hintVisible ? "Hint shown" : "Highlight the piece to move"}
            >
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path d="M9 20h6M10 23h4M8.3 15.2A7 7 0 1 1 15.7 15.2C14.7 16 14 17 14 18h-4c0-1-.7-2-1.7-2.8Z" />
              </svg>
              <span>Hint</span>
            </button>
          )}
        </div>
      </article>
    );
  }

  if (workspace.phase === "black-ready") {
    return (
      <article className="status-note status-note-prompt status-note-current">
        <span className="status-note-marker" aria-hidden="true" />
        <div>
          <strong>Black to move</strong>
          <p>Pick Black’s reply on the board, or press Enter / choose Next and let the engine play it.</p>
          <button className="primary status-next-button" onClick={onNextBlack} disabled={pending} aria-keyshortcuts="Enter">Next</button>
        </div>
      </article>
    );
  }

  if (workspace.phase === "white-result" && workspace.attempt) {
    return (
      <ResultActions
        attempt={workspace.attempt}
        flowPath={workspace.flow.path}
        pending={pending}
        showEditHelp={showEditHelp}
        onRetry={onRetry}
        onKeep={onKeep}
        onToggleEditHelp={onToggleEditHelp}
      />
    );
  }

  return (
    <article className="status-note status-note-current">
      <span className="status-note-marker" aria-hidden="true" />
      <div>
        <strong>Game over</strong>
        <p>{workspace.position.gameOver?.termination ?? "The line has ended."} {workspace.position.gameOver?.result}</p>
      </div>
    </article>
  );
}

function ResultActions({
  attempt,
  flowPath,
  pending,
  showEditHelp,
  onRetry,
  onKeep,
  onToggleEditHelp,
}: {
  attempt: AttemptSnapshot;
  flowPath: string;
  pending: boolean;
  showEditHelp: boolean;
  onRetry: () => void;
  onKeep: () => void;
  onToggleEditHelp: () => void;
}) {
  const correct = attempt.result === "correct";
  const mismatch = attempt.result.startsWith("mismatch");
  return (
    <article className="status-note status-note-action status-note-current">
      <span className="status-note-marker" aria-hidden="true" />
      <div>
        <strong>{correct ? "Correct — continue the line" : "Choose what to do next"}</strong>
        <EngineReview attempt={attempt} />
        <div className="button-row status-actions">
          {correct && <p>Correct. Advancing to Black’s move…</p>}
          {mismatch && <>
            <button onClick={onRetry} disabled={pending}>Retry</button>
            <button className="primary" onClick={onKeep} disabled={pending}>Use saved move</button>
          </>}
          {!correct && !mismatch && <button onClick={onRetry} disabled={pending}>Retry</button>}
          {!correct && <button onClick={onToggleEditHelp} disabled={pending}>Edit rules</button>}
        </div>
        {showEditHelp && (
          <p className="status-edit-help">
            Rule editing is not available in this web view yet. Edit <code>{flowPath}</code> manually or open it in the TUI, then restart this session.
          </p>
        )}
      </div>
    </article>
  );
}

function EngineReview({ attempt }: { attempt: AttemptSnapshot }) {
  const review = attempt.engineReview;
  if (!review) return null;
  if (review.status === "engine-off") return <p>Engine review is unavailable.</p>;
  if (review.status === "error") return <p className="inline-error">Engine review: {review.errorMessage}</p>;
  return (
    <p className="status-engine-review">
      Engine: <strong>{review.quality}</strong>
      {review.lossCp === null ? "." : `, ${(review.lossCp / 100).toFixed(2)} pawns lost.`}
      {review.bestMoveSan ? ` Best move: ${review.bestMoveSan}.` : ""}
    </p>
  );
}

function decisionMessage(workspace: WorkspaceSnapshot): string {
  const decision = workspace.decision;
  if (!decision || decision.status === "frontier") {
    return "This position is beyond the saved flow. Add a rule in the TUI or TOML file, or play a move to inspect it.";
  }
  if (decision.status === "unavailable") {
    return decision.unavailableReason ?? "The saved rule cannot be played in this position.";
  }
  return `Find the saved ${decision.source} move for step ${decision.step}.`;
}
