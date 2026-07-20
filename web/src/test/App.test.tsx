import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import App from "../App";
import { WorkspaceProvider } from "../develop/WorkspaceContext";
import { workspaceFixture } from "./fixtures";

function renderApp(workspace = workspaceFixture) {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
    ok: true,
    json: async () => workspace,
  }));
  render(
    <MemoryRouter initialEntries={["/develop"]}>
      <WorkspaceProvider><App /></WorkspaceProvider>
    </MemoryRouter>,
  );
}

describe("Opening Rule Engine workspace", () => {
  beforeEach(() => {
    sessionStorage.clear();
    vi.restoreAllMocks();
  });

  it("renders default development and multiple piece interrupts", async () => {
    renderApp();
    expect(await screen.findByText("Move to d4")).toBeInTheDocument();
    expect(screen.getByText("take-bishop")).toBeInTheDocument();
    expect(screen.getByText("Capture a bishop when possible.")).toBeInTheDocument();
  });

  it("renders opponent pieces as read-only relation references", async () => {
    renderApp();
    await screen.findByText("Move to d4");
    fireEvent.change(screen.getByLabelText("Inspect piece"), { target: { value: "black-queenside-bishop" } });
    expect(screen.getByText("Read-only opponent piece")).toBeInTheDocument();
    expect(screen.getByText(/Rulebook cannot move it/)).toBeInTheDocument();
  });

  it("shows under-defended relationship diagnostics", async () => {
    renderApp();
    await screen.findByText("Move to d4");
    fireEvent.click(screen.getByText("Current board relationships"));
    expect(screen.getByText("Under-defended")).toBeInTheDocument();
    expect(screen.getByText("black-b-pawn via b4c3")).toBeInTheDocument();
  });

  it("opens a guided interrupt wizard with required and ordered attempts", async () => {
    renderApp();
    await screen.findByText("Move to d4");
    fireEvent.click(screen.getByRole("button", { name: "Add interrupt" }));
    expect(screen.getByRole("dialog", { name: /Add interrupt/ })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Later step" }));
    expect(screen.getByText("Stop with an unhandled-rule frontier")).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText("Stop with an unhandled-rule frontier"));
    fireEvent.click(screen.getByRole("button", { name: "Later step" }));
    expect(screen.getByText("Ordered attempts")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add attempt" })).toBeInTheDocument();
  });

  it("offers exact-position interrupts through the same wizard", async () => {
    renderApp();
    await screen.findByText("Move to d4");
    fireEvent.click(screen.getByRole("button", { name: "Add interrupt" }));
    fireEvent.click(screen.getByRole("button", { name: "Exact position only" }));
    expect(screen.getByText("Exact after: start")).toBeInTheDocument();
  });

  it("renders typed frontier diagnostics", async () => {
    renderApp({
      ...workspaceFixture,
      decision: {
        status: "frontier",
        source: "frontier",
        moveUci: null,
        moveSan: null,
        instructionRef: "d-pawn.required",
        why: "Respond to pressure.",
        frontier: { reason: "unhandled-required-rule", explanation: "Every ordered attempt failed." },
        trace: ["Frontier reached."],
      },
    });
    expect((await screen.findAllByText("unhandled-required-rule")).length).toBeGreaterThan(0);
    expect(
      screen.getAllByText("Every ordered attempt failed.").length,
    ).toBeGreaterThan(0);
  });

  it("uses accessible Earlier and Later ordering controls", async () => {
    renderApp();
    await screen.findByText("Move to d4");
    fireEvent.click(screen.getByText("Interrupt order"));
    expect(screen.getAllByRole("button", { name: "Earlier" }).length).toBeGreaterThan(0);
    expect(screen.getAllByRole("button", { name: "Later" }).length).toBeGreaterThan(0);
  });

  it("authors the controlled side for a Black Rulebook", async () => {
    const black = {
      ...workspaceFixture.pieceScripts[1],
      authorable: true,
      development: {
        reference: "black-queenside-bishop.develop",
        to: "f5",
        requires: [],
        when: null,
        why: "Develop the bishop.",
        status: "selected" as const,
        explanation: "First legal instruction.",
        condition: null,
      },
    };
    const white = {
      ...workspaceFixture.pieceScripts[0],
      authorable: false,
      development: null,
      interrupts: [],
    };
    renderApp({
      ...workspaceFixture,
      rulebook: { ...workspaceFixture.rulebook, side: "black" },
      pieceScripts: [black, white],
      developmentOrder: ["black-queenside-bishop"],
      interruptOrder: [],
      decision: {
        status: "ready",
        source: "development",
        moveUci: "c8f5",
        moveSan: "Bf5",
        instructionRef: "black-queenside-bishop.develop",
        why: "Develop the bishop.",
        frontier: null,
        trace: ["Development black-queenside-bishop.develop: selected."],
      },
    });
    expect(await screen.findByText("Move to f5")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add interrupt" })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Inspect piece"), {
      target: { value: "d-pawn" },
    });
    expect(screen.getByText("Read-only opponent piece")).toBeInTheDocument();
  });

  it("keeps the current workspace after an API error", async () => {
    renderApp();
    await screen.findByText("Move to d4");
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: false,
      status: 422,
      json: async () => ({ error: { code: "INVALID_MOVE", message: "Illegal move", details: {} } }),
    } as Response);
    fireEvent.click(screen.getByRole("button", { name: "Analyze" }));
    await waitFor(() => expect(screen.getByText("Illegal move")).toBeInTheDocument());
    expect(screen.getByText("Move to d4")).toBeInTheDocument();
  });
});
