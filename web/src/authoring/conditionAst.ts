import type { ConditionExpression, PieceType } from "../types/workspace";

export type ConditionKind =
  | "moved" | "unmoved" | "captured" | "at" | "occupied" | "empty"
  | "occupied_by" | "in_check" | "last_move" | "attacked"
  | "attacked_by_piece" | "attacked_by_type" | "undefended"
  | "under_defended" | "attack_balance" | "capturable" | "all" | "any" | "not";

export const conditionKinds: Array<{ value: ConditionKind; label: string }> = [
  { value: "attacked", label: "This piece is attacked" },
  { value: "attacked_by_type", label: "Attacked by a piece type" },
  { value: "attacked_by_piece", label: "Attacked by a selected piece" },
  { value: "under_defended", label: "Attackers outnumber defenders" },
  { value: "undefended", label: "This piece has no defenders" },
  { value: "attack_balance", label: "Attack balance reaches a threshold" },
  { value: "capturable", label: "A selected enemy piece is capturable" },
  { value: "moved", label: "Original piece has moved" },
  { value: "unmoved", label: "Original piece is unmoved" },
  { value: "captured", label: "Original piece is captured" },
  { value: "at", label: "Original piece is on a square" },
  { value: "occupied", label: "Square is occupied" },
  { value: "empty", label: "Square is empty" },
  { value: "occupied_by", label: "Square is occupied by type" },
  { value: "in_check", label: "Side is in check" },
  { value: "last_move", label: "Last move was piece to square" },
  { value: "all", label: "All conditions" },
  { value: "any", label: "Any condition" },
  { value: "not", label: "Not" },
];

export function makeCondition(kind: ConditionKind): ConditionExpression {
  const piece = "self";
  const type: PieceType = "pawn";
  switch (kind) {
    case "moved": return { moved: piece };
    case "unmoved": return { unmoved: piece };
    case "captured": return { captured: piece };
    case "at": return { at: { piece, square: "e4" } };
    case "occupied": return { occupied: "e4" };
    case "empty": return { empty: "e4" };
    case "occupied_by": return { occupied_by: { square: "e4", color: "black", type } };
    case "in_check": return { in_check: "white" };
    case "last_move": return { last_move: { piece, to: "e4" } };
    case "attacked": return { attacked: piece };
    case "attacked_by_piece": return { attacked_by: { target: piece, piece: "piece:black:pawn:d" } };
    case "attacked_by_type": return { attacked_by: { target: piece, type } };
    case "undefended": return { undefended: piece };
    case "under_defended": return { under_defended: piece };
    case "attack_balance": return { attack_balance: { target: piece, at_least: 1 } };
    case "capturable": return { capturable: "piece:black:bishop:queenside" };
    case "all": return { all: [{ attacked: piece }] };
    case "any": return { any: [{ attacked: piece }] };
    case "not": return { not: { attacked: piece } };
  }
}

export function conditionKind(value: ConditionExpression): ConditionKind {
  if ("attacked_by" in value) return "piece" in value.attacked_by ? "attacked_by_piece" : "attacked_by_type";
  return Object.keys(value)[0] as ConditionKind;
}

export function conditionSummary(value: ConditionExpression): string {
  if ("under_defended" in value) return `${value.under_defended} is under-defended`;
  if ("undefended" in value) return `${value.undefended} has no legal defenders`;
  if ("attacked" in value) return `${value.attacked} is legally attacked`;
  if ("attacked_by" in value) {
    const source = "piece" in value.attacked_by ? value.attacked_by.piece : value.attacked_by.type;
    return `${value.attacked_by.target} is attacked by ${source}`;
  }
  if ("attack_balance" in value) return `${value.attack_balance.target} balance ≥ ${value.attack_balance.at_least}`;
  if ("capturable" in value) return `${value.capturable} is uniquely capturable`;
  if ("unmoved" in value) return `${value.unmoved} is unmoved`;
  if ("moved" in value) return `${value.moved} has moved`;
  if ("captured" in value) return `${value.captured} is captured`;
  if ("all" in value) return `All: ${value.all.map(conditionSummary).join("; ")}`;
  if ("any" in value) return `Any: ${value.any.map(conditionSummary).join("; ")}`;
  if ("not" in value) return `Not: ${conditionSummary(value.not)}`;
  return JSON.stringify(value);
}
