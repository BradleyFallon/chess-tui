import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import {
  conditionToExpression,
  expressionToCondition,
  type ConditionNode,
} from "../authoring/conditionAst";
import { ConditionBuilder } from "../components/ConditionBuilder";
import { workspaceFixture } from "./fixtures";

test.each([
  { moved: "piece:white:pawn:c" },
  { unmoved: "piece:white:pawn:c" },
  { captured: "piece:black:bishop:queenside" },
  { at: { piece: "piece:black:bishop:queenside", square: "f5" } },
  { occupied: "e4" },
  { empty: "d5" },
  { occupied_by: { square: "c6", color: "black", type: "knight" } },
  { attacked: "piece:white:bishop:queenside" },
  { attacked_by: { target: "piece:white:pawn:c", attacker: "piece:black:bishop:queenside" } },
  { in_check: "black" },
  { last_move: { piece: "piece:black:pawn:e", to: "e5" } },
  { condition: "center-ready" },
])("condition AST round-trips atomic operator %#", (expression) => {
  expect(conditionToExpression(expressionToCondition(expression))).toEqual(expression);
});

test("condition AST round-trips nested all, any, and not", () => {
  const expression = {
    all: [
      { unmoved: "piece:white:pawn:c" },
      {
        any: [
          { at: { piece: "piece:black:bishop:queenside", square: "f5" } },
          { not: { captured: "piece:black:bishop:queenside" } },
        ],
      },
    ],
  };
  expect(conditionToExpression(expressionToCondition(expression))).toEqual(expression);
});

test("visual builder edits one AST and advanced source reparses it", async () => {
  const workspace = workspaceFixture();
  let latest: ConditionNode = {
    kind: "piece-moved",
    piece: "piece:white:pawn:d",
  };
  const view = render(
    <ConditionBuilder
      id="test-condition"
      label="When should this happen?"
      value={latest}
      pieces={workspace.startingPieces}
      namedConditions={workspace.namedConditions}
      onChange={(node) => { latest = node; }}
    />,
  );
  const pieceSelect = screen.getByLabelText("Piece");
  expect(within(pieceSelect).getByRole("group", { name: "White pieces" })).toBeInTheDocument();
  expect(within(pieceSelect).getByRole("group", { name: "Black pieces" })).toBeInTheDocument();
  expect(within(pieceSelect).getByRole("option", { name: /Black queenside bishop/ })).toBeInTheDocument();
  expect(screen.getByLabelText("Condition type")).not.toContainHTML('value="named"');
  await userEvent.selectOptions(screen.getByLabelText("Condition type"), "piece-unmoved");
  expect(conditionToExpression(latest)).toEqual({
    unmoved: "piece:white:pawn:d",
  });

  await userEvent.click(screen.getByText("Advanced condition source"));
  const source = screen.getByLabelText("Generated condition JSON");
  fireEvent.change(source, {
    target: {
      value: JSON.stringify({ attacked: "piece:white:bishop:queenside" }),
    },
  });
  await userEvent.click(screen.getByRole("button", { name: "Update visual condition" }));
  expect(conditionToExpression(latest)).toEqual({
    attacked: "piece:white:bishop:queenside",
  });

  view.rerender(
    <ConditionBuilder
      id="test-condition"
      label="When should this happen?"
      value={latest}
      pieces={workspace.startingPieces}
      namedConditions={workspace.namedConditions}
      onChange={(node) => { latest = node; }}
    />,
  );
  expect(screen.getByLabelText("Condition type")).toHaveValue("attacked");
});
