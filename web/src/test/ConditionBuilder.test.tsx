import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { makeCondition } from "../authoring/conditionAst";
import { ConditionBuilder } from "../components/ConditionBuilder";
import { workspaceFixture } from "./fixtures";

describe("ConditionBuilder", () => {
  it("preserves unmoved as a distinct node", () => {
    expect(makeCondition("unmoved")).toEqual({ unmoved: "self" });
  });

  it("creates an under-defended trigger without JSON", () => {
    const onChange = vi.fn();
    render(<ConditionBuilder value={{ attacked: "self" }} pieces={workspaceFixture.pieceScripts} onChange={onChange} />);
    fireEvent.change(screen.getByLabelText("Condition"), { target: { value: "under_defended" } });
    expect(onChange).toHaveBeenCalledWith({ under_defended: "self" });
  });

  it("creates attacked-by-type and capture relationship triggers", () => {
    const onChange = vi.fn();
    const { rerender } = render(<ConditionBuilder value={{ attacked: "self" }} pieces={workspaceFixture.pieceScripts} onChange={onChange} />);
    fireEvent.change(screen.getByLabelText("Condition"), { target: { value: "attacked_by_type" } });
    expect(onChange).toHaveBeenCalledWith({ attacked_by: { target: "self", type: "pawn" } });
    rerender(<ConditionBuilder value={{ capturable: "black-queenside-bishop" }} pieces={workspaceFixture.pieceScripts} onChange={onChange} />);
    expect(screen.getByLabelText("Capturable piece")).toBeInTheDocument();
  });
});
