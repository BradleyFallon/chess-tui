import { useEffect, useRef, useState } from "react";

import type { PieceScript, WorkspaceSnapshot } from "../types/workspace";
import { evaluationLabel } from "./EvaluationBar";

export type DetailsTab = "decision" | "relations" | "engine" | "source";

export function DetailsDrawer({
  workspace,
  piece,
  open,
  tab,
  onTabChange,
  onClose,
}: {
  workspace: WorkspaceSnapshot;
  piece: PieceScript | null;
  open: boolean;
  tab: DetailsTab;
  onTabChange: (tab: DetailsTab) => void;
  onClose: () => void;
}) {
  const closeRef = useRef<HTMLButtonElement>(null);
  const [copied, setCopied] = useState(false);
  useEffect(() => {
    if (!open) return;
    closeRef.current?.focus();
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [onClose, open]);
  if (!open) return null;

  return (
    <div
      className="drawer-backdrop"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <aside className="details-drawer" role="dialog" aria-modal="true" aria-label="Details Drawer">
        <header className="drawer-heading">
          <div>
            <span className="eyebrow">Details Drawer</span>
            <h2>Advanced context</h2>
          </div>
          <button ref={closeRef} onClick={onClose}>Close</button>
        </header>
        <nav className="drawer-tabs" aria-label="Details sections">
          {(["decision", "relations", "engine", "source"] as const).map((value) => (
            <button
              key={value}
              className={tab === value ? "active" : undefined}
              aria-selected={tab === value}
              onClick={() => onTabChange(value)}
            >
              {value.charAt(0).toUpperCase() + value.slice(1)}
            </button>
          ))}
        </nav>
        <div className="drawer-body">
          {tab === "decision" && <DecisionDetails workspace={workspace} piece={piece} />}
          {tab === "relations" && <RelationDetails workspace={workspace} piece={piece} />}
          {tab === "engine" && <EngineDetails workspace={workspace} />}
          {tab === "source" && (
            <SourceDetails
              workspace={workspace}
              copied={copied}
              onCopy={() => {
                void navigator.clipboard.writeText(workspace.rulebookSource).then(() => setCopied(true));
              }}
            />
          )}
        </div>
      </aside>
    </div>
  );
}

function DecisionDetails({
  workspace,
  piece,
}: {
  workspace: WorkspaceSnapshot;
  piece: PieceScript | null;
}) {
  const selectedRule = piece?.interrupts.find(
    (rule) => rule.reference === workspace.decision?.instructionRef,
  );
  return (
    <div className="details-content">
      <DetailSection title="Selected instruction">
        <dl className="detail-grid">
          <div><dt>Status</dt><dd>{workspace.decision?.status ?? "Waiting"}</dd></div>
          <div><dt>Move</dt><dd>{workspace.decision?.moveSan ?? "—"}</dd></div>
          <div><dt>Source</dt><dd>{workspace.decision?.source ?? "—"}</dd></div>
          <div><dt>Reference</dt><dd><code>{workspace.decision?.instructionRef ?? "—"}</code></dd></div>
        </dl>
        {workspace.decision?.why && <p>{workspace.decision.why}</p>}
      </DetailSection>
      {workspace.decision?.frontier && (
        <DetailSection title="Frontier">
          <strong>{humanize(workspace.decision.frontier.reason)}</strong>
          <p>{workspace.decision.frontier.explanation}</p>
          {workspace.attempt && <pre>{JSON.stringify(workspace.attempt, null, 2)}</pre>}
        </DetailSection>
      )}
      {selectedRule && (
        <DetailSection title="Trigger and ordered attempts">
          <pre>{JSON.stringify({
            trigger: selectedRule.trigger,
            attempts: selectedRule.attempts,
          }, null, 2)}</pre>
        </DetailSection>
      )}
      <DetailSection title="Scheduler trace">
        <ol className="trace-list">
          {workspace.decision?.trace.length
            ? workspace.decision.trace.map((line, index) => <li key={`${index}-${line}`}>{line}</li>)
            : <li>No trace is available while waiting for the opponent.</li>}
        </ol>
      </DetailSection>
    </div>
  );
}

function RelationDetails({
  workspace,
  piece,
}: {
  workspace: WorkspaceSnapshot;
  piece: PieceScript | null;
}) {
  if (!piece) return <p>Select a piece to inspect its legal relationships.</p>;
  const facts = piece.relationships;
  const legalMoves = piece.currentSquare
    ? workspace.position.legalMovesUci.filter((move) => move.startsWith(piece.currentSquare ?? ""))
    : [];
  return (
    <div className="details-content">
      <DetailSection title={piece.label}>
        <dl className="detail-grid">
          <div><dt>Square</dt><dd>{piece.currentSquare ?? "Captured"}</dd></div>
          <div><dt>Attackers</dt><dd>{facts.attackerCount}</dd></div>
          <div><dt>Defenders</dt><dd>{facts.defenderCount}</dd></div>
          <div><dt>Balance</dt><dd>{facts.attackBalance}</dd></div>
          <div><dt>King pinned</dt><dd>{facts.kingPinned ? "Yes" : "No"}</dd></div>
          <div><dt>Pinning piece</dt><dd>{facts.pinnedBy ?? "—"}</dd></div>
        </dl>
      </DetailSection>
      <DetailSection title="Attackers">
        {facts.attackers.length ? (
          <ul className="detail-list">{facts.attackers.map((attacker) => (
            <li key={attacker.moveUci}><strong>{humanize(attacker.alias ?? attacker.piece)}</strong><code>{attacker.moveUci}</code></li>
          ))}</ul>
        ) : <p>No legal attackers.</p>}
      </DetailSection>
      <DetailSection title="Defenders by attacker">
        {facts.defendersByAttacker.length ? facts.defendersByAttacker.map((group) => (
          <div className="defender-group" key={group.attacker}>
            <strong>After {humanize(group.attackerAlias ?? group.attacker)} captures</strong>
            <ul className="detail-list">
              {group.defenders.map((defender) => <li key={defender.moveUci}><span>{humanize(defender.alias ?? defender.piece)}</span><code>{defender.moveUci}</code></li>)}
            </ul>
          </div>
        )) : <p>No legal recaptures are currently required.</p>}
      </DetailSection>
      <DetailSection title="Legal captures and moves">
        <p>Captures: {facts.attacks.map((attack) => attack.moveUci).join(", ") || "None"}</p>
        <p>Moves: {legalMoves.join(", ") || "None on the current turn"}</p>
      </DetailSection>
    </div>
  );
}

function EngineDetails({ workspace }: { workspace: WorkspaceSnapshot }) {
  const evaluation = workspace.evaluation;
  const profile = workspace.analysisSettings.profiles.find(
    (item) => item.id === workspace.analysisSettings.selectedProfileId,
  );
  return (
    <div className="details-content">
      <DetailSection title="Engine evaluation">
        <div className="engine-score-large">{evaluationLabel(evaluation)}</div>
        <dl className="detail-grid">
          <div><dt>Engine</dt><dd>{evaluation.engineName ?? workspace.analysisSettings.engineName ?? "Not configured"}</dd></div>
          <div><dt>Profile</dt><dd>{profile?.label ?? evaluation.profileId ?? "—"}</dd></div>
          <div><dt>Requested depth</dt><dd>{evaluation.requestedDepth ?? profile?.depth ?? "—"}</dd></div>
          <div><dt>Actual depth</dt><dd>{evaluation.actualDepth ?? "—"}</dd></div>
          <div><dt>Selective depth</dt><dd>{evaluation.selectiveDepth ?? "—"}</dd></div>
          <div><dt>Nodes</dt><dd>{evaluation.nodes?.toLocaleString() ?? "—"}</dd></div>
          <div><dt>NPS</dt><dd>{evaluation.nps?.toLocaleString() ?? "—"}</dd></div>
          <div><dt>Elapsed</dt><dd>{evaluation.timeMs !== null ? `${evaluation.timeMs} ms` : "—"}</dd></div>
          <div><dt>Best move</dt><dd>{evaluation.bestMoveSan ?? evaluation.bestMoveUci ?? "—"}</dd></div>
        </dl>
        {evaluation.message && <p className={evaluation.status === "error" ? "inline-error" : undefined}>{evaluation.message}</p>}
      </DetailSection>
      <DetailSection title="Candidate engine lines">
        {workspace.positionAnalysis?.engineMoves.length ? (
          <ol className="engine-lines">
            {workspace.positionAnalysis.engineMoves.map((move) => (
              <li key={move.uci}>
                <strong>{move.san}</strong>
                <span>{score(move.centipawns, move.mateIn)}</span>
                <code>{move.principalVariation.join(" ") || move.uci}</code>
              </li>
            ))}
          </ol>
        ) : <p>Run analysis to populate candidate lines.</p>}
      </DetailSection>
      <DetailSection title="Opening index">
        <p>{workspace.positionAnalysis?.bookMoves.join(", ") || "No indexed continuations in the latest analysis."}</p>
      </DetailSection>
    </div>
  );
}

function SourceDetails({
  workspace,
  copied,
  onCopy,
}: {
  workspace: WorkspaceSnapshot;
  copied: boolean;
  onCopy: () => void;
}) {
  return (
    <div className="details-content">
      <DetailSection title="Rulebook source">
        <dl className="detail-grid">
          <div><dt>File</dt><dd><code>{workspace.rulebook.path}</code></dd></div>
          <div><dt>Version</dt><dd>{workspace.rulebook.version}</dd></div>
        </dl>
        <div className="source-toolbar">
          <span>{workspace.rulebook.warnings.length} validation warning(s)</span>
          <button type="button" onClick={onCopy}>{copied ? "Copied" : "Copy source"}</button>
        </div>
        {workspace.rulebook.warnings.map((warning) => <p key={warning}>{warning}</p>)}
        <pre className="source-code">{workspace.rulebookSource}</pre>
      </DetailSection>
    </div>
  );
}

function DetailSection({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="detail-section">
      <h3>{title}</h3>
      {children}
    </section>
  );
}

function score(centipawns: number | null, mateIn: number | null) {
  if (mateIn !== null) return `${mateIn >= 0 ? "+" : "-"}M${Math.abs(mateIn)}`;
  if (centipawns === null) return "—";
  const pawns = centipawns / 100;
  return `${pawns > 0 ? "+" : ""}${pawns.toFixed(2)}`;
}

function humanize(value: string) {
  return value.replaceAll("-", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}
