import { render, screen } from "@testing-library/react";

import { EvaluationBar } from "../components/EvaluationBar";
import { workspaceFixture } from "./fixtures";

test("evaluation shows the signed score, bar, engine, and search depth", () => {
  const { container } = render(<EvaluationBar evaluation={{
      ...workspaceFixture().evaluation,
      centipawns: 80,
      previousCentipawns: 20,
      changeCentipawns: 60,
    }} />);

  expect(screen.getByText("+0.80")).toBeInTheDocument();
  expect(screen.getByText("Stockfish 18 · depth 20 · 125 ms")).toBeInTheDocument();
  expect(screen.getByRole("meter", { name: "White-perspective evaluation: +0.80" })).toBeInTheDocument();
  expect(container.querySelector(".evaluation-center-marker")).toBeInTheDocument();
  expect(screen.queryByText("Previous")).not.toBeInTheDocument();
  expect(screen.queryByText("Change")).not.toBeInTheDocument();
});

test.each([
  ["mate", { status: "ready" as const, centipawns: null, mateIn: -2 }, "-M2"],
  ["engine off", { status: "engine-off" as const, centipawns: null, mateIn: null }, "Engine off"],
  ["engine error", { status: "error" as const, centipawns: null, mateIn: null, errorMessage: "engine exited" }, "Engine error"],
])("evaluation renders %s state", (_name, overrides, label) => {
  render(<EvaluationBar evaluation={{ ...workspaceFixture().evaluation, ...overrides }} />);
  expect(screen.getByText(label)).toBeInTheDocument();
  if ("errorMessage" in overrides && overrides.errorMessage) {
    expect(screen.getByText(overrides.errorMessage)).toBeInTheDocument();
  }
});
