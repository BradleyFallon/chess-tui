import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

import type { WorkspaceSnapshot } from "../types/workspace";

interface Props {
  workspace: WorkspaceSnapshot;
  pending: boolean;
  autoRespond: boolean;
  onAutoRespondChange: (enabled: boolean) => void;
  onOpponentModeChange: (mode: WorkspaceSnapshot["opponent"]["mode"]) => void;
  onAnalysisProfileChange: (profileId: string) => void;
  onAnalyse: () => void;
  onBack: () => void;
  onRestart: () => void;
}

export function CommandBar(props: Props) {
  const { workspace, pending } = props;
  const [open, setOpen] = useState(false);
  const shellRef = useRef<HTMLDivElement>(null);
  const profile = workspace.analysisSettings.profiles.find(
    (item) => item.id === workspace.analysisSettings.selectedProfileId,
  );

  useEffect(() => {
    if (!open) return;
    const close = (event: KeyboardEvent | MouseEvent) => {
      if (event instanceof KeyboardEvent && event.key !== "Escape") return;
      if (
        event instanceof MouseEvent
        && shellRef.current?.contains(event.target as Node)
      ) return;
      setOpen(false);
    };
    window.addEventListener("keydown", close);
    window.addEventListener("mousedown", close);
    return () => {
      window.removeEventListener("keydown", close);
      window.removeEventListener("mousedown", close);
    };
  }, [open]);

  const engineStatus = workspace.analysisSettings.status === "off"
    ? "Engine off"
    : workspace.analysisSettings.status === "error"
      ? "Engine error"
      : `${workspace.analysisSettings.engineName ?? "Engine"} ready`;

  return (
    <header className="command-bar">
      <div className="command-identity">
        <Link className="brand" to="/">Chess Flow</Link>
        <span className="command-divider" aria-hidden="true" />
        <strong>{workspace.rulebook.name}</strong>
        <span className="mode-label">Development</span>
      </div>
      <div className="command-actions">
        <div className="settings-shell" ref={shellRef}>
          <div className="status-chips" aria-label="Workspace settings summary">
            <button type="button" onClick={() => setOpen(true)}>
              {profile?.label ?? workspace.analysisSettings.selectedProfileId}
            </button>
            <button type="button" onClick={() => setOpen(true)}>
              {opponentLabel(workspace.opponent.mode)}
            </button>
            <button
              type="button"
              className={`engine-chip engine-${workspace.analysisSettings.status}`}
              onClick={() => setOpen(true)}
            >
              <span aria-hidden="true" />
              {engineStatus}
            </button>
          </div>
          <button
            className="settings-button"
            type="button"
            aria-haspopup="dialog"
            aria-expanded={open}
            onClick={() => setOpen((current) => !current)}
          >
            Settings
          </button>
          {open && (
            <SettingsPopover
              {...props}
              onClose={() => setOpen(false)}
            />
          )}
        </div>
        <span className="command-divider" aria-hidden="true" />
        <button
          className="command-button"
          disabled={pending || !workspace.navigation.canBack}
          onClick={props.onBack}
        >
          Back
        </button>
        <button
          className="command-button"
          disabled={pending || !workspace.navigation.canRestart}
          onClick={props.onRestart}
        >
          Restart
        </button>
      </div>
    </header>
  );
}

function SettingsPopover(props: Props & { onClose: () => void }) {
  const { workspace, pending } = props;
  return (
    <section
      className="settings-popover"
      role="dialog"
      aria-label="Development settings"
    >
      <div className="popover-heading">
        <strong>Settings</strong>
        <button type="button" aria-label="Close settings" onClick={props.onClose}>×</button>
      </div>
      <fieldset>
        <legend>Analysis</legend>
        <div className="segmented-options">
          {workspace.analysisSettings.profiles.map((profile) => {
            const selected =
              profile.id === workspace.analysisSettings.selectedProfileId;
            const unavailable =
              workspace.analysisSettings.status === "off" && !selected;
            return (
              <button
                type="button"
                key={profile.id}
                className={selected ? "selected" : undefined}
                disabled={pending || unavailable}
                title={unavailable ? "Configure an engine to use this profile." : profile.costDescription}
                onClick={() => props.onAnalysisProfileChange(profile.id)}
              >
                {profile.label}
                <small>D{profile.depth}</small>
              </button>
            );
          })}
        </div>
        <small className="setting-help">
          {workspace.analysisSettings.status === "off"
            ? "No engine is configured. Analysis profiles are unavailable."
            : "Profiles control local engine depth and compute time."}
        </small>
        <button
          className="settings-analyse"
          type="button"
          disabled={pending || workspace.analysisSettings.status === "off"}
          onClick={props.onAnalyse}
        >
          Analyze position
        </button>
      </fieldset>
      <fieldset>
        <legend>Opponent mode</legend>
        <div className="segmented-options three">
          {(["stored", "engine", "manual"] as const).map((mode) => {
            const selected = workspace.opponent.mode === mode;
            const unavailable = (
              (mode === "stored" && !workspace.opponent.storedReplyAvailable)
              || (mode === "engine" && !workspace.opponent.engineAvailable)
            ) && !selected;
            return (
              <button
                type="button"
                key={mode}
                className={selected ? "selected" : undefined}
                disabled={pending || unavailable}
                title={opponentExplanation(workspace, mode)}
                onClick={() => props.onOpponentModeChange(mode)}
              >
                {mode.charAt(0).toUpperCase() + mode.slice(1)}
              </button>
            );
          })}
        </div>
        <small className="setting-help">
          {opponentExplanation(workspace, workspace.opponent.mode)}
        </small>
      </fieldset>
      <label className="settings-toggle">
        <input
          type="checkbox"
          checked={props.autoRespond}
          disabled={pending || workspace.opponent.mode === "manual"}
          onChange={(event) => props.onAutoRespondChange(event.target.checked)}
        />
        <span>
          <strong>Auto-play opponent response</strong>
          <small>Respond after each controlled-side move.</small>
        </span>
      </label>
    </section>
  );
}

function opponentLabel(mode: WorkspaceSnapshot["opponent"]["mode"]) {
  if (mode === "stored") return "Stored opponent";
  if (mode === "engine") return "Engine opponent";
  return "Manual opponent";
}

function opponentExplanation(
  workspace: WorkspaceSnapshot,
  mode: WorkspaceSnapshot["opponent"]["mode"],
) {
  if (mode === "stored") {
    return workspace.opponent.storedReplyAvailable
      ? "A stored reply is available at this position."
      : "No stored reply exists at this position.";
  }
  if (mode === "engine") {
    return workspace.opponent.engineAvailable
      ? "The configured engine will choose the reply."
      : "No opponent engine is configured.";
  }
  return "Enter the opponent move on the board or in the composer.";
}
