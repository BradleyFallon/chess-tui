import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import {
  conditionToExpression,
  expressionToCondition,
  type ConditionNode,
} from "../authoring/conditionAst";
import { ConditionBuilder } from "../components/ConditionBuilder";
import { workspaceFixture } from "./fixtures";

test("condition AST round-trips nested all, any, and invisible not-moved mapping", () => {
  const expression = {
    all: [
      { not: { moved: "piece:white:pawn:c" } },
      {
        any: [
          { at: { piece: "piece:black:bishop:queenside", square: "f5" } },
          { at: { piece: "piece:black:bishop:queenside", square: "g4" } },
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
    negated: false,
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
  await userEvent.selectOptions(screen.getByLabelText("Movement"), "not-moved");
  expect(conditionToExpression(latest)).toEqual({
    not: { moved: "piece:white:pawn:d" },
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
