import {
  type FormEvent,
  type KeyboardEvent,
  useEffect,
  useRef,
  useState,
} from "react";

import type { WorkspaceSnapshot } from "../types/workspace";

interface Props {
  workspace: WorkspaceSnapshot;
  pending: boolean;
  error?: { code: string; message: string } | null;
  autoRespond: boolean;
  onAutoRespondChange: (enabled: boolean) => void;
  onOpponentModeChange: (
    mode: WorkspaceSnapshot["opponent"]["mode"],
  ) => void;
  onAnalysisProfileChange: (profileId: string) => void;
  onAddOpeningTag: (recordId: number) => void;
  onRemoveOpeningTag: (recordId: number) => void;
  onAnalyse: () => void;
  onNextOpponent: () => void;
  onSubmit: (text: string) => void;
  onRetry: () => void;
  onContinue: () => void;
  onAcceptHere: () => void;
}

export function StatusFeed(props: Props) {
  const { workspace, pending } = props;
  const feedRef = useRef<HTMLDivElement>(null);
  const composerRef = useRef<HTMLInputElement>(null);
  const [text, setText] = useState("");
  const [selectedCommand, setSelectedCommand] = useState(0);
  const commandMode = text.startsWith("/");
  const token = commandMode ? text.split(/\s/, 1)[0].toLowerCase() : "";
  const commands = workspace.availableCommands.filter((command) =>
    command.slash.startsWith(token),
  );

  useEffect(() => {
    if (feedRef.current) feedRef.current.scrollTop = feedRef.current.scrollHeight;
  }, [workspace.timeline.length, workspace.position.historySan.length]);

  const send = (value: string) => {
    const trimmed = value.trim();
    if (!trimmed || pending) return;
    setText("");
    setSelectedCommand(0);
    props.onSubmit(trimmed);
  };
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (commandMode && !text.trim().includes(" ")) {
      const selected =
        workspace.availableCommands.find(
          (command) => command.slash === text.trim().toLowerCase(),
        ) ?? commands[selectedCommand];
      if (selected) {
        if (selected.arguments.length) {
          setText(`${selected.slash} `);
          composerRef.current?.focus();
        } else {
          send(selected.slash);
        }
        return;
      }
    }
    send(text);
  };
  const keyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (!commandMode || !commands.length) return;
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setSelectedCommand((current) => (current + 1) % commands.length);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setSelectedCommand(
        (current) => (current - 1 + commands.length) % commands.length,
      );
    } else if (event.key === "Escape") {
      setText("");
    }
  };

  const opponentTurn = workspace.position.turn !== workspace.rulebook.side;
  const selectedProfile = workspace.analysisSettings.profiles.find(
    (profile) => profile.id === workspace.analysisSettings.selectedProfileId,
  );
  return (
    <aside className="workspace-panel status-panel" aria-label="Development timeline">
      <div className="section-heading-row status-heading-row">
        <h2>Development timeline</h2>
        <span className="status-chip">live</span>
      </div>
      <section className="development-options" aria-label="Development options">
        <h3>Options</h3>
        <label className="option-toggle">
          <input
            type="checkbox"
            checked={props.autoRespond}
            disabled={pending || workspace.opponent.mode === "manual"}
            onChange={(event) => props.onAutoRespondChange(event.target.checked)}
          />
          <span>
            <strong>Auto-respond</strong>
            <small>Use the selected opponent source after your move.</small>
          </span>
        </label>
        <label className="analysis-option">
          <span><strong>Opponent source</strong></span>
          <select
            aria-label="Opponent source"
            value={workspace.opponent.mode}
            disabled={pending}
            onChange={(event) =>
              props.onOpponentModeChange(
                event.target.value as WorkspaceSnapshot["opponent"]["mode"],
              )}
          >
            <option value="stored">Stored reply mode</option>
            <option value="engine">Engine reply mode</option>
            <option value="manual">Manual mode</option>
          </select>
          <small>
            {opponentStatus(workspace)}
          </small>
        </label>
        <label className="analysis-option">
          <span>
            <strong>Engine analysis</strong>
            <small>{selectedProfile?.costDescription}</small>
          </span>
          <select
            aria-label="Engine analysis strength"
            value={workspace.analysisSettings.selectedProfileId}
            disabled={pending || workspace.analysisSettings.status === "off"}
            onChange={(event) =>
              props.onAnalysisProfileChange(event.target.value)}
          >
            {workspace.analysisSettings.profiles.map((profile) => (
              <option value={profile.id} key={profile.id}>
                {profile.label} · depth {profile.depth}
              </option>
            ))}
          </select>
          <button
            type="button"
            disabled={pending}
            onClick={props.onAnalyse}
          >
            Analyze position
          </button>
        </label>
      </section>
      <div className="status-feed" role="log" aria-live="polite" ref={feedRef}>
        {workspace.timeline.map((item) => item.kind === "user"
          || item.kind === "assistant" ? (
            <article
              className={`chat-message chat-message-${item.kind}`}
              key={item.id}
            >
              <span className="chat-role">{item.title}</span>
              <p>{item.message}</p>
            </article>
          ) : (
            <article
              className={`status-note status-note-${timelineClass(item.kind)}`}
              key={item.id}
            >
              <span className="status-note-marker" aria-hidden="true" />
              <div><strong>{item.title}</strong><p>{item.message}</p></div>
            </article>
          ))}
        {props.error && (
          <article className="status-note status-note-warning">
            <span className="status-note-marker" aria-hidden="true" />
            <div>
              <strong>{props.error.code}</strong>
              <p>{props.error.message}</p>
            </div>
          </article>
        )}
        <OpeningStatus
          workspace={workspace}
          pending={pending}
          onAdd={props.onAddOpeningTag}
          onRemove={props.onRemoveOpeningTag}
        />
        <PositionAnalysis workspace={workspace} />
        <CurrentStatus
          workspace={workspace}
          pending={pending}
          opponentTurn={opponentTurn}
          onNextOpponent={props.onNextOpponent}
          onRetry={props.onRetry}
          onContinue={props.onContinue}
          onAcceptHere={props.onAcceptHere}
        />
      </div>
      <div className="status-composer-shell">
        {commandMode && (
          <div
            className="command-menu"
            id="chat-command-menu"
            role="listbox"
            aria-label="Chat commands"
          >
            {commands.length ? commands.map((command, index) => (
              <button
                className={index === selectedCommand ? "selected" : undefined}
                key={command.id}
                type="button"
                role="option"
                aria-selected={index === selectedCommand}
                onMouseEnter={() => setSelectedCommand(index)}
                onClick={() => {
                  if (command.arguments.length) {
                    setText(`${command.slash} `);
                    composerRef.current?.focus();
                  } else send(command.slash);
                }}
              >
                <strong>{command.usage}</strong>
                <span>{command.description}</span>
              </button>
            )) : <p className="command-menu-empty">No matching commands</p>}
          </div>
        )}
        <form className="status-composer" onSubmit={submit}>
          <input
            ref={composerRef}
            aria-label="Enter move, chat, or command"
            data-move-composer="true"
            value={text}
            onChange={(event) => {
              setText(event.target.value);
              setSelectedCommand(0);
            }}
            onKeyDown={keyDown}
            placeholder="Type SAN or / command…"
            disabled={pending}
            autoComplete="off"
            spellCheck={false}
          />
          <button
            type="submit"
            aria-label="Send"
            disabled={pending || !text.trim()}
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

function PositionAnalysis({ workspace }: { workspace: WorkspaceSnapshot }) {
  const analysis = workspace.positionAnalysis;
  if (!analysis) return null;
  return (
    <article className="status-note status-note-commentary">
      <span className="status-note-marker" aria-hidden="true" />
      <div>
        <strong>Position analysis</strong>
        <div className="position-analysis">
          <section>
            <h3>Engine candidates</h3>
            <ol>
              {analysis.engineMoves.map((move) => (
                <li key={move.uci}>
                  <strong>{move.san}</strong>
                  <span>{moveScore(move.centipawns, move.mateIn)}</span>
                </li>
              ))}
            </ol>
          </section>
          <section>
            <h3>Opening index</h3>
            <p>{analysis.bookMoves.join(", ") || "No indexed continuation."}</p>
          </section>
        </div>
      </div>
    </article>
  );
}

function CurrentStatus(props: {
  workspace: WorkspaceSnapshot;
  pending: boolean;
  opponentTurn: boolean;
  onNextOpponent: () => void;
  onRetry: () => void;
  onContinue: () => void;
  onAcceptHere: () => void;
}) {
  const { workspace } = props;
  if (workspace.attempt) {
    return (
      <article className="status-note status-note-warning status-note-current">
        <span className="status-note-marker" aria-hidden="true" />
        <div>
          <strong>{workspace.attempt.result}</strong>
          <p>
            You played {workspace.attempt.moveSan}; expected{" "}
            {workspace.attempt.expectedSan ?? "a frontier"}.
          </p>
          <div className="button-row status-actions">
            <button disabled={props.pending} onClick={props.onRetry}>Retry</button>
            {workspace.attempt.expectedUci && (
              <button disabled={props.pending} onClick={props.onContinue}>
                Use recommendation
              </button>
            )}
            <button disabled={props.pending} onClick={props.onAcceptHere}>
              Accept in this position
            </button>
          </div>
        </div>
      </article>
    );
  }
  if (props.opponentTurn) {
    return (
      <article className="status-note status-note-prompt status-note-current">
        <span className="status-note-marker" aria-hidden="true" />
        <div>
          <strong>{capitalize(workspace.position.turn)} to move</strong>
          <p>{workspace.opponent.mode === "manual"
            ? "Enter the opponent move manually."
            : "Use the explicitly selected opponent source."}</p>
          {workspace.opponent.mode !== "manual" && (
            <button
              className="primary status-next-button"
              disabled={props.pending}
              onClick={props.onNextOpponent}
            >
              Next opponent
            </button>
          )}
        </div>
      </article>
    );
  }
  if (workspace.decision?.status === "ready") {
    return (
      <article className="status-note status-note-prompt status-note-current">
        <span className="status-note-marker" aria-hidden="true" />
        <div>
          <strong>Rulebook recommends {workspace.decision.moveSan}</strong>
          <p>{workspace.decision.instructionRef}</p>
          {workspace.decision.why && (
            <p className="status-reason">{workspace.decision.why}</p>
          )}
        </div>
      </article>
    );
  }
  return (
    <article className="status-note status-note-warning status-note-current">
      <span className="status-note-marker" aria-hidden="true" />
      <div>
        <strong>
          Frontier: {workspace.decision?.frontier?.reason ?? "unavailable"}
        </strong>
        <p>{workspace.decision?.frontier?.explanation}</p>
      </div>
    </article>
  );
}

function OpeningStatus({
  workspace,
  pending,
  onAdd,
  onRemove,
}: {
  workspace: WorkspaceSnapshot;
  pending: boolean;
  onAdd: (recordId: number) => void;
  onRemove: (recordId: number) => void;
}) {
  const name = workspace.opening.name ?? workspace.opening.lastKnownName;
  if (!name && !workspace.opening.moveSource) return null;
  return (
    <article className="status-note status-note-commentary">
      <span className="status-note-marker" aria-hidden="true" />
      <div>
        <strong>{workspace.opening.eco
          ? `${workspace.opening.eco} · ${name}`
          : name ?? "Opening context"}</strong>
        <p>
          Source: {workspace.opening.moveSource?.replaceAll("-", " ") ?? "start"}.
          {" "}{workspace.opening.bookContinuations.length} book continuation(s).
        </p>
        {workspace.opening.recordId !== null && (
          <button
            className="opening-tag-button"
            type="button"
            disabled={pending}
            onClick={() => workspace.opening.recordId !== null
              && (workspace.opening.isTagged
                ? onRemove(workspace.opening.recordId)
                : onAdd(workspace.opening.recordId))}
          >
            {workspace.opening.isTagged
              ? "Remove Rulebook label"
              : "Add as Rulebook label"}
          </button>
        )}
      </div>
    </article>
  );
}

function opponentStatus(workspace: WorkspaceSnapshot): string {
  if (workspace.opponent.mode === "stored") {
    return workspace.opponent.storedReplyAvailable
      ? "A stored reply is available here."
      : "No stored reply exists for the current history.";
  }
  if (workspace.opponent.mode === "engine") {
    return workspace.opponent.engineAvailable
      ? "The configured engine will choose the reply."
      : "No engine is configured; this mode will fail clearly.";
  }
  return "Choose the opponent move on the board or enter SAN.";
}

function timelineClass(kind: WorkspaceSnapshot["timeline"][number]["kind"]) {
  if (kind === "success") return "success";
  if (kind === "warning" || kind === "error") return "warning";
  if (kind === "move") return "move";
  if (kind === "opening") return "commentary";
  return "info";
}

function capitalize(value: string) {
  return value.charAt(0).toUpperCase() + value.slice(1);
}

function moveScore(centipawns: number | null, mateIn: number | null) {
  if (mateIn !== null) return `${mateIn >= 0 ? "+" : "-"}M${Math.abs(mateIn)}`;
  if (centipawns === null) return "—";
  const pawns = centipawns / 100;
  return `${pawns > 0 ? "+" : ""}${pawns.toFixed(2)}`;
}
