import type { EvaluationSnapshot } from "../types/workspace";

interface EvaluationBarProps {
  evaluation: EvaluationSnapshot;
}

export function EvaluationBar({ evaluation }: EvaluationBarProps) {
  const label = evaluationLabel(evaluation);
  const percentage = evaluationPercentage(evaluation);
  return (
    <section className="evaluation-card" aria-label="Engine advantage">
      <output className="evaluation-score" aria-label="White-perspective score">{label}</output>
      <div
        className="evaluation-track"
        role="meter"
        aria-label={`White-perspective evaluation: ${label}`}
        aria-valuemin={-10}
        aria-valuemax={10}
        aria-valuenow={evaluation.centipawns === null ? undefined : evaluation.centipawns / 100}
      >
        <div className="evaluation-black" style={{ width: `${100 - percentage}%` }} />
        <div className="evaluation-white" style={{ width: `${percentage}%` }} />
        <span className="evaluation-center-marker" aria-hidden="true" />
      </div>
      <span className="evaluation-provenance">{analysisLabel(evaluation)}</span>
      {evaluation.errorMessage && <p className="inline-error">{evaluation.errorMessage}</p>}
    </section>
  );
}

function analysisLabel(evaluation: EvaluationSnapshot): string {
  const analysis = evaluation.analysis;
  if (!analysis) return evaluation.status === "engine-off" ? "No engine configured" : "White perspective";
  const depth = analysis.actualDepth ?? analysis.requestedDepth;
  return `${analysis.engineName}${depth === null ? "" : ` · depth ${depth}`}${analysis.timeMs === null ? "" : ` · ${analysis.timeMs} ms`}`;
}

export function evaluationLabel(evaluation: EvaluationSnapshot): string {
  if (evaluation.status === "engine-off") return "Engine off";
  if (evaluation.status === "error") return "Engine error";
  if (evaluation.status === "analyzing") return "Analyzing…";
  if (evaluation.status === "game-over") return "Game over";
  return scoreLabel(evaluation.centipawns, evaluation.mateIn);
}

function scoreLabel(cp: number | null, mate: number | null): string {
  if (mate !== null) return `${mate >= 0 ? "+" : "-"}M${Math.abs(mate)}`;
  if (cp === null) return "—";
  const pawns = cp / 100;
  if (pawns === 0) return "0.00";
  return `${pawns > 0 ? "+" : ""}${pawns.toFixed(2)}`;
}

function evaluationPercentage(evaluation: EvaluationSnapshot): number {
  if (evaluation.status !== "ready") return 50;
  if (evaluation.mateIn !== null) return evaluation.mateIn >= 0 ? 100 : 0;
  const clamped = Math.max(-1000, Math.min(1000, evaluation.centipawns ?? 0));
  return 50 + clamped / 20;
}
