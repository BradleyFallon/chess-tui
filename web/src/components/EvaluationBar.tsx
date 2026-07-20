import type { WorkspaceSnapshot } from "../types/workspace";

type Evaluation = WorkspaceSnapshot["evaluation"];

export function EvaluationBar({
  evaluation,
  onOpenDetails,
}: {
  evaluation: Evaluation;
  onOpenDetails?: () => void;
}) {
  const label = evaluationLabel(evaluation);
  const percentage = evaluationPercentage(evaluation);
  return (
    <section
      className={`evaluation-bar evaluation-${evaluation.status}`}
      aria-label="Engine advantage"
    >
      <div
        className="evaluation-track"
        role="meter"
        aria-label={`White-perspective evaluation: ${label}`}
        aria-valuemin={-10}
        aria-valuemax={10}
        aria-valuenow={
          evaluation.centipawns === null
            ? undefined
            : evaluation.centipawns / 100
        }
      >
        <div className="evaluation-black" style={{ height: `${100 - percentage}%` }} />
        <div className="evaluation-white" style={{ height: `${percentage}%` }} />
        <span className="evaluation-center-marker" aria-hidden="true" />
      </div>
      <button
        type="button"
        className="evaluation-score"
        aria-label="White-perspective score"
        title={analysisLabel(evaluation)}
        onClick={onOpenDetails}
      >
        {label}
      </button>
    </section>
  );
}

function analysisLabel(evaluation: Evaluation): string {
  if (evaluation.status === "off") return "No engine configured";
  const details = [
    evaluation.engineName,
    evaluation.actualDepth !== null
      ? `depth ${evaluation.actualDepth}`
      : evaluation.requestedDepth !== null
        ? `requested ${evaluation.requestedDepth}`
        : null,
    evaluation.timeMs !== null ? `${evaluation.timeMs} ms` : null,
    evaluation.nodes !== null
      ? `${evaluation.nodes.toLocaleString()} nodes`
      : null,
  ].filter(Boolean);
  return details.join(" · ") || "White perspective";
}

export function evaluationLabel(evaluation: Evaluation): string {
  if (evaluation.status === "off") return "Engine off";
  if (evaluation.status === "error") return "Engine error";
  if (evaluation.mateIn !== null) {
    return `${evaluation.mateIn >= 0 ? "+" : "-"}M${Math.abs(evaluation.mateIn)}`;
  }
  if (evaluation.centipawns === null) return "—";
  const pawns = evaluation.centipawns / 100;
  return `${pawns > 0 ? "+" : ""}${pawns.toFixed(2)}`;
}

function evaluationPercentage(evaluation: Evaluation): number {
  if (evaluation.status !== "ready") return 50;
  if (evaluation.mateIn !== null) return evaluation.mateIn >= 0 ? 100 : 0;
  const clamped = Math.max(
    -1000,
    Math.min(1000, evaluation.centipawns ?? 0),
  );
  return 50 + clamped / 20;
}
