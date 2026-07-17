import {
  type FormEvent,
  type KeyboardEvent,
  useEffect,
  useRef,
  useState,
} from "react";

import type {
  ActivitySnapshot,
  AvailableCommandSnapshot,
  AttemptSnapshot,
  ChatAttachment,
  ChatMessageSnapshot,
  OpeningContextAttachment,
  OpeningContextSnapshot,
  OpeningMatchSnapshot,
  OpeningTagSnapshot,
  PolicyItemSnapshot,
  PositionAnalysisSnapshot,
  TypedCommand,
  WorkspaceSnapshot,
} from "../types/workspace";

interface Props {
  workspace: WorkspaceSnapshot;
  pending: boolean;
  hintVisible: boolean;
  autoRespond: boolean;
  onAutoRespondChange: (enabled: boolean) => void;
  onSubmit: (text: string) => void;
  onExecute: (command: TypedCommand) => void;
  onAddOpeningTag: (recordId: number) => void;
  onRemoveOpeningTag: (recordId: number) => void;
}

type TimelineItem =
  | { type: "activity"; sequence: number; value: ActivitySnapshot }
  | { type: "chat"; sequence: number; value: ChatMessageSnapshot };

export function StatusFeed({
  workspace,
  pending,
  hintVisible,
  autoRespond,
  onAutoRespondChange,
  onSubmit,
  onExecute,
  onAddOpeningTag,
  onRemoveOpeningTag,
}: Props) {
  const feedRef = useRef<HTMLDivElement>(null);
  const composerRef = useRef<HTMLInputElement>(null);
  const [text, setText] = useState("");
  const [selectedCommand, setSelectedCommand] = useState(0);
  const commandMode = text.startsWith("/");
  const commandToken = commandMode ? text.split(/\s/, 1)[0].toLowerCase() : "";
  const visibleCommands = workspace.availableCommands.filter((command) =>
    command.slash.startsWith(commandToken),
  );
  const timeline: TimelineItem[] = [
    ...workspace.activity.map((value) => ({ type: "activity" as const, sequence: value.sequence, value })),
    ...workspace.chat.map((value) => ({ type: "chat" as const, sequence: value.sequence, value })),
  ].sort((left, right) => left.sequence - right.sequence);

  const send = (value: string) => {
    const trimmed = value.trim();
    if (!trimmed || pending) return;
    setText("");
    setSelectedCommand(0);
    onSubmit(trimmed);
  };
  const chooseCommand = (command: AvailableCommandSnapshot) => {
    if (command.arguments.length) {
      setText(`${command.slash} `);
      composerRef.current?.focus();
    } else {
      send(command.slash);
    }
  };
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (commandMode && !text.trim().includes(" ")) {
      const exact = workspace.availableCommands.find(
        (command) => command.slash === text.trim().toLowerCase(),
      );
      const selected = exact ?? visibleCommands[selectedCommand];
      if (selected) {
        chooseCommand(selected);
        return;
      }
    }
    send(text);
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
      setText("");
    }
  };

  useEffect(() => {
    if (feedRef.current) feedRef.current.scrollTop = feedRef.current.scrollHeight;
  }, [workspace.activity.length, workspace.chat.length, workspace.phase]);
  useEffect(() => {
    const focusComposerOnTyping = (event: globalThis.KeyboardEvent) => {
      if (
        pending || event.defaultPrevented || event.isComposing || event.metaKey ||
        event.ctrlKey || event.altKey || event.key.length !== 1 || event.key.trim() === ""
      ) return;
      const target = event.target;
      if (
        target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement ||
        target instanceof HTMLSelectElement ||
        (target instanceof HTMLElement && target.isContentEditable)
      ) return;
      event.preventDefault();
      composerRef.current?.focus();
      setText((current) => current + event.key);
      setSelectedCommand(0);
    };
    window.addEventListener("keydown", focusComposerOnTyping);
    return () => window.removeEventListener("keydown", focusComposerOnTyping);
  }, [pending]);

  return (
    <aside className="workspace-panel status-panel" aria-labelledby="status-heading">
      <div className="section-heading-row status-heading-row">
        <h2 id="status-heading">Game status</h2><span className="status-chip">live</span>
      </div>
      <section className="development-options" aria-labelledby="development-options-heading">
        <h3 id="development-options-heading">Options</h3>
        <label className="option-toggle">
          <input
            type="checkbox"
            checked={autoRespond}
            disabled={pending}
            onChange={(event) => onAutoRespondChange(event.target.checked)}
          />
          <span>
            <strong>Auto-respond</strong>
            <small>Play the opponent reply as soon as the flow hands over the turn.</small>
          </span>
        </label>
      </section>
      <div className="status-feed" role="log" aria-live="polite" ref={feedRef}>
        {timeline.map((item) => item.type === "activity"
          ? <ActivityEntry
              key={`activity-${item.value.id}-${item.sequence}`}
              item={item.value}
              openingTags={workspace.flow.openingTags}
              pending={pending}
              onAddOpeningTag={onAddOpeningTag}
              onRemoveOpeningTag={onRemoveOpeningTag}
            />
          : <ChatEntry key={item.value.id} message={item.value} />)}
        <CurrentStatus
          workspace={workspace}
          pending={pending}
          hintVisible={hintVisible}
          autoRespond={autoRespond}
          onExecute={onExecute}
        />
      </div>
      <div className="status-composer-shell">
        {commandMode && (
          <div className="command-menu" id="chat-command-menu" role="listbox" aria-label="Chat commands">
            {visibleCommands.length ? visibleCommands.map((command, index) => (
              <button
                className={index === selectedCommand ? "selected" : undefined}
                id={`chat-command-${command.id}`}
                key={command.id}
                type="button"
                role="option"
                aria-selected={index === selectedCommand}
                disabled={pending}
                onMouseEnter={() => setSelectedCommand(index)}
                onClick={() => chooseCommand(command)}
              >
                <strong>{command.usage}</strong>
                <span title={command.description}>{command.description}</span>
              </button>
            )) : <p className="command-menu-empty">No matching commands</p>}
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
            aria-activedescendant={commandMode && visibleCommands[selectedCommand]
              ? `chat-command-${visibleCommands[selectedCommand].id}` : undefined}
            value={text}
            onChange={(event) => { setText(event.target.value); setSelectedCommand(0); }}
            onKeyDown={handleComposerKeyDown}
            placeholder="Type a move or / command…"
            disabled={pending}
            autoComplete="off"
            spellCheck={false}
            enterKeyHint="send"
            data-move-composer="true"
          />
          <button type="submit" aria-label="Submit move" disabled={pending || !text.trim()}>
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m5 12 14-7-4 14-3-6-7-1Z" /><path d="m12 13 7-8" /></svg>
          </button>
        </form>
      </div>
    </aside>
  );
}

function ActivityEntry({
  item,
  openingTags,
  pending,
  onAddOpeningTag,
  onRemoveOpeningTag,
}: {
  item: ActivitySnapshot;
  openingTags: OpeningTagSnapshot[];
  pending: boolean;
  onAddOpeningTag: Props["onAddOpeningTag"];
  onRemoveOpeningTag: Props["onRemoveOpeningTag"];
}) {
  return <article className={`status-note status-note-${item.kind}`}>
    <span className="status-note-marker" aria-hidden="true" />
    <div><strong>{item.title}</strong><p>{item.message}</p>
      {item.attachment && <Attachment
        attachment={item.attachment}
        openingTags={openingTags}
        pending={pending}
        onAddOpeningTag={onAddOpeningTag}
        onRemoveOpeningTag={onRemoveOpeningTag}
      />}
    </div>
  </article>;
}

function ChatEntry({ message }: { message: ChatMessageSnapshot }) {
  return <article className={`chat-message chat-message-${message.role}`}>
    <div className="chat-role">{message.role}</div>
    <p>{message.text}</p>
    {message.attachment && <Attachment attachment={message.attachment} />}
  </article>;
}

function Attachment({
  attachment,
  openingTags,
  pending = false,
  onAddOpeningTag,
  onRemoveOpeningTag,
}: {
  attachment: ChatAttachment;
  openingTags?: OpeningTagSnapshot[];
  pending?: boolean;
  onAddOpeningTag?: Props["onAddOpeningTag"];
  onRemoveOpeningTag?: Props["onRemoveOpeningTag"];
}) {
  switch (attachment.kind) {
    case "opening-context": return <OpeningContext
      attachment={attachment}
      openingTags={openingTags}
      pending={pending}
      onAddOpeningTag={onAddOpeningTag}
      onRemoveOpeningTag={onRemoveOpeningTag}
    />;
    case "opening-list": return <div className="attachment-details">
      <span><strong>Primary:</strong> {attachment.primaryMatch?.name ?? "No exact named position"}</span>
      {attachment.matches.map((match) => <span key={match.recordId}>{match.eco} · {match.name}</span>)}
    </div>;
    case "defense-list": return <div className="attachment-details">
      <NameList label="Entered defenses" values={attachment.entered} />
      <NameList label="Book defenses still reachable" values={attachment.reachable} />
    </div>;
    case "book-details": return <div className="attachment-details">
      <span><strong>Last move in book:</strong> {bookAnswer(attachment.playedMoveInBook)}</span>
      <NameList label="Continuations" values={attachment.continuations.map((move) => move.san)} />
    </div>;
    case "book-history": return <div className="attachment-details">
      {attachment.entries.map((entry) => <span key={`${entry.ply}-${entry.uci}`}>
        <strong>{moveLabel(entry.ply, entry.san)}</strong> · {openingLabel(entry.context)}
        {entry.context.playedMoveInBook === null ? "" : ` · book ${entry.context.playedMoveInBook ? "yes" : "no"}`}
      </span>)}
      {attachment.firstPolicyWithoutBookPly !== null && <small>Policy first operated without book support at ply {attachment.firstPolicyWithoutBookPly}.</small>}
    </div>;
    case "position-analysis": return <PositionAnalysis analysis={attachment.analysis} />;
    case "decision-explanation": return <DecisionExplanation attachment={attachment} />;
    case "rule-details": return <RuleDetails item={attachment.rule} />;
    case "rule-list": return <RuleList groups={attachment.groups} />;
    case "decision-trace": return <ol className="attachment-list">{attachment.entries.map((entry, index) => <li key={`${index}-${entry}`}>{entry}</li>)}</ol>;
    case "position-details": return <div className="attachment-details"><code>{attachment.fen}</code><span>{attachment.turn} to move · ply {attachment.ply}{attachment.inCheck ? " · in check" : ""}</span><span>{attachment.legalMoves.length} legal moves</span></div>;
    case "command-list": return <ul className="attachment-list">{attachment.commands.map((command) => <li key={command.id}><strong>{command.usage}</strong> — {command.description}</li>)}</ul>;
    case "validation-error": return <p className="inline-error">{attachment.code}</p>;
  }
}

function OpeningContext({
  attachment,
  openingTags = [],
  pending,
  onAddOpeningTag,
  onRemoveOpeningTag,
}: {
  attachment: OpeningContextAttachment;
  openingTags?: OpeningTagSnapshot[];
  pending: boolean;
  onAddOpeningTag?: Props["onAddOpeningTag"];
  onRemoveOpeningTag?: Props["onRemoveOpeningTag"];
}) {
  const { context, entry, presentation } = attachment;
  const match = context.primaryMatch ?? context.lastKnownMatch;
  const currentMatch = context.primaryMatch;
  const tagged = currentMatch
    ? openingTags.some((tag) => tag.eco === currentMatch.eco && tag.name === currentMatch.name)
    : false;
  return <div className={`opening-attachment opening-attachment-${presentation}`}>
    {match
      ? <span><strong>{context.primaryMatch ? "Opening" : "Last known"}:</strong> {displayOpeningName(match)}</span>
      : <span><strong>No exact named opening position</strong></span>}
    {entry && <span><strong>Book move:</strong> {bookAnswer(context.playedMoveInBook)}</span>}
    {context.moveSource && <span><strong>Move source:</strong> {sourceLabel(context)}</span>}
    {currentMatch && onAddOpeningTag && onRemoveOpeningTag && (
      <button
        className="opening-tag-button"
        type="button"
        disabled={pending}
        onClick={() => tagged
          ? onRemoveOpeningTag(currentMatch.recordId)
          : onAddOpeningTag(currentMatch.recordId)}
      >
        {tagged ? "Remove flow label" : "Label this flow"}
      </button>
    )}
  </div>;
}

function displayOpeningName(match: OpeningMatchSnapshot): string {
  return match.variation ?? match.name;
}

function NameList({ label, values }: { label: string; values: string[] }) {
  const visible = values.slice(0, 8);
  const remaining = values.length - visible.length;
  return <span><strong>{label}:</strong> {visible.length ? visible.join(", ") : "None"}{remaining > 0 ? `, +${remaining} more` : ""}</span>;
}

function sourceLabel(context: OpeningContextSnapshot): string {
  if (context.moveSource === "book-and-policy") return `Policy rule ${context.policyRuleId ?? "unknown"}, supported by book`;
  if (context.moveSource === "policy-only") return `Policy rule ${context.policyRuleId ?? "unknown"}, without book support`;
  if (context.moveSource === "exact-override") return `Exact override ${context.exactOverrideId ?? "unknown"}`;
  if (context.moveSource === "recorded-branch") return `Recorded branch ${context.recordedReplyId ?? ""}`.trim();
  return context.moveSource?.replaceAll("-", " ") ?? "unknown";
}

function openingLabel(context: OpeningContextSnapshot): string {
  return context.primaryMatch?.name ?? (context.lastKnownMatch ? `last known ${context.lastKnownMatch.name}` : "no named opening");
}

function bookAnswer(value: boolean | null): string {
  return value === null ? "Not applicable" : value ? "yes" : "no";
}

function moveLabel(ply: number, san: string): string {
  const moveNumber = Math.ceil(ply / 2);
  return ply % 2 ? `${moveNumber}.${san}` : `${moveNumber}...${san}`;
}

function DecisionExplanation({ attachment }: { attachment: Extract<ChatAttachment, { kind: "decision-explanation" }> }) {
  return <div className="attachment-details">
    {attachment.selected && <span><strong>Selected:</strong> {attachment.selected.id}{attachment.selected.priority === null ? "" : ` · ${attachment.selected.priority}`}</span>}
    <RuleNames label="Higher-priority waiting" items={attachment.higherPriorityWaiting} />
    <RuleNames label="Shadowed active" items={attachment.shadowedActive} />
    <RuleNames label="Dormant" items={attachment.dormant} />
    {attachment.conditionReasons.map((reason) => <span key={reason}>{reason}</span>)}
    <small>Sources: {attachment.provenance.join(", ")}</small>
  </div>;
}

function RuleNames({ label, items }: { label: string; items: Array<{ id: string }> }) {
  return <span><strong>{label}:</strong> {items.length ? items.map((item) => item.id).join(", ") : "None"}</span>;
}

function RuleDetails({ item }: { item: PolicyItemSnapshot }) {
  return <div className="attachment-details"><strong>{item.id}</strong><span>{item.piece} → {item.destination}</span><span>{item.reason}</span>{item.note && <span>Note: {item.note}</span>}</div>;
}

function RuleList({ groups }: { groups: WorkspaceSnapshot["rules"] }) {
  const rows = [
    ["Selected", groups.selected ? [groups.selected] : []], ["Applies now", groups.appliesNow],
    ["Waiting", groups.waiting], ["Dormant", groups.dormant], ["Retired", groups.retired],
    ["Disabled", groups.disabled],
  ] as const;
  return <div className="attachment-details">{rows.map(([label, items]) => <span key={label}><strong>{label}:</strong> {items.length ? items.map((item) => item.id).join(", ") : "None"}</span>)}</div>;
}

function CurrentStatus({
  workspace,
  pending,
  hintVisible,
  autoRespond,
  onExecute,
}: Pick<Props, "workspace" | "pending" | "hintVisible" | "autoRespond" | "onExecute">) {
  if (workspace.phase === "policy-ready") {
    const side = capitalize(workspace.flow.side);
    return <article className="status-note status-note-prompt status-note-current"><span className="status-note-marker" aria-hidden="true" /><div>
      <strong>{side} to move</strong><p>{decisionMessage(workspace)}</p>
      {workspace.decision?.note && <p className="status-reason">Reason: {workspace.decision.note}</p>}
      {workspace.decision?.moveUci && <button className="hint-button" onClick={() => onExecute({ command: "hint_policy_move", source: "ui" })} disabled={pending || hintVisible} aria-label={hintVisible ? "Hint shown" : "Hint"} title="Highlight the piece to move"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 20h6M10 23h4M8.3 15.2A7 7 0 1 1 15.7 15.2C14.7 16 14 17 14 18h-4c0-1-.7-2-1.7-2.8Z" /></svg><span>Hint</span></button>}
    </div></article>;
  }
  if (workspace.phase === "opponent-ready") {
    const side = workspace.position.turn === "white" ? "White" : "Black";
    return <article className="status-note status-note-prompt status-note-current"><span className="status-note-marker" aria-hidden="true" /><div><strong>{side} to move</strong><p>{autoRespond ? "Auto-respond is choosing the opponent reply." : "Pick a reply on the board, or press Enter / choose Next and let the engine play it."}</p><button className="primary status-next-button" onClick={() => onExecute({ command: "next_opponent", source: "ui" })} disabled={pending} aria-keyshortcuts="Enter">Next</button></div></article>;
  }
  if (workspace.phase === "policy-result" && workspace.attempt) return <ResultActions attempt={workspace.attempt} pending={pending} onExecute={onExecute} />;
  return <article className="status-note status-note-current"><span className="status-note-marker" aria-hidden="true" /><div><strong>Game over</strong><p>{workspace.position.gameOver?.termination ?? "The line has ended."} {workspace.position.gameOver?.result}</p></div></article>;
}

function ResultActions({ attempt, pending, onExecute }: { attempt: AttemptSnapshot; pending: boolean; onExecute: Props["onExecute"] }) {
  const mismatch = attempt.result === "mismatch";
  return <article className="status-note status-note-action status-note-current"><span className="status-note-marker" aria-hidden="true" /><div>
    <strong>{mismatch ? "Rule mismatch" : "Flow frontier"}</strong>
    <p>You played {attempt.playedSan}.{attempt.expectedSan ? ` The selected policy expects ${attempt.expectedSan}.` : " No policy action resolves here."}</p>
    {attempt.note && <p>Reason: {attempt.note}</p>}<EngineReview attempt={attempt} />
    <div className="button-row status-actions"><button onClick={() => onExecute({ command: "retry_policy", source: "ui" })} disabled={pending}>Retry</button>{mismatch && <button className="primary" onClick={() => onExecute({ command: "continue_policy", source: "ui" })} disabled={pending}>Use selected move</button>}</div>
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
  return <div className="position-analysis">
    <AnalysisGroup title="Book moves" empty="No opening-index moves found.">{analysis.bookMoves.map((move) => <li key={move.uci}><strong>{move.san}</strong><span>{bookMoveLabel(move.source)}</span></li>)}</AnalysisGroup>
    <AnalysisGroup title="Engine best" empty="No engine candidates returned.">{analysis.engineMoves.map((move, index) => <li key={move.uci}><strong>{index + 1}. {move.san}</strong><span>{analysisScore(move.evaluationCp, move.mateIn)}</span></li>)}</AnalysisGroup>
  </div>;
}

function AnalysisGroup({ title, empty, children }: { title: string; empty: string; children: React.ReactNode }) {
  const items = Array.isArray(children) ? children : [children];
  return <section><h3>{title}</h3>{items.length ? <ol>{children}</ol> : <p>{empty}</p>}</section>;
}

function bookMoveLabel(source: string): string {
  if (source === "book-and-policy") return "opening index · selected policy";
  if (source === "opening-index") return "opening index";
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
