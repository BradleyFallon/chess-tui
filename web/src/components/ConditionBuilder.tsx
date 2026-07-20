import { conditionKind, conditionKinds, conditionSummary, makeCondition, type ConditionKind } from "../authoring/conditionAst";
import type { ConditionExpression, PieceScript, PieceType } from "../types/workspace";

interface Props {
  value: ConditionExpression | null;
  pieces: PieceScript[];
  onChange: (value: ConditionExpression | null) => void;
}

export function ConditionBuilder({ value, pieces, onChange }: Props) {
  if (!value) {
    return (
      <button type="button" onClick={() => onChange({ attacked: "self" })}>
        Add trigger
      </button>
    );
  }
  const kind = conditionKind(value);
  return (
    <fieldset className="condition-builder">
      <legend>Trigger</legend>
      <label>
        Condition
        <select value={kind} onChange={(event) => onChange(makeCondition(event.target.value as ConditionKind))}>
          {conditionKinds.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
        </select>
      </label>
      <ConditionFields value={value} pieces={pieces} onChange={onChange} />
      <small>{conditionSummary(value)}</small>
      <button type="button" onClick={() => onChange(null)}>Whenever an attempt is legal</button>
    </fieldset>
  );
}

function ConditionFields({ value, pieces, onChange }: { value: ConditionExpression; pieces: PieceScript[]; onChange: (value: ConditionExpression) => void }) {
  const refs = ["self", ...pieces.map((piece) => piece.alias)];
  if ("attacked_by" in value) {
    if ("piece" in value.attacked_by) {
      return <PieceSelect label="Attacking piece" value={value.attacked_by.piece} refs={refs} onChange={(piece) => onChange({ attacked_by: { ...value.attacked_by, piece } })} />;
    }
    return <TypeSelect value={value.attacked_by.type} onChange={(type) => onChange({ attacked_by: { ...value.attacked_by, type } })} />;
  }
  if ("capturable" in value) return <PieceSelect label="Capturable piece" value={value.capturable} refs={refs.slice(1)} onChange={(capturable) => onChange({ capturable })} />;
  if ("attack_balance" in value) return <label>At least<input type="number" min={0} value={value.attack_balance.at_least} onChange={(event) => onChange({ attack_balance: { ...value.attack_balance, at_least: Number(event.target.value) } })} /></label>;
  if ("all" in value || "any" in value) {
    const key = "all" in value ? "all" : "any";
    const children = value[key];
    return (
      <div className="condition-group">
        {children.map((child, index) => (
          <ConditionBuilder key={index} value={child} pieces={pieces} onChange={(next) => {
            if (!next) return;
            onChange({ [key]: children.map((item, childIndex) => childIndex === index ? next : item) } as ConditionExpression);
          }} />
        ))}
        <button type="button" onClick={() => onChange({ [key]: [...children, { attacked: "self" }] } as ConditionExpression)}>Add child</button>
      </div>
    );
  }
  if ("not" in value) return <ConditionBuilder value={value.not} pieces={pieces} onChange={(not) => not && onChange({ not })} />;
  return null;
}

function PieceSelect({ label, value, refs, onChange }: { label: string; value: string; refs: string[]; onChange: (value: string) => void }) {
  return <label>{label}<select value={value} onChange={(event) => onChange(event.target.value)}>{refs.map((ref) => <option key={ref}>{ref}</option>)}</select></label>;
}

function TypeSelect({ value, onChange }: { value: PieceType; onChange: (value: PieceType) => void }) {
  return <label>Piece type<select value={value} onChange={(event) => onChange(event.target.value as PieceType)}>{["pawn", "knight", "bishop", "rook", "queen", "king"].map((type) => <option key={type}>{type}</option>)}</select></label>;
}
