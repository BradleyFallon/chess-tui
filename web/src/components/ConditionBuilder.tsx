import { useState } from "react";

import {
  conditionToExpression,
  defaultCondition,
  expressionToCondition,
  type ConditionNode,
} from "../authoring/conditionAst";
import type { StartingPieceSnapshot, WorkspaceSnapshot } from "../types/workspace";

interface Props {
  id: string;
  label: string;
  value: ConditionNode;
  pieces: StartingPieceSnapshot[];
  namedConditions: WorkspaceSnapshot["namedConditions"];
  onChange: (node: ConditionNode) => void;
}

export function ConditionBuilder({
  id,
  label,
  value,
  pieces,
  namedConditions,
  onChange,
}: Props) {
  const [source, setSource] = useState(
    () => JSON.stringify(conditionToExpression(value), null, 2),
  );
  const [sourceError, setSourceError] = useState<string | null>(null);
  const updateValue = (node: ConditionNode) => {
    setSource(JSON.stringify(conditionToExpression(node), null, 2));
    onChange(node);
  };

  return (
    <fieldset className="condition-builder">
      <legend>{label}</legend>
      <ConditionNodeEditor
        node={value}
        path={id}
        pieces={pieces}
        namedConditions={namedConditions}
        onChange={updateValue}
      />
      <details className="advanced-condition-source">
        <summary>Advanced condition source</summary>
        <label htmlFor={`${id}-source`}>Generated condition JSON</label>
        <textarea
          id={`${id}-source`}
          rows={7}
          value={source}
          onChange={(event) => setSource(event.target.value)}
        />
        {sourceError && <p className="inline-error" role="alert">{sourceError}</p>}
        <button
          type="button"
          onClick={() => {
            try {
              const parsed: unknown = JSON.parse(source);
              if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
                throw new Error("Condition source must be one JSON object.");
              }
              const node = expressionToCondition(parsed as Record<string, unknown>);
              setSourceError(null);
              updateValue(node);
            } catch (error) {
              setSourceError(
                error instanceof Error ? error.message : "Invalid condition source.",
              );
            }
          }}
        >
          Update visual condition
        </button>
      </details>
    </fieldset>
  );
}

function ConditionNodeEditor({
  node,
  path,
  pieces,
  namedConditions,
  onChange,
}: {
  node: ConditionNode;
  path: string;
  pieces: StartingPieceSnapshot[];
  namedConditions: WorkspaceSnapshot["namedConditions"];
  onChange: (node: ConditionNode) => void;
}) {
  const firstPiece = pieces[0]?.ref ?? "piece:white:pawn:a";
  const replaceKind = (kind: string) => {
    if (kind === "all" || kind === "any") {
      onChange({ kind, children: [defaultCondition(firstPiece)] });
    } else if (kind === "not") {
      onChange({ kind: "not", child: defaultCondition(firstPiece) });
    } else if (kind === "piece-at") {
      onChange({ kind, piece: firstPiece, square: "e4" });
    } else if (kind === "square") {
      onChange({ kind, square: "e4", state: "occupied" });
    } else if (kind === "occupied-by") {
      onChange({ kind, square: "e4", color: "black", pieceType: "pawn" });
    } else if (kind === "attacked") {
      onChange({ kind, piece: firstPiece });
    } else if (kind === "attacked-by") {
      onChange({ kind, target: firstPiece, attacker: pieces[1]?.ref ?? firstPiece });
    } else if (kind === "in-check") {
      onChange({ kind, color: "white" });
    } else if (kind === "named") {
      onChange({ kind, conditionId: namedConditions[0]?.id ?? "" });
    } else {
      onChange(defaultCondition(firstPiece));
    }
  };

  return (
    <div className={`condition-node condition-node-${node.kind}`}>
      <label htmlFor={`${path}-kind`}>Condition type</label>
      <select
        id={`${path}-kind`}
        value={node.kind}
        onChange={(event) => replaceKind(event.target.value)}
      >
        <option value="piece-moved">Piece has moved</option>
        <option value="piece-at">Piece is on square</option>
        <option value="square">Square occupancy</option>
        <option value="occupied-by">Square contains color and type</option>
        <option value="attacked">Piece is attacked</option>
        <option value="attacked-by">Piece is attacked by piece</option>
        <option value="in-check">Side is in check</option>
        <option value="named">Named condition</option>
        <option value="all">All conditions</option>
        <option value="any">Any condition</option>
        <option value="not">Not condition</option>
      </select>
      {renderFields(node, path, pieces, namedConditions, onChange)}
    </div>
  );
}

function renderFields(
  node: ConditionNode,
  path: string,
  pieces: StartingPieceSnapshot[],
  namedConditions: WorkspaceSnapshot["namedConditions"],
  onChange: (node: ConditionNode) => void,
) {
  if (node.kind === "piece-moved") {
    return (
      <div className="condition-fields">
        <PieceSelect id={`${path}-piece`} value={node.piece} pieces={pieces} onChange={(piece) => onChange({ ...node, piece })} />
        <label htmlFor={`${path}-movement`}>Movement</label>
        <select id={`${path}-movement`} value={node.negated ? "not-moved" : "moved"} onChange={(event) => onChange({ ...node, negated: event.target.value === "not-moved" })}>
          <option value="moved">has moved</option>
          <option value="not-moved">has not moved</option>
        </select>
      </div>
    );
  }
  if (node.kind === "piece-at") {
    return <div className="condition-fields"><PieceSelect id={`${path}-piece`} value={node.piece} pieces={pieces} onChange={(piece) => onChange({ ...node, piece })} /><SquareInput id={`${path}-square`} value={node.square} onChange={(square) => onChange({ ...node, square })} /></div>;
  }
  if (node.kind === "square") {
    return <div className="condition-fields"><SquareInput id={`${path}-square`} value={node.square} onChange={(square) => onChange({ ...node, square })} /><label htmlFor={`${path}-state`}>State</label><select id={`${path}-state`} value={node.state} onChange={(event) => onChange({ ...node, state: event.target.value as "occupied" | "empty" })}><option value="occupied">is occupied</option><option value="empty">is empty</option></select></div>;
  }
  if (node.kind === "occupied-by") {
    return <div className="condition-fields"><SquareInput id={`${path}-square`} value={node.square} onChange={(square) => onChange({ ...node, square })} /><label htmlFor={`${path}-color`}>Color</label><select id={`${path}-color`} value={node.color} onChange={(event) => onChange({ ...node, color: event.target.value as "white" | "black" })}><option value="white">White</option><option value="black">Black</option></select><label htmlFor={`${path}-type`}>Piece type</label><select id={`${path}-type`} value={node.pieceType} onChange={(event) => onChange({ ...node, pieceType: event.target.value })}>{["pawn", "knight", "bishop", "rook", "queen", "king"].map((piece) => <option key={piece}>{piece}</option>)}</select></div>;
  }
  if (node.kind === "attacked") {
    return <PieceSelect id={`${path}-piece`} value={node.piece} pieces={pieces} onChange={(piece) => onChange({ ...node, piece })} />;
  }
  if (node.kind === "attacked-by") {
    return <div className="condition-fields"><PieceSelect id={`${path}-target`} label="Target piece" value={node.target} pieces={pieces} onChange={(target) => onChange({ ...node, target })} /><PieceSelect id={`${path}-attacker`} label="Attacking piece" value={node.attacker} pieces={pieces} onChange={(attacker) => onChange({ ...node, attacker })} /></div>;
  }
  if (node.kind === "in-check") {
    return <><label htmlFor={`${path}-color`}>Side</label><select id={`${path}-color`} value={node.color} onChange={(event) => onChange({ ...node, color: event.target.value as "white" | "black" })}><option value="white">White</option><option value="black">Black</option></select></>;
  }
  if (node.kind === "named") {
    return <><label htmlFor={`${path}-named`}>Named condition</label><select id={`${path}-named`} value={node.conditionId} onChange={(event) => onChange({ ...node, conditionId: event.target.value })}>{namedConditions.map((condition) => <option key={condition.id} value={condition.id}>{condition.id} · {condition.summary}</option>)}</select></>;
  }
  if (node.kind === "not") {
    return <ConditionNodeEditor node={node.child} path={`${path}-not`} pieces={pieces} namedConditions={namedConditions} onChange={(child) => onChange({ ...node, child })} />;
  }
  return (
    <fieldset className="condition-group">
      <legend>{node.kind === "all" ? "ALL of the following" : "ANY of the following"}</legend>
      {node.children.map((child, index) => (
        <div className="condition-group-row" key={`${path}-${index}`}>
          <ConditionNodeEditor node={child} path={`${path}-${index}`} pieces={pieces} namedConditions={namedConditions} onChange={(nextChild) => onChange({ ...node, children: node.children.map((item, itemIndex) => itemIndex === index ? nextChild : item) })} />
          <button type="button" aria-label={`Remove condition ${index + 1}`} disabled={node.children.length === 1} onClick={() => onChange({ ...node, children: node.children.filter((_, itemIndex) => itemIndex !== index) })}>Remove</button>
        </div>
      ))}
      <button type="button" onClick={() => onChange({ ...node, children: [...node.children, defaultCondition(pieces[0]?.ref ?? "piece:white:pawn:a")] })}>Add condition</button>
    </fieldset>
  );
}

function PieceSelect({ id, label = "Piece", value, pieces, onChange }: { id: string; label?: string; value: string; pieces: StartingPieceSnapshot[]; onChange: (piece: string) => void }) {
  return <><label htmlFor={id}>{label}</label><select id={id} value={value} onChange={(event) => onChange(event.target.value)}>{pieces.map((piece) => <option key={piece.ref} value={piece.ref}>{piece.label}</option>)}</select></>;
}

function SquareInput({ id, value, onChange }: { id: string; value: string; onChange: (square: string) => void }) {
  return <><label htmlFor={id}>Square</label><input id={id} value={value} minLength={2} maxLength={2} onChange={(event) => onChange(event.target.value)} /></>;
}
