import type { ConditionExpression } from "../types/workspace";

export type ConditionNode =
  | { kind: "piece-moved"; piece: string; negated: boolean }
  | { kind: "piece-at"; piece: string; square: string }
  | { kind: "square"; square: string; state: "occupied" | "empty" }
  | { kind: "occupied-by"; square: string; color: "white" | "black"; pieceType: string }
  | { kind: "attacked"; piece: string }
  | { kind: "attacked-by"; target: string; attacker: string }
  | { kind: "in-check"; color: "white" | "black" }
  | { kind: "named"; conditionId: string }
  | { kind: "all" | "any"; children: ConditionNode[] }
  | { kind: "not"; child: ConditionNode };

export function defaultCondition(piece: string): ConditionNode {
  return { kind: "piece-moved", piece, negated: false };
}

export function conditionToExpression(node: ConditionNode): ConditionExpression {
  switch (node.kind) {
    case "piece-moved":
      return node.negated
        ? { not: { moved: node.piece } }
        : { moved: node.piece };
    case "piece-at":
      return { at: { piece: node.piece, square: node.square } };
    case "square":
      return { [node.state]: node.square };
    case "occupied-by":
      return {
        occupied_by: {
          square: node.square,
          color: node.color,
          type: node.pieceType,
        },
      };
    case "attacked":
      return { attacked: node.piece };
    case "attacked-by":
      return { attacked_by: { target: node.target, attacker: node.attacker } };
    case "in-check":
      return { in_check: node.color };
    case "named":
      return { condition: node.conditionId };
    case "all":
    case "any":
      return { [node.kind]: node.children.map(conditionToExpression) };
    case "not":
      return { not: conditionToExpression(node.child) };
  }
}

export function expressionToCondition(expression: ConditionExpression): ConditionNode {
  const entries = Object.entries(expression);
  if (entries.length !== 1) throw new Error("A condition must contain exactly one operator.");
  const [kind, value] = entries[0];
  if (kind === "moved" && typeof value === "string") {
    return { kind: "piece-moved", piece: value, negated: false };
  }
  if (kind === "unmoved" && typeof value === "string") {
    return { kind: "piece-moved", piece: value, negated: true };
  }
  if (kind === "at" && isRecord(value) && typeof value.piece === "string" && typeof value.square === "string") {
    return { kind: "piece-at", piece: value.piece, square: value.square };
  }
  if ((kind === "occupied" || kind === "empty") && typeof value === "string") {
    return { kind: "square", square: value, state: kind };
  }
  if (
    kind === "occupied_by"
    && isRecord(value)
    && typeof value.square === "string"
    && (value.color === "white" || value.color === "black")
    && typeof value.type === "string"
  ) {
    return {
      kind: "occupied-by",
      square: value.square,
      color: value.color,
      pieceType: value.type,
    };
  }
  if (kind === "attacked" && typeof value === "string") {
    return { kind: "attacked", piece: value };
  }
  if (
    kind === "attacked_by"
    && isRecord(value)
    && typeof value.target === "string"
    && typeof value.attacker === "string"
  ) {
    return { kind: "attacked-by", target: value.target, attacker: value.attacker };
  }
  if (kind === "in_check" && (value === "white" || value === "black")) {
    return { kind: "in-check", color: value };
  }
  if (kind === "condition" && typeof value === "string") {
    return { kind: "named", conditionId: value };
  }
  if ((kind === "all" || kind === "any") && Array.isArray(value) && value.length > 0) {
    return {
      kind,
      children: value.map((item) => {
        if (!isRecord(item)) throw new Error(`${kind.toUpperCase()} contains an invalid child.`);
        return expressionToCondition(item);
      }),
    };
  }
  if (kind === "not" && isRecord(value)) {
    if (Object.keys(value).length === 1 && typeof value.moved === "string") {
      return { kind: "piece-moved", piece: value.moved, negated: true };
    }
    return { kind: "not", child: expressionToCondition(value) };
  }
  throw new Error(`Condition operator ${kind} is not supported by the visual builder.`);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}
