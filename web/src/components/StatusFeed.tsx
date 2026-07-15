import {
  type FormEvent,
  type KeyboardEvent,
  useEffect,
  useRef,
  useState,
} from "react";

import type {
  AttemptSnapshot,
  PositionAnalysisSnapshot,
  WorkspaceSnapshot,
} from "../types/workspace";

interface Props {
  workspace: WorkspaceSnapshot;
  pending: boolean;
  hintVisible: boolean;
  onHint: () => void;
  onRetry: () => void;
  onContinue: () => void;
  onAddRule: () => void;
  onNextOpponent: () => void;
  onSubmitSan: (san: string) => void;
  onBack: () => void;
  onRestart: () => void;
  onAnalyse: () => void;
}

interface ChatCommand {
  name: string;
  description: string;
  available: boolean;
  run: () => void;
}

export function StatusFeed({
  workspace,
  pending,
  hintVisible,
  onHint,
  onRetry,
  onContinue,
  onAddRule,
  onNextOpponent,
  onSubmitSan,
  onBack,
  onRestart,
  onAnalyse,
}: Props) {
  const feedRef = useRef<HTMLDivElement>(null);
  const composerRef = useRef<HTMLInputElement>(null);
  const [moveText, setMoveText] = useState("");
  const [selectedCommand, setSelectedCommand] = useState(0);
  const commandMode = moveText.startsWith("/");
  const sanUnavailable =
    workspace.phase === "policy-result" || workspace.phase === "game-over";
  const commands: ChatCommand[] = [
    {
      name: "/add-rule",
      description: "Accept the attempted move as an exact-position policy rule.",
      available:
        workspace.phase === "policy-result" &&
        workspace.attempt?.result === "mismatch",
      run: onAddRule,
    },
    {
      name: "/analyse",
      description: "Show local book moves and Stockfish's best candidates.",
      available:
        workspace.phase !== "game-over" &&
        workspace.evaluation.status !== "engine-off",
      run: onAnalyse,
    },
    {
      name: "/hint",
      description: "Highlight the piece selected by the current policy.",
      available:
        workspace.phase === "policy-ready" && Boolean(workspace.decision?.moveUci),
      run: onHint,
    },
    {
      name: "/next",
      description: "Ask the engine to play the opponent's next move.",
      available: workspace.phase === "opponent-ready",
      run: onNextOpponent,
    },
    {
      name: "/retry",
      description: "Discard the attempted move and try the policy turn again.",
      available: workspace.phase === "policy-result",
      run: onRetry,
    },
    {
      name: "/continue",
      description: "Discard the mismatch and play the selected policy move.",
      available:
        workspace.phase === "policy-result" &&
        workspace.attempt?.result === "mismatch",
      run: onContinue,
    },
    {
      name: "/back",
      description: "Return to the previous policy decision.",
      available: workspace.navigation.canBack,
      run: onBack,
    },
    {
      name: "/restart",
      description: "Restart this line from its initial position.",
      available: workspace.navigation.canRestart,
      run: onRestart,
    },
    {
      name: "/help",
      description: "Show all chat commands.",
      available: true,
      run: () => setMoveText("/"),
    },
  ];
  const commandQuery = commandMode ? moveText.slice(1).trim().toLowerCase() : "";
  const visibleCommands = commands.filter(
    (command) =>
      command.available && command.name.slice(1).startsWith(commandQuery),
  );

  const executeCommand = (command: ChatCommand | undefined) => {
    if (!command?.available || pending) return;
    if (command.name !== "/help") setMoveText("");
    command.run();
  };
  const submit = (event: FormEvent) => {
    event.preventDefault();
    const value = moveText.trim();
    if (!value || pending) return;
    if (commandMode) {
      const exact = commands.find((command) => command.name === value.toLowerCase());
      executeCommand(exact ?? visibleCommands[selectedCommand]);
      return;
    }
    if (sanUnavailable) return;
    setMoveText("");
    onSubmitSan(value);
  };
  const handleComposerKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (!commandMode || !visibleCommands.length) return;
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setSelectedCommand((current) => (current + 1) % visibleCommands.length);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setSelectedCommand(
        (current) => (current - 1 + visibleCommands.length) % visibleCommands.length,
      );
    } else if (event.key === "Escape") {
      event.preventDefault();
      setMoveText("");
    }
  };

  useEffect(() => {
    if (feedRef.current) feedRef.current.scrollTop = feedRef.current.scrollHeight;
  }, [workspace.activity.length, workspace.phase]);
  useEffect(() => {
    const focusComposerOnTyping = (event: globalThis.KeyboardEvent) => {
      if (
        pending ||
        event.defaultPrevented ||
        event.isComposing ||
        event.metaKey ||
        event.ctrlKey ||
        event.altKey ||
        event.key.length !== 1 ||
        event.key.trim() === ""
      ) {
        return;
      }
      const target = event.target;
      if (
        target instanceof HTMLInputElement ||
        target instanceof HTMLTextAreaElement ||
        target instanceof HTMLSelectElement ||
        (target instanceof HTMLElement && target.isContentEditable)
      ) {
        return;
      }
      event.preventDefault();
      composerRef.current?.focus();
      setMoveText((current) => current + event.key);
      setSelectedCommand(0);
    };

    window.addEventListener("keydown", focusComposerOnTyping);
    return () => window.removeEventListener("keydown", focusComposerOnTyping);
  }, [pending]);

  return (
    <aside className="workspace-panel status-panel" aria-labelledby="status-heading">
      <div className="section-heading-row status-heading-row">
        <h2 id="status-heading">Game status</h2>
        <span className="status-chip">live</span>
      </div>
      <div className="status-feed" role="log" aria-live="polite" ref={feedRef}>
        {workspace.activity.map((item) => (
          <article className={`status-note status-note-${item.kind}`} key={item.id}>
            <span className="status-note-marker" aria-hidden="true" />
            <div>
              <strong>{item.title}</strong>
              <p>{item.message}</p>
              {item.analysis && <PositionAnalysis analysis={item.analysis} />}
            </div>
          </article>
        ))}
        <CurrentStatus
          workspace={workspace}
          pending={pending}
          hintVisible={hintVisible}
          onHint={onHint}
          onRetry={onRetry}
          onContinue={onContinue}
          onNextOpponent={onNextOpponent}
        />
      </div>
      <div className="status-composer-shell">
        {commandMode && (
          <div className="command-menu" id="chat-command-menu" role="listbox" aria-label="Chat commands">
            {visibleCommands.length ? (
              visibleCommands.map((command, index) => (
                <button
                  className={index === selectedCommand ? "selected" : undefined}
                  id={`chat-command-${command.name.slice(1)}`}
                  key={command.name}
                  type="button"
                  role="option"
                  aria-selected={index === selectedCommand}
                  disabled={pending}
                  onMouseEnter={() => setSelectedCommand(index)}
                  onClick={() => executeCommand(command)}
                >
                  <strong>{command.name}</strong>
                  <span title={command.description}>{command.description}</span>
                </button>
              ))
            ) : (
              <p className="command-menu-empty">No matching commands</p>
            )}
          </div>
        )}
        <form className="status-composer" onSubmit={submit}>
          <input
            ref={composerRef}
            aria-label="Enter move in SAN"
            role="combobox"
            aria-autocomplete="list"
            aria-expanded={commandMode}
            aria-controls={commandMode ? "chat-command-menu" : undefined}
            aria-activedescendant={
              commandMode && visibleCommands[selectedCommand]
                ? `chat-command-${visibleCommands[selectedCommand].name.slice(1)}`
                : undefined
            }
            value={moveText}
            onChange={(event) => {
              setMoveText(event.target.value);
              setSelectedCommand(0);
            }}
            onKeyDown={handleComposerKeyDown}
            placeholder="Type a move or / command…"
            disabled={pending}
            autoComplete="off"
            spellCheck={false}
            enterKeyHint="send"
            data-move-composer="true"
          />
          <button
            type="submit"
            aria-label="Submit move"
            disabled={
              pending ||
              !moveText.trim() ||
              (!commandMode && sanUnavailable)
            }
          >
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="m5 12 14-7-4 14-3-6-7-1Z" />
              <path d="m12 13 7-8" />
            </svg>
          </button>
        </form>
      </div>
    </aside>
  );
}

function CurrentStatus({
  workspace,
  pending,
  hintVisible,
  onHint,
  onRetry,
  onContinue,
  onNextOpponent,
}: Omit<Props, "onSubmitSan" | "onBack" | "onRestart" | "onAnalyse" | "onAddRule">) {
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
    <p className="status-edit-help">Use /add-rule in chat to accept this move here, or use Edit in Rule Status to change the selected rule or override.</p>
  </div></article>;
}

function EngineReview({ attempt }: { attempt: AttemptSnapshot }) {
  const review = attempt.engineReview;
  if (!review) return null;
  if (review.status === "engine-off") return <p>Engine review is unavailable.</p>;
  if (review.status === "error") return <p className="inline-error">Engine review: {review.errorMessage}</p>;
  return <p className="status-engine-review">Engine: <strong>{review.quality}</strong>{review.lossCp === null ? "." : `, ${(review.lossCp / 100).toFixed(2)} pawns lost.`}{review.bestMoveSan ? ` Best move: ${review.bestMoveSan}.` : ""}</p>;
}

function PositionAnalysis({ analysis }: { analysis: PositionAnalysisSnapshot }) {
  return (
    <div className="position-analysis">
      <AnalysisGroup title="Book moves" empty="No local book moves found.">
        {analysis.bookMoves.map((move) => (
          <li key={move.uci}>
            <strong>{move.san}</strong>
            <span>{bookMoveLabel(move.source, move.frequency)}</span>
          </li>
        ))}
      </AnalysisGroup>
      <AnalysisGroup title="Engine best" empty="No engine candidates returned.">
        {analysis.engineMoves.map((move, index) => (
          <li key={move.uci}>
            <strong>{index + 1}. {move.san}</strong>
            <span>{analysisScore(move.evaluationCp, move.mateIn)}</span>
          </li>
        ))}
      </AnalysisGroup>
    </div>
  );
}

function AnalysisGroup({ title, empty, children }: { title: string; empty: string; children: React.ReactNode }) {
  const items = Array.isArray(children) ? children : [children];
  return (
    <section>
      <h3>{title}</h3>
      {items.length ? <ol>{children}</ol> : <p>{empty}</p>}
    </section>
  );
}

function bookMoveLabel(source: string, frequency: number | null): string {
  if (frequency !== null) return `${Math.round(frequency * 100)}% · local book`;
  if (source === "policy") return "selected policy";
  return "authored branch";
}

function analysisScore(cp: number | null, mate: number | null): string {
  if (mate !== null) return `${mate >= 0 ? "+" : "-"}M${Math.abs(mate)}`;
  if (cp === null) return "—";
  const pawns = cp / 100;
  if (pawns === 0) return "0.00";
  return `${pawns > 0 ? "+" : ""}${pawns.toFixed(2)}`;
}

function decisionMessage(workspace: WorkspaceSnapshot): string {
  const decision = workspace.decision;
  if (!decision || decision.status === "frontier") return "No active legal rule resolves here. Edit an existing rule or the flow TOML.";
  return `Find the move selected by ${decision.source} ${decision.sourceId ?? ""}.`;
}
function capitalize(value: string): string { return value.charAt(0).toUpperCase() + value.slice(1); }
