import type { AttemptSnapshot } from "../types/workspace";

interface ResultControlsProps {
  attempt: AttemptSnapshot;
  pending: boolean;
  onRetry: () => void;
  onKeep: () => void;
  onContinue: () => void;
}

export function ResultControls({ attempt, pending, onRetry, onKeep, onContinue }: ResultControlsProps) {
  const correct = attempt.result === "correct";
  const mismatch = attempt.result.startsWith("mismatch");
  return (
    <section className={`result-card result-${correct ? "correct" : "attention"}`} aria-labelledby="result-heading">
      <div>
        <span className="eyebrow">White result</span>
        <h2 id="result-heading">{attempt.result.replaceAll("-", " ")}</h2>
      </div>
      <dl className="result-moves">
        <div><dt>You played</dt><dd>{attempt.playedSan}</dd></div>
        <div><dt>Expected</dt><dd>{attempt.expectedSan ?? "No saved rule"}</dd></div>
        <div><dt>Source</dt><dd>{attempt.source}</dd></div>
      </dl>
      {attempt.engineReview && <EngineReview review={attempt.engineReview} />}
      <div className="button-row">
        {correct && <button className="primary" onClick={onContinue} disabled={pending}>Continue</button>}
        {mismatch && <>
          <button onClick={onRetry} disabled={pending}>Retry</button>
          <button className="primary" onClick={onKeep} disabled={pending}>Continue with expected move</button>
        </>}
        {!correct && !mismatch && <button onClick={onRetry} disabled={pending}>Return to decision</button>}
      </div>
    </section>
  );
}

function EngineReview({ review }: { review: NonNullable<AttemptSnapshot["engineReview"]> }) {
  if (review.status === "engine-off") return <p className="muted">Engine review: engine off</p>;
  if (review.status === "error") return <p className="inline-error">Engine review: {review.errorMessage}</p>;
  return (
    <div className="engine-review">
      <strong>Engine review: {review.quality}</strong>
      <span>{review.lossCp === null ? "Mate score" : `${(review.lossCp / 100).toFixed(2)} pawns lost`}</span>
      <span>Best: {review.bestMoveSan}</span>
    </div>
  );
}
