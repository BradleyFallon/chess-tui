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
  onAddOpeningTag: (recordId: number) => void;
  onRemoveOpeningTag: (recordId: number) => void;
  onSubmit: (text: string) => void;
  onOpenDetails: (tab: "decision" | "relations" | "engine" | "source") => void;
}

export function CoachPanel(props: Props) {
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
        } else send(selected.slash);
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

  return (
    <aside className="coach-panel" aria-label="Coach Panel">
      <header className="coach-heading">
        <div>
          <span className="eyebrow">Coach Panel</span>
          <h2>Timeline</h2>
        </div>
        <button
          className="details-button"
          type="button"
          onClick={() => props.onOpenDetails("decision")}
        >
          Details
        </button>
      </header>
      <div className="coach-timeline" role="log" aria-live="polite" ref={feedRef}>
        {workspace.timeline.map((item) => (
          <TimelineEntry key={item.id} item={item} onOpenDetails={props.onOpenDetails} />
        ))}
        {props.error && (
          <article className="timeline-entry tone-warning">
            <span className="timeline-icon" aria-hidden="true">!</span>
            <div><strong>{props.error.code}</strong><p>{props.error.message}</p></div>
          </article>
        )}
        <OpeningContext
          workspace={workspace}
          pending={pending}
          onAdd={props.onAddOpeningTag}
          onRemove={props.onRemoveOpeningTag}
        />
        {workspace.positionAnalysis && (
          <button
            className="timeline-entry timeline-button tone-analysis"
            type="button"
            onClick={() => props.onOpenDetails("engine")}
          >
            <span className="timeline-icon" aria-hidden="true">⚙</span>
            <div>
              <strong>Position analysis ready</strong>
              <p>
                {workspace.positionAnalysis.engineMoves.length} engine line(s)
                {" · "}{workspace.positionAnalysis.bookMoves.length} book move(s)
              </p>
            </div>
            <span aria-hidden="true">›</span>
          </button>
        )}
        {workspace.decision?.frontier && (
          <button
            className="timeline-entry timeline-button tone-warning"
            type="button"
            onClick={() => props.onOpenDetails("decision")}
          >
            <span className="timeline-icon" aria-hidden="true">!</span>
            <div>
              <strong>{humanize(workspace.decision.frontier.reason)}</strong>
              <p>{workspace.decision.frontier.explanation}</p>
            </div>
            <span aria-hidden="true">›</span>
          </button>
        )}
      </div>
      <div className="coach-composer-shell">
        {commandMode && (
          <div className="command-menu" id="chat-command-menu" role="listbox" aria-label="Chat commands">
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
        <form className="coach-composer" onSubmit={submit}>
          <input
            ref={composerRef}
            id="coach-composer-input"
            name="coach-composer"
            aria-label="Enter move, chat, or command"
            data-move-composer="true"
            value={text}
            onChange={(event) => {
              setText(event.target.value);
              setSelectedCommand(0);
            }}
            onKeyDown={keyDown}
            placeholder="SAN, chat, or / command…"
            disabled={pending}
            autoComplete="off"
            spellCheck={false}
          />
          <button type="submit" aria-label="Send" disabled={pending || !text.trim()}>
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

function TimelineEntry({
  item,
  onOpenDetails,
}: {
  item: WorkspaceSnapshot["timeline"][number];
  onOpenDetails: Props["onOpenDetails"];
}) {
  const long = item.message.length > 120 || item.message.includes("\n");
  const icon = item.kind === "move"
    ? "♟"
    : item.kind === "analysis"
      ? "⚙"
      : item.kind === "warning" || item.kind === "error"
        ? "!"
        : item.kind === "opening"
          ? "◈"
          : item.kind === "user"
            ? "→"
            : "·";
  const tone = item.kind === "warning" || item.kind === "error"
    ? "warning"
    : item.kind === "analysis"
      ? "analysis"
      : item.kind === "success"
        ? "success"
        : item.kind === "user" || item.kind === "assistant"
          ? "chat"
          : "default";
  return (
    <article className={`timeline-entry tone-${tone}`}>
      <span className="timeline-icon" aria-hidden="true">{icon}</span>
      <div>
        <strong>{item.title}</strong>
        {long ? (
          <details>
            <summary>Show details</summary>
            <p>{item.message}</p>
          </details>
        ) : <p>{item.message}</p>}
        {(item.kind === "analysis" || item.kind === "warning" || item.kind === "error") && (
          <button className="disclosure-link" type="button" onClick={() => onOpenDetails(item.kind === "analysis" ? "engine" : "decision")}>
            Open details
          </button>
        )}
      </div>
    </article>
  );
}

function OpeningContext({
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
    <article className="timeline-entry tone-opening">
      <span className="timeline-icon" aria-hidden="true">◈</span>
      <div>
        <strong>{workspace.opening.eco ? `${workspace.opening.eco} · ${name}` : name ?? "Opening context"}</strong>
        <p>
          {humanize(workspace.opening.moveSource ?? "start")}
          {" · "}{workspace.opening.bookContinuations.length} continuation(s)
        </p>
        {workspace.opening.recordId !== null && (
          <button
            className="disclosure-link"
            type="button"
            disabled={pending}
            onClick={() => workspace.opening.recordId !== null
              && (workspace.opening.isTagged
                ? onRemove(workspace.opening.recordId)
                : onAdd(workspace.opening.recordId))}
          >
            {workspace.opening.isTagged ? "Remove Rulebook label" : "Add Rulebook label"}
          </button>
        )}
      </div>
    </article>
  );
}

function humanize(value: string) {
  return value.replaceAll("-", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}
