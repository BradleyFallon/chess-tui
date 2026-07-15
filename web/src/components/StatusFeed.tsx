import { type FormEvent, useEffect, useRef, useState } from "react";

import type { AttemptSnapshot, WorkspaceSnapshot } from "../types/workspace";

interface Props {
  workspace: WorkspaceSnapshot; pending: boolean; hintVisible: boolean;
  onHint: () => void; onRetry: () => void; onContinue: () => void;
  onNextOpponent: () => void; onSubmitSan: (san: string) => void;
}

export function StatusFeed({ workspace, pending, hintVisible, onHint, onRetry, onContinue, onNextOpponent, onSubmitSan }: Props) {
  const feedRef = useRef<HTMLDivElement>(null);
  const [moveText, setMoveText] = useState("");
  const disabled = pending || workspace.phase === "policy-result" || workspace.phase === "game-over";
  const submit = (event: FormEvent) => { event.preventDefault(); const san = moveText.trim(); if (!san || disabled) return; setMoveText(""); onSubmitSan(san); };
  useEffect(() => { if (feedRef.current) feedRef.current.scrollTop = feedRef.current.scrollHeight; }, [workspace.activity.length, workspace.phase]);
  return <aside className="workspace-panel status-panel" aria-labelledby="status-heading">
    <div className="section-heading-row status-heading-row"><h2 id="status-heading">Game status</h2><span className="status-chip">live</span></div>
    <div className="status-feed" role="log" aria-live="polite" ref={feedRef}>
      {workspace.activity.map((item) => <article className={`status-note status-note-${item.kind}`} key={item.id}><span className="status-note-marker" aria-hidden="true" /><div><strong>{item.title}</strong><p>{item.message}</p></div></article>)}
      <CurrentStatus workspace={workspace} pending={pending} hintVisible={hintVisible} onHint={onHint} onRetry={onRetry} onContinue={onContinue} onNextOpponent={onNextOpponent} />
    </div>
    <form className="status-composer" onSubmit={submit}>
      <input aria-label="Enter move in SAN" value={moveText} onChange={(event) => setMoveText(event.target.value)} placeholder={disabled ? "Resolve the current result first" : "Type a move in SAN…"} disabled={disabled} autoComplete="off" spellCheck={false} enterKeyHint="send" data-move-composer="true" />
      <button type="submit" aria-label="Submit move" disabled={disabled || !moveText.trim()}><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m5 12 14-7-4 14-3-6-7-1Z" /><path d="m12 13 7-8" /></svg></button>
    </form>
  </aside>;
}

function CurrentStatus({ workspace, pending, hintVisible, onHint, onRetry, onContinue, onNextOpponent }: Omit<Props, "onSubmitSan">) {
  if (workspace.phase === "policy-ready") {
    const side = capitalize(workspace.flow.side);
    return <article className="status-note status-note-prompt status-note-current"><span className="status-note-marker" aria-hidden="true" /><div>
      <strong>{side} to move</strong><p>{decisionMessage(workspace)}</p>
      {workspace.decision?.note && <p className="status-reason">Reason: {workspace.decision.note}</p>}
      {workspace.decision?.moveUci && <button className="hint-button" onClick={onHint} disabled={pending || hintVisible} aria-label={hintVisible ? "Hint shown" : "Hint"} title="Highlight the piece to move"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 20h6M10 23h4M8.3 15.2A7 7 0 1 1 15.7 15.2C14.7 16 14 17 14 18h-4c0-1-.7-2-1.7-2.8Z" /></svg><span>Hint</span></button>}
    </div></article>;
  }
  if (workspace.phase === "opponent-ready") {
    const side = workspace.position.turn === "white" ? "White" : "Black";
    return <article className="status-note status-note-prompt status-note-current"><span className="status-note-marker" aria-hidden="true" /><div><strong>{side} to move</strong><p>Pick a reply on the board, or press Enter / choose Next and let the engine play it.</p><button className="primary status-next-button" onClick={onNextOpponent} disabled={pending} aria-keyshortcuts="Enter">Next</button></div></article>;
  }
  if (workspace.phase === "policy-result" && workspace.attempt) return <ResultActions attempt={workspace.attempt} pending={pending} onRetry={onRetry} onContinue={onContinue} />;
  return <article className="status-note status-note-current"><span className="status-note-marker" aria-hidden="true" /><div><strong>Game over</strong><p>{workspace.position.gameOver?.termination ?? "The line has ended."} {workspace.position.gameOver?.result}</p></div></article>;
}

function ResultActions({ attempt, pending, onRetry, onContinue }: { attempt: AttemptSnapshot; pending: boolean; onRetry: () => void; onContinue: () => void }) {
  const mismatch = attempt.result === "mismatch";
  return <article className="status-note status-note-action status-note-current"><span className="status-note-marker" aria-hidden="true" /><div>
    <strong>{mismatch ? "Rule mismatch" : "Flow frontier"}</strong>
    <p>You played {attempt.playedSan}.{attempt.expectedSan ? ` The selected policy expects ${attempt.expectedSan}.` : " No policy action resolves here."}</p>
    {attempt.note && <p>Reason: {attempt.note}</p>}<EngineReview attempt={attempt} />
    <div className="button-row status-actions"><button onClick={onRetry} disabled={pending}>Retry</button>{mismatch && <button className="primary" onClick={onContinue} disabled={pending}>Use selected move</button>}</div>
    <p className="status-edit-help">Use Edit in Rule Status to change the selected rule or override.</p>
  </div></article>;
}

function EngineReview({ attempt }: { attempt: AttemptSnapshot }) {
  const review = attempt.engineReview;
  if (!review) return null;
  if (review.status === "engine-off") return <p>Engine review is unavailable.</p>;
  if (review.status === "error") return <p className="inline-error">Engine review: {review.errorMessage}</p>;
  return <p className="status-engine-review">Engine: <strong>{review.quality}</strong>{review.lossCp === null ? "." : `, ${(review.lossCp / 100).toFixed(2)} pawns lost.`}{review.bestMoveSan ? ` Best move: ${review.bestMoveSan}.` : ""}</p>;
}

function decisionMessage(workspace: WorkspaceSnapshot): string {
  const decision = workspace.decision;
  if (!decision || decision.status === "frontier") return "No active legal rule resolves here. Edit an existing rule or the flow TOML.";
  return `Find the move selected by ${decision.source} ${decision.sourceId ?? ""}.`;
}
function capitalize(value: string): string { return value.charAt(0).toUpperCase() + value.slice(1); }
