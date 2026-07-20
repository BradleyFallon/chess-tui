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
    localStorage.clear();
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

  it("labels an attacked piece with no defenders as undefended", async () => {
    renderApp({
      ...workspaceFixture,
      pieceScripts: workspaceFixture.pieceScripts.map((piece, index) => index
        ? piece
        : {
            ...piece,
            relationships: {
              ...piece.relationships,
              undefended: true,
              underDefended: true,
              defenderCount: 0,
            },
          }),
    });
    await screen.findByText("Move to d4");
    fireEvent.click(screen.getByText("Current board relationships"));
    expect(screen.getByText("Undefended")).toBeInTheDocument();
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

  it("preloads the guided wizard when editing an existing interrupt", async () => {
    renderApp();
    await screen.findByText("Move to d4");
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    expect(screen.getByRole("dialog", { name: /Edit interrupt/ })).toBeInTheDocument();
    expect(screen.getByLabelText("Rule ID")).toHaveValue("take-bishop");
    expect(screen.getByLabelText("Prerequisites")).toHaveValue("d-pawn.develop");
    fireEvent.click(screen.getByRole("button", { name: "Later step" }));
    fireEvent.click(screen.getByRole("button", { name: "Later step" }));
    expect(screen.getByLabelText("Capture type")).toHaveValue("bishop");
    fireEvent.click(screen.getByRole("button", { name: "Later step" }));
    expect(screen.getByLabelText("Why")).toHaveValue(
      "Capture a bishop when possible.",
    );
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

  it("renders the restored timeline, composer, and evaluation controls", async () => {
    renderApp({
      ...workspaceFixture,
      evaluation: {
        ...workspaceFixture.evaluation,
        status: "ready",
        centipawns: 42,
        previousCentipawns: 18,
        changeCentipawns: 24,
        engineName: "Stockfish",
        profileId: "quick",
        requestedDepth: 10,
        actualDepth: 10,
        nodes: 12000,
        timeMs: 45,
      },
      analysisSettings: {
        ...workspaceFixture.analysisSettings,
        status: "ready",
        engineName: "Stockfish",
      },
      positionAnalysis: {
        bookMoves: ["d4", "Nf3"],
        engineMoves: [
          {
            uci: "d2d4",
            san: "d4",
            centipawns: 42,
            mateIn: null,
            principalVariation: ["d2d4", "g8f6"],
          },
        ],
      },
    });
    expect(await screen.findByRole("complementary", {
      name: "Development timeline",
    })).toBeInTheDocument();
    expect(screen.getByLabelText("Enter move, chat, or command")).toBeInTheDocument();
    expect(screen.getByLabelText("Engine advantage")).toBeInTheDocument();
    expect(screen.getByLabelText("White-perspective score")).toHaveTextContent("+0.42");
    expect(screen.getByLabelText("Engine analysis strength")).toHaveValue("quick");
    expect(screen.getByText(/Stockfish · depth 10 · 45 ms · 12,000 nodes/)).toBeInTheDocument();
    expect(screen.getByText(/\+0.24 since the previous position/)).toBeInTheDocument();
    expect(screen.getByText("Engine candidates")).toBeInTheDocument();
    expect(screen.getByText("d4, Nf3")).toBeInTheDocument();
  });

  it("automatically requests the selected engine reply on the opponent turn", async () => {
    localStorage.setItem("chess-flow-development-auto-respond", "true");
    renderApp({
      ...workspaceFixture,
      position: {
        ...workspaceFixture.position,
        turn: "black",
        historySan: ["d4"],
      },
      decision: null,
      opponent: {
        mode: "engine",
        storedReplyAvailable: false,
        engineAvailable: true,
        lastSource: null,
      },
    });
    await screen.findByText("Black to move");
    await waitFor(() => expect(vi.mocked(fetch)).toHaveBeenCalledWith(
      expect.stringContaining("/opponent/next"),
      expect.objectContaining({ method: "POST" }),
    ));
  });
});
