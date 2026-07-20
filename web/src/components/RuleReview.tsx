import type { DevelopmentRuleValidation, RuleDraftValidation } from "../types/workspace";

export function RuleReview({
  title,
  validation,
  applying,
  onApply,
  onBack,
  onCancel,
}: {
  title: string;
  validation: DevelopmentRuleValidation | RuleDraftValidation;
  applying: boolean;
  onApply: () => void;
  onBack: () => void;
  onCancel: () => void;
}) {
  return (
    <section className="rule-review" aria-labelledby="rule-review-heading">
      <span className="eyebrow">Review changes</span>
      <h3 id="rule-review-heading">{title}</h3>
      <p>{validation.summary}</p>
      {"readinessSummary" in validation
        ? <p><strong>Ready:</strong> {validation.readinessSummary}</p>
        : <>
          {validation.scopeSummary && <p><strong>Scope:</strong> {validation.scopeSummary}</p>}
          {validation.unlockSummary && <p><strong>Historical unlock:</strong> {validation.unlockSummary}</p>}
          <p><strong>Trigger:</strong> {validation.triggerSummary}</p>
          <p><strong>Expiration:</strong> {validation.expirationSummary}</p>
        </>}
      <dl className="review-impact">
        <div><dt>Current decision</dt><dd>{validation.currentDecision ?? "Opponent turn"}</dd></div>
        <div><dt>After this change</dt><dd>{validation.previewDecision ?? "Opponent turn"}</dd></div>
        <div><dt>Current plan</dt><dd>{validation.currentStructure ?? "No plan selected"}</dd></div>
        <div><dt>Preview plan</dt><dd>{validation.previewStructure ?? "No plan selected"}</dd></div>
        {validation.affectedOrder.length > 0 && (
          <div>
            <dt>Affected order</dt>
            <dd>{validation.affectedOrder.join(" → ")}</dd>
          </div>
        )}
      </dl>
      {validation.dependencies.length > 0 && <p><strong>Dependencies:</strong> {validation.dependencies.join(", ")}</p>}
      {"newlyApplicable" in validation && validation.newlyApplicable.length > 0 && <p><strong>Newly applicable:</strong> {validation.newlyApplicable.join(", ")}</p>}
      {"newlySuppressed" in validation && validation.newlySuppressed.length > 0 && <p><strong>Newly suppressed:</strong> {validation.newlySuppressed.join(", ")}</p>}
      {"newlyShadowed" in validation && validation.newlyShadowed.length > 0 && <p><strong>Newly shadowed:</strong> {validation.newlyShadowed.join(", ")}</p>}
      {validation.warnings.length > 0 && <ul className="validation-warning">{validation.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul>}
      <details>
        <summary>Generated condition</summary>
        <pre><code>{JSON.stringify(validation.conditionExpression, null, 2)}</code></pre>
      </details>
      <div className="button-row">
        <button className="primary" type="button" onClick={onApply} disabled={applying || !validation.valid}>Apply</button>
        <button type="button" onClick={onBack} disabled={applying}>Back</button>
        <button type="button" onClick={onCancel} disabled={applying}>Cancel</button>
      </div>
    </section>
  );
}
