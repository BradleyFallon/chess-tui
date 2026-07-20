import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import App from "../App";
import { WorkspaceProvider } from "../develop/WorkspaceContext";
import type { PieceScript, WorkspaceSnapshot } from "../types/workspace";
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

describe("compact Development Mode workspace", () => {
  beforeEach(() => {
    sessionStorage.clear();
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it("separates Piece Inspector and Rulebook Outline tabs", async () => {
    renderApp();
    expect(await screen.findByLabelText("Piece Inspector")).toBeInTheDocument();
    expect(screen.queryByLabelText("Rulebook Outline")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Rulebook" }));
    expect(screen.getByLabelText("Rulebook Outline")).toBeInTheDocument();
    expect(screen.queryByLabelText("Piece Inspector")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Piece" }));
    expect(screen.getByLabelText("Piece Inspector")).toBeInTheDocument();
  });

  it("renders compact draggable development order rows", async () => {
    renderApp();
    await screen.findByLabelText("Piece Inspector");
    fireEvent.click(screen.getByRole("button", { name: "Rulebook" }));

    const list = screen.getByRole("list", { name: "Development order" });
    const row = within(list).getByRole("listitem");
    expect(row).toHaveAttribute("draggable", "true");
    expect(within(row).getByText("D Pawn")).toBeInTheDocument();
    expect(within(row).getByText("d4")).toBeInTheDocument();
    expect(within(row).getByLabelText("Reorder d-pawn")).toBeInTheDocument();
  });

  it("persists a native drag reorder through the existing endpoint", async () => {
    renderApp(withSecondDevelopment());
    await screen.findByLabelText("Piece Inspector");
    fireEvent.click(screen.getByRole("button", { name: "Rulebook" }));
    vi.mocked(fetch).mockClear();

    const rows = within(screen.getByRole("list", {
      name: "Development order",
    })).getAllByRole("listitem");
    fireEvent.dragStart(rows[0]);
    fireEvent.dragOver(rows[1]);
    fireEvent.drop(rows[1]);

    await waitFor(() => expect(vi.mocked(fetch)).toHaveBeenCalledWith(
      expect.stringContaining("/orders/development"),
      expect.objectContaining({
        method: "PUT",
        body: JSON.stringify({ aliases: ["e-pawn", "d-pawn"] }),
      }),
    ));
  });

  it("opens settings in a popover and closes it with Escape", async () => {
    renderApp();
    await screen.findByLabelText("Piece Inspector");
    expect(screen.queryByRole("dialog", { name: "Development settings" })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Settings" }));
    const popover = screen.getByRole("dialog", { name: "Development settings" });
    expect(within(popover).getByText("Analysis")).toBeInTheDocument();
    expect(within(popover).getByText("Opponent mode")).toBeInTheDocument();
    expect(within(popover).getByText("Auto-play opponent response")).toBeInTheDocument();
    expect(within(popover).getByRole("button", { name: "Engine" })).toBeDisabled();

    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.queryByRole("dialog", { name: "Development settings" })).not.toBeInTheDocument();
  });

  it("uses focused editors instead of expanding the Piece Inspector", async () => {
    renderApp();
    await screen.findByLabelText("Piece Inspector");
    fireEvent.click(screen.getByRole("button", {
      name: "Edit default development, d4, selected",
    }));

    expect(screen.getByLabelText("Development editor")).toBeInTheDocument();
    expect(screen.queryByLabelText("Piece Inspector")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Destination")).toHaveValue("d4");

    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.getByLabelText("Piece Inspector")).toBeInTheDocument();
  });

  it("opens compact interrupt rows in the focused interrupt editor", async () => {
    renderApp();
    await screen.findByLabelText("Piece Inspector");
    fireEvent.click(screen.getByRole("button", { name: /Take Bishop/ }));

    expect(screen.getByLabelText("Interrupt editor")).toBeInTheDocument();
    expect(screen.getByLabelText("Rule name")).toHaveValue("take-bishop");
    expect(screen.getByLabelText("Capture type")).toHaveValue("bishop");
    expect(screen.getByLabelText("Why")).toHaveValue(
      "Capture a bishop when possible.",
    );
  });

  it("opens the Details Drawer on the requested tab", async () => {
    renderApp();
    await screen.findByLabelText("Piece Inspector");
    fireEvent.click(screen.getByRole("button", { name: /Relationships/ }));

    const drawer = screen.getByRole("dialog", { name: "Details Drawer" });
    expect(drawer).toBeInTheDocument();
    expect(within(drawer).getByRole("button", { name: "Relations" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(within(drawer).getByText("Black B Pawn")).toBeInTheDocument();

    fireEvent.click(within(drawer).getByRole("button", { name: "Source" }));
    expect(within(drawer).getByText("Rulebook source")).toBeInTheDocument();
    expect(within(drawer).getByText("flows/london.toml")).toBeInTheDocument();
  });

  it("selects a board piece and returns the sidebar to Piece", async () => {
    renderApp();
    await screen.findByLabelText("Piece Inspector");
    fireEvent.click(screen.getByRole("button", { name: "Rulebook" }));
    const blackBishopSquare = await waitFor(() => {
      const square = document.querySelector<HTMLElement>("[data-square='c8']");
      expect(square).not.toBeNull();
      return square as HTMLElement;
    });

    fireEvent.click(blackBishopSquare);
    expect(screen.getByLabelText("Piece Inspector")).toBeInTheDocument();
    expect(screen.getByText("Read-only opponent piece")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Piece" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
  });

  it("keeps the Coach Panel composer wired to chat/SAN input", async () => {
    renderApp();
    expect(await screen.findByRole("complementary", {
      name: "Coach Panel",
    })).toBeInTheDocument();
    vi.mocked(fetch).mockClear();

    fireEvent.change(screen.getByLabelText("Enter move, chat, or command"), {
      target: { value: "d4" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    await waitFor(() => expect(vi.mocked(fetch)).toHaveBeenCalledWith(
      expect.stringContaining("/chat"),
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ text: "d4" }),
      }),
    ));
  });

  it("opens engine diagnostics from the attached evaluation bar", async () => {
    renderApp({
      ...workspaceFixture,
      evaluation: {
        ...workspaceFixture.evaluation,
        status: "ready",
        centipawns: 42,
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
    });
    const score = await screen.findByLabelText("White-perspective score");
    expect(score).toHaveTextContent("+0.42");
    fireEvent.click(score);

    const drawer = screen.getByRole("dialog", { name: "Details Drawer" });
    expect(within(drawer).getByText("Engine evaluation")).toBeInTheDocument();
    expect(within(drawer).getByText("12,000")).toBeInTheDocument();
    expect(within(drawer).getByText("45 ms")).toBeInTheDocument();
  });

  it("still auto-plays the selected opponent source", async () => {
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
    await screen.findByText("Black to move via engine");
    await waitFor(() => expect(vi.mocked(fetch)).toHaveBeenCalledWith(
      expect.stringContaining("/opponent/next"),
      expect.objectContaining({ method: "POST" }),
    ));
  });
});

function withSecondDevelopment(): WorkspaceSnapshot {
  const source = workspaceFixture.pieceScripts[0];
  const emptyRelationships: PieceScript["relationships"] = {
    attacks: [],
    attackers: [],
    defendersByAttacker: [],
    distinctDefenders: [],
    attackerCount: 0,
    defenderCount: 0,
    attackBalance: 0,
    attacked: false,
    undefended: false,
    underDefended: false,
    kingPinned: false,
    pinnedBy: null,
  };
  const ePawn: PieceScript = {
    ...source,
    alias: "e-pawn",
    ref: "piece:white:pawn:e",
    label: "White e-pawn",
    currentSquare: "e2",
    development: {
      ...source.development!,
      reference: "e-pawn.develop",
      to: "e3",
      status: "available",
    },
    interrupts: [],
    relationships: emptyRelationships,
  };
  return {
    ...workspaceFixture,
    pieceScripts: [
      workspaceFixture.pieceScripts[0],
      ePawn,
      workspaceFixture.pieceScripts[1],
    ],
    developmentOrder: ["d-pawn", "e-pawn"],
  };
}
