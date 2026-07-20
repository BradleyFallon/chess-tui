import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";

import App from "../App";
import { WorkspaceProvider } from "../develop/WorkspaceContext";
import { commandResponse, jsonResponse, ruleFixture, workspaceFixture } from "./fixtures";

vi.mock("react-chessboard", () => ({
  Chessboard: ({ options }: { options: {
    position?: string;
    boardOrientation?: string;
    squareStyles?: Record<string, { background?: string }>;
    onPieceDrop?: (args: { sourceSquare: string; targetSquare: string }) => boolean;
    onSquareClick?: (args: { square: string }) => void;
    squareRenderer?: (args: { square: string; children: React.ReactNode }) => React.ReactNode;
  } }) => (
    <div data-testid="chessboard" data-position={options.position} data-orientation={options.boardOrientation} data-hint={Object.entries(options.squareStyles ?? {}).find(([, style]) => style.background === "#e2ad55")?.[0]}>
      <button onClick={() => options.onSquareClick?.({ square: "d2" })}>Click d2</button>
      <button onClick={() => options.onSquareClick?.({ square: "c1" })}>Click c1</button>
      <button onClick={() => options.onSquareClick?.({ square: "a2" })}>Click a2</button>
      <button onClick={() => options.onSquareClick?.({ square: "c8" })}>Click c8</button>
      <button onClick={() => options.onSquareClick?.({ square: "f4" })}>Click f4</button>
      <button onClick={() => options.onPieceDrop?.({ sourceSquare: "d2", targetSquare: "d4" })}>Play d4</button>
      {options.squareRenderer?.({ square: "d2", children: <span>White pawn</span> })}
      {options.squareRenderer?.({ square: "c1", children: <span>White bishop</span> })}
    </div>
  ),
}));

function renderRoute(path = "/") {
  return render(<MemoryRouter initialEntries={[path]}><WorkspaceProvider><App /></WorkspaceProvider></MemoryRouter>);
}

test("menu and development workspace show the v3 policy", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(workspaceFixture())));
  renderRoute();
  expect(await screen.findByText("London System")).toBeInTheDocument();
  expect(screen.getByText(/deterministic-v3/)).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /Develop/ })).toBeInTheDocument();
});

test("workspace centers piece authoring and keeps diagnostics collapsed", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(workspaceFixture())));
  renderRoute("/develop");
  expect(await screen.findByTestId("chessboard")).toBeInTheDocument();
  const panel = screen.getByRole("complementary", { name: "Piece authoring" });
  expect(within(panel).getByText(/Click a piece to inspect/)).toBeInTheDocument();
  expect(within(panel).getByText("Current decision")).toBeInTheDocument();
  expect(within(panel).getByText("Change authored order")).toBeInTheDocument();
  expect(within(panel).queryByText("develop-d-pawn")).not.toBeInTheDocument();
  expect(within(panel).queryByText(/priority/i)).not.toBeInTheDocument();
  expect(within(panel).queryByLabelText("Generated condition JSON")).not.toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Options" })).toBeInTheDocument();
  expect(screen.getByRole("checkbox", { name: /Auto-respond/ })).not.toBeChecked();
  expect(screen.getByRole("log")).toHaveTextContent("Development session ready");
  expect(screen.queryByText(/legacy/i)).not.toBeInTheDocument();
});

test("piece inspection coexists with move entry and renders status markers", async () => {
  const snapshot = workspaceFixture();
  const fetchMock = vi.fn()
    .mockResolvedValueOnce(jsonResponse(snapshot))
    .mockResolvedValueOnce(jsonResponse(commandResponse(snapshot)));
  vi.stubGlobal("fetch", fetchMock);
  renderRoute("/develop");

  const board = await screen.findByTestId("chessboard");
  expect(board).toHaveAttribute("data-orientation", "white");
  expect(screen.getByRole("img", { name: /White d-pawn.*selected/i })).toHaveTextContent("★");
  expect(screen.getByRole("img", { name: /White queenside bishop.*inactive/i })).toHaveTextContent("○");

  await userEvent.click(screen.getByRole("button", { name: "Click d2" }));
  expect(screen.getByRole("heading", { name: "White d-pawn" })).toBeInTheDocument();
  expect(screen.getByText("piece:white:pawn:d")).toBeInTheDocument();
  expect(screen.getByText("Target d4")).toBeInTheDocument();
  expect(screen.getByText("Recommended now")).toBeInTheDocument();

  await userEvent.click(screen.getByRole("button", { name: "Play d4" }));
  await waitFor(() => expect(fetchMock).toHaveBeenLastCalledWith(
    "/api/sessions/session-1/commands",
    expect.objectContaining({
      body: JSON.stringify({ command: "play_move", source: "ui", notation: "uci", move: "d2d4" }),
    }),
  ));
});

test("opponent pieces are inspectable but never move-authorable", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(workspaceFixture())));
  renderRoute("/develop");

  await userEvent.click(await screen.findByRole("button", { name: "Click c8" }));

  expect(screen.getByRole("heading", { name: "Black queenside bishop" })).toBeInTheDocument();
  expect(screen.getAllByText("Opponent piece").length).toBeGreaterThan(0);
  expect(screen.getByText("This piece may be referenced in conditions.")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Add assignment" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Add special response" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Add continuation" })).not.toBeInTheDocument();
});

test("multiple assignments aggregate their marker and edit the selected assignment id", async () => {
  const initial = workspaceFixture();
  const snapshot = workspaceFixture({
    startingPieces: initial.startingPieces.map((piece) => piece.ref === "piece:white:pawn:d" ? {
      ...piece,
      developmentRules: [
        {
          ...piece.developmentRules[0],
          id: "fallback-d3",
          target: "d3",
          scopeSummary: "Global fallback",
          status: "out-of-scope" as const,
          friendlyStatus: "not-ready" as const,
          reason: "A scoped assignment is in scope.",
        },
        {
          ...piece.developmentRules[0],
          id: "active-d4",
          target: "d4",
          scopeSummary: "Plans: Active center",
          status: "waiting" as const,
          friendlyStatus: "blocked" as const,
          reason: "d4 is temporarily unavailable.",
        },
      ],
    } : piece),
  });
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(snapshot)));
  renderRoute("/develop");

  expect(await screen.findByRole("img", { name: /White d-pawn.*status waiting.*d3.*d4/i })).toHaveTextContent("!");
  await userEvent.click(screen.getByRole("button", { name: "Click d2" }));
  expect(screen.getByText("Global fallback")).toBeInTheDocument();
  expect(screen.getByText("Plans: Active center")).toBeInTheDocument();
  await userEvent.click(screen.getAllByRole("button", { name: "Edit assignment" })[1]);
  expect(screen.getByLabelText("Development target")).toHaveValue("d4");
});

test("unassigned piece can choose, cancel, validate, and apply a board target", async () => {
  const initial = workspaceFixture({
    startingPieces: [
      ...workspaceFixture().startingPieces,
      {
        ref: "piece:white:pawn:a", originalPieceId: "white:a2", color: "white",
        pieceType: "pawn", qualifier: "a", label: "White a-pawn",
        startingSquare: "a2", currentSquare: "a2", state: "undeveloped",
        firstMovedPly: null, capturedPly: null, authorable: true, developmentRules: [],
        relatedRules: [], exactFixes: [],
      },
    ],
  });
  const applied = workspaceFixture({
    startingPieces: initial.startingPieces.map((piece) => piece.ref === "piece:white:pawn:a"
      ? {
        ...piece,
        developmentRules: [{
          id: "develop-white-pawn-a", target: "f4", order: 3, structures: [], structureNames: [],
          scopeSummary: "All structures",
          status: "waiting" as const, readyWhen: null, note: "Test target.",
          reason: "a2f4 is not legal.",
          readinessSummary: "Ready immediately", friendlyStatus: "blocked" as const,
        }],
      }
      : piece),
  });
  const fetchMock = vi.fn()
    .mockResolvedValueOnce(jsonResponse(initial))
    .mockResolvedValueOnce(jsonResponse({
      valid: true, ruleId: "develop-white-pawn-a",
      piece: "piece:white:pawn:a", target: "f4", order: 3,
      summary: "Move White a-pawn to f4.",
      readinessSummary: "White d-pawn has moved",
      currentDecision: "d4", previewDecision: "d4",
      affectedOrder: [], conditionExpression: { moved: "piece:white:pawn:d" },
      warnings: [], errors: [],
      scopeSummary: "All structures", currentStructure: null,
      previewStructure: null, dependencies: [],
    }))
    .mockResolvedValueOnce(jsonResponse(applied))
    .mockResolvedValueOnce(jsonResponse(initial));
  vi.stubGlobal("fetch", fetchMock);
  renderRoute("/develop");

  await userEvent.click(await screen.findByRole("button", { name: "Click a2" }));
  expect(screen.getByText("No development assignment.")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Add assignment" }));
  await userEvent.click(screen.getByRole("button", { name: "Choose on board" }));
  await userEvent.click(screen.getByRole("button", { name: "Click f4" }));
  expect(screen.getByLabelText("Development target")).toHaveValue("f4");
  await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
  await userEvent.click(screen.getByRole("button", { name: "Add assignment" }));
  expect(screen.getByLabelText("Development target")).toHaveValue("");
  await userEvent.click(screen.getByRole("button", { name: "Choose on board" }));
  await userEvent.click(screen.getByRole("button", { name: "Click f4" }));

  await userEvent.type(screen.getByLabelText("Teaching note"), "Test target.");
  await userEvent.click(screen.getByRole("radio", { name: "After other pieces develop" }));
  await userEvent.selectOptions(screen.getByLabelText("Required piece"), "piece:white:pawn:d");
  await userEvent.click(screen.getByRole("button", { name: "Review changes" }));
  await waitFor(() => expect(fetchMock).toHaveBeenNthCalledWith(
    2,
    "/api/sessions/session-1/development-rules/validate",
    expect.objectContaining({
      method: "POST",
      body: expect.stringContaining('"readyWhen":{"moved":"piece:white:pawn:d"}'),
    }),
  ));
  await userEvent.click(await screen.findByRole("button", { name: "Apply" }));
  await waitFor(() => expect(fetchMock).toHaveBeenNthCalledWith(
    3,
    "/api/sessions/session-1/development-rules",
    expect.objectContaining({ method: "POST" }),
  ));
  expect(await screen.findByText("Target f4")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Remove assignment" }));
  await waitFor(() => expect(fetchMock).toHaveBeenNthCalledWith(
    4,
    "/api/sessions/session-1/development-rules/develop-white-pawn-a",
    expect.objectContaining({ method: "DELETE" }),
  ));
  expect(await screen.findByText("No development assignment.")).toBeInTheDocument();
});

test("black-controlled flows flip the board and keep markers square-local", async () => {
  const initial = workspaceFixture();
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(workspaceFixture({
    flow: { ...initial.flow, side: "black" },
    startingPieces: [...initial.startingPieces, {
      ref: "piece:black:pawn:d", originalPieceId: "black:d7", color: "black",
      pieceType: "pawn", qualifier: "d", label: "Black d-pawn",
      startingSquare: "d7", currentSquare: "d7", state: "undeveloped",
      firstMovedPly: null, capturedPly: null, authorable: true,
      developmentRules: [{
        id: "develop-black-pawn-d", target: "d5", order: 1, structures: [], structureNames: [],
        scopeSummary: "All structures",
        status: "selected", readyWhen: null, note: null, reason: "Selected.",
        readinessSummary: "Ready immediately", friendlyStatus: "recommended",
      }],
      relatedRules: [], exactFixes: [],
    }],
  }))));
  renderRoute("/develop");
  expect(await screen.findByTestId("chessboard")).toHaveAttribute("data-orientation", "black");
  expect(screen.queryByRole("img", { name: /White d-pawn.*selected/i })).not.toBeInTheDocument();
});

test("development order controls call the deterministic reorder endpoint", async () => {
  const initial = workspaceFixture();
  const fetchMock = vi.fn()
    .mockResolvedValueOnce(jsonResponse(initial))
    .mockResolvedValueOnce(jsonResponse(initial));
  vi.stubGlobal("fetch", fetchMock);
  renderRoute("/develop");
  await userEvent.click(await screen.findByText("Change authored order"));
  await userEvent.click(screen.getByRole("button", { name: "Move White d-pawn d4 later" }));
  await waitFor(() => expect(fetchMock).toHaveBeenLastCalledWith(
    "/api/sessions/session-1/development-rules/order",
    expect.objectContaining({
      method: "PUT",
      body: JSON.stringify({ ruleIds: ["develop-dark-bishop", "develop-d-pawn"] }),
    }),
  ));
});

test("captured development pieces remain inspectable from the order list", async () => {
  const initial = workspaceFixture();
  const captured = workspaceFixture({
    startingPieces: initial.startingPieces.map((piece) =>
      piece.ref === "piece:white:bishop:queenside"
        ? {
          ...piece,
          currentSquare: null,
          state: "captured-undeveloped" as const,
          capturedPly: 4,
          developmentRules: [{
            ...piece.developmentRules[0],
            status: "captured" as const,
            reason: "White queenside bishop was captured.",
          }],
        }
        : piece),
  });
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(captured)));
  renderRoute("/develop");
  await userEvent.click(await screen.findByText("Change authored order"));
  await userEvent.click(screen.getByRole("button", { name: /White queenside bishop → f4/ }));
  expect(screen.getAllByText("Captured before development on ply 4").length).toBeGreaterThan(0);
});

test("activity and deterministic chat attachments render in sequence order", async () => {
  const initial = workspaceFixture();
  const snapshot = workspaceFixture({
    activity: [
      initial.activity[0],
      { id: 2, sequence: 3, kind: "info", title: "Middle activity", message: "A state update.", attachment: null },
    ],
    chat: [
      { id: "message-1", sequence: 2, role: "user", text: "What changed?", attachment: null },
      {
        id: "message-2", sequence: 4, role: "assistant", text: "Current position details.",
        attachment: { kind: "position-details", fen: initial.position.fen, historySan: [], turn: "white", ply: 0, inCheck: false, lastMoveUci: null, legalMoves: [{ uci: "d2d4", san: "d4" }], gameOver: null },
      },
      {
        id: "message-3", sequence: 5, role: "assistant", text: "Why this move.",
        attachment: { kind: "decision-explanation", selected: { kind: "rule", id: "develop-d-pawn", moveSan: "d4", note: "Control the center.", reason: "Selected." }, waiting: [], applicableLater: [], unavailable: [], conditionReasons: ["Unlocked from start."], provenance: ["policy-trace"] },
      },
      { id: "message-4", sequence: 6, role: "assistant", text: "Trace.", attachment: { kind: "decision-trace", entries: ["Selected develop-d-pawn."], provenance: "policy-trace" } },
      { id: "message-5", sequence: 7, role: "assistant", text: "Invalid.", attachment: { kind: "validation-error", code: "UNKNOWN_RULE", details: {} } },
    ],
  });
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(snapshot)));
  renderRoute("/develop");

  const feed = await screen.findByRole("log");
  const content = feed.textContent ?? "";
  expect(content.indexOf("Development session ready")).toBeLessThan(content.indexOf("What changed?"));
  expect(content.indexOf("What changed?")).toBeLessThan(content.indexOf("Middle activity"));
  expect(content.indexOf("Middle activity")).toBeLessThan(content.indexOf("Current position details."));
  expect(within(feed).getByText(initial.position.fen)).toBeInTheDocument();
  expect(within(feed).getByText((_, node) =>
    node?.tagName === "SPAN" && node.textContent === "Selected: develop-d-pawn",
  )).toBeInTheDocument();
  expect(within(feed).getByText("Selected develop-d-pawn.")).toBeInTheDocument();
  expect(within(feed).getByText("UNKNOWN_RULE")).toBeInTheDocument();
});

test("opening timeline renders only the primary match with label controls", async () => {
  const initial = workspaceFixture();
  const london = {
    recordId: 42, eco: "D00", name: "Queen's Pawn Game: Accelerated London System",
    family: "Queen's Pawn Game", variation: "Accelerated London System", lineDepth: 3,
  };
  const context = {
    ...initial.opening,
    primaryMatch: london,
    currentMatches: [london],
    entered: [london],
    playedMoveInBook: true,
    moveSource: "book-and-policy" as const,
    policyRuleId: "develop-dark-bishop",
  };
  const entry = { ply: 3, san: "Bf4", uci: "c1f4", positionKey: "position", context };
  const maintainedContext = {
    ...context,
    entered: [],
    maintained: [london],
  };
  const maintainedEntry = {
    ...entry, ply: 4, san: "Nf6", uci: "g8f6", context: maintainedContext,
  };
  const workspace = workspaceFixture({
    activity: [
      ...initial.activity,
      {
        id: 2, sequence: 2, kind: "success", title: "White played Bf4",
        message: "Correct.", attachment: null,
      },
      {
        id: 3, sequence: 3, kind: "commentary", title: "Opening after 2.Bf4",
        message: "Accelerated London System.", attachment: {
          kind: "opening-context", entry, context, presentation: "transition",
        },
      },
      {
        id: 4, sequence: 4, kind: "move", title: "Black played Nf6",
        message: "Selected reply.", attachment: null,
      },
      {
        id: 5, sequence: 5, kind: "commentary", title: "Opening after 2...Nf6",
        message: "Accelerated London System.", attachment: {
          kind: "opening-context", entry: maintainedEntry,
          context: maintainedContext, presentation: "compact",
        },
      },
    ],
  });

  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(workspace)));
  renderRoute("/develop");

  expect(await screen.findAllByText("Opening:")).toHaveLength(2);
  expect(screen.queryByText("Entered:")).not.toBeInTheDocument();
  expect(screen.queryByText("Left:")).not.toBeInTheDocument();
  expect(screen.getAllByText(/Policy rule develop-dark-bishop, supported by book/)).toHaveLength(2);
  expect(screen.getAllByRole("button", { name: "Label this flow" })).toHaveLength(2);
  expect(screen.queryByText("Queen's Pawn Game: Accelerated London System")).not.toBeInTheDocument();
});

test("opening commentary can add an official flow label", async () => {
  const initial = workspaceFixture();
  const match = {
    recordId: 536, eco: "A40", name: "Queen's Pawn Game",
    family: "Queen's Pawn Game", variation: null, lineDepth: 1,
  };
  const context = {
    ...initial.opening,
    primaryMatch: match,
    currentMatches: [match],
    entered: [match],
    playedMoveInBook: true,
    moveSource: "book-and-policy" as const,
    policyRuleId: "develop-d-pawn",
  };
  const entry = { ply: 1, san: "d4", uci: "d2d4", positionKey: "position", context };
  const withCommentary = workspaceFixture({
    activity: [
      ...initial.activity,
      {
        id: 2, sequence: 2, kind: "commentary", title: "Opening after 1.d4",
        message: "Queen's Pawn Game.", attachment: {
          kind: "opening-context", entry, context, presentation: "transition",
        },
      },
    ],
  });
  const tagged = workspaceFixture({
    ...withCommentary,
    flow: {
      ...withCommentary.flow,
      openingTags: [{ recordId: 536, eco: "A40", name: "Queen's Pawn Game" }],
    },
  });
  const fetchMock = vi.fn()
    .mockResolvedValueOnce(jsonResponse(withCommentary))
    .mockResolvedValueOnce(jsonResponse(tagged));
  vi.stubGlobal("fetch", fetchMock);
  renderRoute("/develop");

  await userEvent.click(await screen.findByRole("button", { name: "Label this flow" }));

  await waitFor(() => expect(fetchMock).toHaveBeenNthCalledWith(
    2,
    "/api/sessions/session-1/opening-tags",
    expect.objectContaining({
      method: "POST",
      body: JSON.stringify({ recordId: 536 }),
    }),
  ));
  expect(await screen.findByRole("button", { name: /Queen's Pawn Game/ })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Remove flow label" })).toBeInTheDocument();
});

test("correct move advances directly to opponent and Enter calls Next", async () => {
  const initial = workspaceFixture();
  const opponent = workspaceFixture({
    phase: "opponent-ready", decision: null,
    position: { ...initial.position, turn: "black", historySan: ["d4"], ply: 1, lastMoveUci: "d2d4", legalMovesUci: ["d7d5"] },
    activity: [{ id: 2, sequence: 2, kind: "success", title: "White played d4", message: "Correct. Control the center.", attachment: null }],
  });
  const advanced = workspaceFixture({ position: { ...initial.position, historySan: ["d4", "d5"], ply: 2 } });
  const fetchMock = vi.fn().mockResolvedValueOnce(jsonResponse(initial)).mockResolvedValueOnce(jsonResponse(commandResponse(opponent))).mockResolvedValueOnce(jsonResponse(commandResponse(advanced)));
  vi.stubGlobal("fetch", fetchMock); renderRoute("/develop");
  await userEvent.click(await screen.findByRole("button", { name: "Play d4" }));
  await waitFor(() => expect(fetchMock).toHaveBeenNthCalledWith(
    2,
    "/api/sessions/session-1/commands",
    expect.objectContaining({ method: "POST", body: JSON.stringify({ command: "play_move", source: "ui", notation: "uci", move: "d2d4" }) }),
  ));
  expect(await screen.findByRole("button", { name: "Next" })).toBeInTheDocument();
  const composer = screen.getByRole("combobox", { name: "Enter move in SAN" });
  composer.focus(); fireEvent.keyDown(composer, { key: "Enter" });
  await waitFor(() => expect(fetchMock).toHaveBeenLastCalledWith("/api/sessions/session-1/commands", expect.objectContaining({ method: "POST", body: JSON.stringify({ command: "next_opponent", source: "ui" }) })));
});

test("Auto-respond persists and plays the opponent move without Enter", async () => {
  const initial = workspaceFixture();
  const opponent = workspaceFixture({
    phase: "opponent-ready",
    decision: null,
    position: {
      ...initial.position,
      turn: "black",
      historySan: ["d4"],
      ply: 1,
      lastMoveUci: "d2d4",
      legalMovesUci: ["d7d5"],
    },
  });
  const advanced = workspaceFixture({
    position: {
      ...initial.position,
      historySan: ["d4", "d5"],
      ply: 2,
      lastMoveUci: "d7d5",
    },
  });
  const fetchMock = vi.fn()
    .mockResolvedValueOnce(jsonResponse(initial))
    .mockResolvedValueOnce(jsonResponse(commandResponse(opponent)))
    .mockResolvedValueOnce(jsonResponse(commandResponse(advanced)));
  vi.stubGlobal("fetch", fetchMock);
  renderRoute("/develop");

  const autoRespond = await screen.findByRole("checkbox", { name: /Auto-respond/ });
  await userEvent.click(autoRespond);
  expect(autoRespond).toBeChecked();
  expect(localStorage.getItem("chess-flow-development-auto-respond")).toBe("true");

  await userEvent.click(screen.getByRole("button", { name: "Play d4" }));

  await waitFor(() => expect(fetchMock).toHaveBeenNthCalledWith(
    3,
    "/api/sessions/session-1/commands",
    expect.objectContaining({
      method: "POST",
      body: JSON.stringify({ command: "next_opponent", source: "ui" }),
    }),
  ));
});

test("SAN composer submits moves", async () => {
  const snapshot = workspaceFixture();
  const fetchMock = vi.fn().mockResolvedValueOnce(jsonResponse(snapshot)).mockResolvedValueOnce(jsonResponse(commandResponse(snapshot)));
  vi.stubGlobal("fetch", fetchMock); renderRoute("/develop");
  await userEvent.type(await screen.findByRole("combobox", { name: "Enter move in SAN" }), "d4{Enter}");
  await waitFor(() => expect(fetchMock).toHaveBeenLastCalledWith("/api/sessions/session-1/chat", expect.objectContaining({ method: "POST", body: JSON.stringify({ text: "d4" }) })));
});

test("typing anywhere sends printable keys to the move composer", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(workspaceFixture())));
  renderRoute("/develop");
  const composer = await screen.findByRole("combobox", { name: "Enter move in SAN" });

  fireEvent.keyDown(window, { key: "d" });
  expect(composer).toHaveFocus();
  expect(composer).toHaveValue("d");
  await userEvent.keyboard("4");
  expect(composer).toHaveValue("d4");

  const destination = document.createElement("input");
  document.body.append(destination);
  destination.focus();
  fireEvent.keyDown(destination, { key: "x" });
  expect(composer).toHaveValue("d4");
  destination.remove();
});

test("slash commands show concise help, filter, and execute from the composer", async () => {
  const snapshot = workspaceFixture();
  vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(jsonResponse(snapshot)).mockResolvedValueOnce(jsonResponse(commandResponse(snapshot, [{ kind: "highlight-move", uci: "d2d4" }]))));
  renderRoute("/develop");
  const composer = await screen.findByRole("combobox", { name: "Enter move in SAN" });

  await userEvent.type(composer, "/");
  const menu = screen.getByRole("listbox", { name: "Chat commands" });
  expect(within(menu).getByRole("option", { name: /\/hint/ })).toBeInTheDocument();
  expect(within(menu).getByRole("option", { name: /\/help/ })).toBeInTheDocument();
  expect(within(menu).queryByRole("option", { name: /\/next/ })).not.toBeInTheDocument();
  expect(
    within(menu).getByTitle("Highlight the piece selected by the current policy."),
  ).toBeInTheDocument();

  await userEvent.type(composer, "hin");
  expect(within(menu).getAllByRole("option")).toHaveLength(1);
  await userEvent.keyboard("{Enter}");
  expect(screen.getByTestId("chessboard")).toHaveAttribute("data-hint", "d2");
});

test("analysis strength can be changed from development options", async () => {
  const initial = workspaceFixture();
  const deep = workspaceFixture({
    analysisSettings: {
      ...initial.analysisSettings,
      selectedProfileId: "deep",
    },
  });
  const fetchMock = vi.fn()
    .mockResolvedValueOnce(jsonResponse(initial))
    .mockResolvedValueOnce(jsonResponse(deep));
  vi.stubGlobal("fetch", fetchMock);
  renderRoute("/develop");

  await userEvent.selectOptions(
    await screen.findByRole("combobox", { name: "Engine analysis strength" }),
    "deep",
  );

  await waitFor(() => expect(fetchMock).toHaveBeenLastCalledWith(
    "/api/sessions/session-1/analysis/settings",
    expect.objectContaining({
      method: "PUT",
      body: JSON.stringify({ profileId: "deep" }),
    }),
  ));
  expect(screen.getByText(/Depth 26 is the slowest/)).toBeInTheDocument();
});

test("analyse command adds book and engine suggestions to the status feed", async () => {
  const initial = workspaceFixture();
  const analysed = workspaceFixture({
    activity: [
      ...initial.activity,
      {
        id: 2, sequence: 3,
        kind: "info",
        title: "Position analysis completed",
        message: "Candidate moves are available in the conversation.",
        attachment: null,
      },
    ],
    chat: [
      { id: "chat-1", sequence: 2, role: "user", text: "/analyse", attachment: null },
      {
        id: "chat-2", sequence: 4, role: "assistant",
        text: "Candidate moves for White from the opening index and Stockfish.",
        attachment: { kind: "position-analysis", analysis: {
          bookMoves: [
            { uci: "d2d4", san: "d4", source: "policy", openingNames: [], defenseNames: [] },
          ],
          engineMoves: [
            { uci: "d2d4", san: "d4", evaluationCp: 32, mateIn: null, principalVariation: ["d2d4", "g8f6"] },
            { uci: "g1f3", san: "Nf3", evaluationCp: 20, mateIn: null, principalVariation: ["g1f3"] },
          ],
          engine: {
            engineName: "Stockfish 18", profileId: "analysis",
            requestedDepth: 20, actualDepth: 20, selectiveDepth: 28,
            nodes: 125000, nps: 1000000, timeMs: 125, lines: 4,
          },
        } },
      },
    ],
  });
  const fetchMock = vi.fn()
    .mockResolvedValueOnce(jsonResponse(initial))
    .mockResolvedValueOnce(jsonResponse(commandResponse(analysed)));
  vi.stubGlobal("fetch", fetchMock);
  renderRoute("/develop");

  await userEvent.type(
    await screen.findByRole("combobox", { name: "Enter move in SAN" }),
    "/analyse{Enter}",
  );
  await waitFor(() => expect(fetchMock).toHaveBeenLastCalledWith(
    "/api/sessions/session-1/chat",
    expect.objectContaining({ method: "POST", body: JSON.stringify({ text: "/analyse" }) }),
  ));
  expect(await screen.findByRole("heading", { name: "Book moves" })).toBeInTheDocument();
  expect(screen.getByText("selected policy")).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Engine best" })).toBeInTheDocument();
  expect(screen.getByText("+0.32")).toBeInTheDocument();
});

test("mismatch shows direct exact-fix and broader-response authoring actions", async () => {
  const snapshot = workspaceFixture({
    phase: "policy-result",
    attempt: {
      result: "mismatch", playedUci: "e2e4", playedSan: "e4", expectedUci: "d2d4", expectedSan: "d4",
      source: "development", sourceId: "develop-d-pawn", note: "Control the center.", trace: [],
      engineReview: { status: "ready", quality: "blunder", lossCp: 260, bestMoveUci: "d2d4", bestMoveSan: "d4", evaluationBeforeCp: 20, evaluationAfterCp: -240, mateBefore: null, mateAfter: null, errorMessage: null },
      authoringPrefill: { piece: "piece:white:pawn:e", target: "e4", pieceLabel: "White e-pawn", suggestions: [] },
    },
  });
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(snapshot))); renderRoute("/develop");
  expect(await screen.findByRole("button", { name: "Retry" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Use expected move" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Accept in this position" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Create broader response" })).toBeInTheDocument();
  expect(screen.getByText("blunder").closest("p")).toHaveTextContent("Best move: d4");
});

test("broader-response prefill never invents a trigger and offers backend suggestions", async () => {
  const initial = workspaceFixture();
  const ePawn = {
    ...initial.startingPieces[0],
    ref: "piece:white:pawn:e",
    originalPieceId: "white:e2",
    qualifier: "e",
    label: "White e-pawn",
    startingSquare: "e2",
    currentSquare: "e2",
    developmentRules: [],
  };
  const snapshot = workspaceFixture({
    phase: "policy-result",
    startingPieces: [...initial.startingPieces, ePawn],
    attempt: {
      result: "mismatch", playedUci: "e2e4", playedSan: "e4",
      expectedUci: "d2d4", expectedSan: "d4", source: "development",
      sourceId: "develop-d-pawn", note: null, trace: [], engineReview: null,
      authoringPrefill: {
        piece: "piece:white:pawn:e", target: "e4", pieceLabel: "White e-pawn",
        suggestions: [{
          label: "Previous move was Black e-pawn to e5",
          expression: { last_move: { piece: "piece:black:pawn:e", to: "e5" } },
        }],
      },
    },
  });
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(snapshot)));
  renderRoute("/develop");

  await userEvent.click(await screen.findByRole("button", { name: "Create broader response" }));
  expect(screen.getByDisplayValue("e4")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /Use suggestion: Previous move/ })).toBeInTheDocument();
  expect(screen.queryByRole("group", { name: "Current applicability" })).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Review changes" }));
  expect(screen.getByRole("alert")).toHaveTextContent("Choose a current trigger");

  await userEvent.click(screen.getByRole("button", { name: /Use suggestion: Previous move/ }));
  expect(screen.getByRole("group", { name: "Current applicability" })).toBeInTheDocument();
  expect(screen.getByLabelText("Condition type")).toHaveValue("last-move");
});

test("mismatch chat command accepts the attempted move here", async () => {
  const initial = workspaceFixture();
  const mismatch = workspaceFixture({
    phase: "policy-result",
    attempt: {
      result: "mismatch", playedUci: "e2e4", playedSan: "e4",
      expectedUci: "d2d4", expectedSan: "d4", source: "development",
      sourceId: "develop-d-pawn", note: "Control the center.", trace: [],
      engineReview: null,
      authoringPrefill: { piece: "piece:white:pawn:e", target: "e4", pieceLabel: "White e-pawn", suggestions: [] },
    },
    availableCommands: [
      { id: "accept_attempt_as_override", slash: "/accept-here", usage: "/accept-here", description: "Accept the attempted move as an exact fix.", arguments: [] },
      { id: "retry_policy", slash: "/retry", usage: "/retry", description: "Discard the attempted move and try again.", arguments: [] },
      { id: "continue_policy", slash: "/continue", usage: "/continue", description: "Discard the attempt and play the selected policy move.", arguments: [] },
    ],
  });
  const accepted = workspaceFixture({
    phase: "opponent-ready",
    decision: null,
    position: {
      ...initial.position,
      turn: "black",
      ply: 1,
      historySan: ["e4"],
      lastMoveUci: "e2e4",
    },
    activity: [
      ...initial.activity,
      {
        id: 2, sequence: 3,
        kind: "success",
        title: "Added rule allow-e2e4-ply-0",
        message: "e4 is now the exact-position policy move here and was accepted.",
        attachment: null,
      },
    ],
  });
  const fetchMock = vi.fn()
    .mockResolvedValueOnce(jsonResponse(mismatch))
    .mockResolvedValueOnce(jsonResponse(commandResponse(accepted)));
  vi.stubGlobal("fetch", fetchMock);
  renderRoute("/develop");
  const composer = await screen.findByRole("combobox", { name: "Enter move in SAN" });

  await userEvent.type(composer, "/");
  expect(screen.getByRole("option", { name: /\/accept-here/ })).toBeInTheDocument();
  await userEvent.clear(composer);
  await userEvent.type(composer, "/accept-here{Enter}");

  await waitFor(() => expect(fetchMock).toHaveBeenLastCalledWith(
    "/api/sessions/session-1/chat",
    expect.objectContaining({ method: "POST", body: JSON.stringify({ text: "/accept-here" }) }),
  ));
  expect(await screen.findByText("Added rule allow-e2e4-ply-0")).toBeInTheDocument();
});

test("hint highlights the expected original piece square", async () => {
  const snapshot = workspaceFixture();
  vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(jsonResponse(snapshot)).mockResolvedValueOnce(jsonResponse(commandResponse(snapshot, [{ kind: "highlight-move", uci: "d2d4" }])))); renderRoute("/develop");
  const board = await screen.findByTestId("chessboard");
  await userEvent.click(screen.getByRole("button", { name: "Hint" }));
  await waitFor(() => expect(board).toHaveAttribute("data-hint", "d2"));
});

test("guided special-response editor validates, reviews, and applies", async () => {
  const initial = workspaceFixture();
  const generic = ruleFixture({
    id: "generic-center-rule",
    section: "response",
    piece: "piece:white:pawn:d",
    destination: "e4",
    title: "Protect the center",
    triggerSummary: "White d-pawn is attacked",
    expirationSummary: "Stops after the move is used",
  });
  const snapshot = workspaceFixture({
    rules: { ...initial.rules, selected: generic, responses: [generic] },
    startingPieces: initial.startingPieces.map((piece) => piece.ref === "piece:white:pawn:d" ? {
      ...piece,
      relatedRules: [{
        id: generic.id, role: "response", title: generic.title,
        piece: generic.piece, target: generic.destination, moveSan: generic.moveSan,
        triggerSummary: generic.triggerSummary,
        expirationSummary: generic.expirationSummary,
        friendlyStatus: "recommended", runtimeStatus: "selected", note: generic.note,
      }],
    } : piece),
  });
  const validation = {
    valid: true, ruleId: generic.id, summary: "If attacked, move the White d-pawn to e4.",
    triggerSummary: "White d-pawn is attacked",
    expirationSummary: "Stops after the move is used",
    currentDecision: "d4", previewDecision: "e4", affectedOrder: [generic.id],
    conditionExpression: { attacked: "piece:white:pawn:d" }, warnings: [], errors: [],
    scopeSummary: "Global", unlockSummary: "Available immediately",
    currentStructure: null, previewStructure: null, dependencies: [],
    newlyApplicable: [generic.id], newlySuppressed: ["develop-d-pawn"],
  };
  const fetchMock = vi.fn()
    .mockResolvedValueOnce(jsonResponse(snapshot))
    .mockResolvedValueOnce(jsonResponse(validation))
    .mockResolvedValueOnce(jsonResponse(snapshot));
  vi.stubGlobal("fetch", fetchMock); renderRoute("/develop");
  await userEvent.click(await screen.findByRole("button", { name: "Click d2" }));
  await userEvent.click(screen.getByRole("button", { name: "Edit response" }));
  await userEvent.click(screen.getByRole("button", { name: "Review changes" }));
  await waitFor(() => expect(fetchMock).toHaveBeenLastCalledWith(
    "/api/sessions/session-1/rules/drafts/validate",
    expect.objectContaining({ method: "POST", body: expect.stringContaining('"piece":"piece:white:pawn:d"') }),
  ));
  expect(await screen.findByText("Review changes")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Apply" }));
  await waitFor(() => expect(fetchMock).toHaveBeenLastCalledWith(
    "/api/sessions/session-1/rules",
    expect.objectContaining({ method: "POST" }),
  ));
});

test("condition library creates a slugged named condition through review and apply", async () => {
  const snapshot = workspaceFixture();
  const validation = {
    valid: true, ruleId: "center-ready", summary: "Define center-ready.",
    triggerSummary: "White d-pawn has moved", expirationSummary: "Reusable condition",
    currentDecision: "d4", previewDecision: "d4", affectedOrder: [],
    conditionExpression: { moved: "piece:white:pawn:d" }, warnings: [], errors: [],
    scopeSummary: "", unlockSummary: "", currentStructure: null, previewStructure: null,
    dependencies: [], newlyApplicable: [], newlySuppressed: [], newlyShadowed: [],
  };
  const fetchMock = vi.fn()
    .mockResolvedValueOnce(jsonResponse(snapshot))
    .mockResolvedValueOnce(jsonResponse(validation))
    .mockResolvedValueOnce(jsonResponse(snapshot));
  vi.stubGlobal("fetch", fetchMock);
  renderRoute("/develop");

  await userEvent.click(await screen.findByText("Condition library"));
  await userEvent.click(screen.getByRole("button", { name: "Add named condition" }));
  await userEvent.type(screen.getByLabelText("Name / ID"), "Center Ready");
  expect(screen.getByText("center-ready")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Review condition" }));
  await waitFor(() => expect(fetchMock).toHaveBeenNthCalledWith(
    2,
    "/api/sessions/session-1/named-conditions/validate",
    expect.objectContaining({ method: "POST", body: expect.stringContaining('"id":"center-ready"') }),
  ));
  await userEvent.click(await screen.findByRole("button", { name: "Apply" }));
  await waitFor(() => expect(fetchMock).toHaveBeenNthCalledWith(
    3,
    "/api/sessions/session-1/named-conditions",
    expect.objectContaining({ method: "POST" }),
  ));
});

test("plans show current availability and create through the shared review", async () => {
  const initial = workspaceFixture();
  const plan = {
    id: "active-center", name: "Active center", status: "available" as const,
    availableWhen: { expression: { unmoved: "piece:white:pawn:c" }, value: true, explanation: "White c-pawn is undeveloped." },
    selectedWhen: { expression: { at: { piece: "piece:white:pawn:c", square: "c4" } }, value: false, explanation: "White c-pawn is not on c4." },
    selectedAtPly: null, note: "Use c4.", reason: "Available before selection.",
    order: 1, affectedPolicyItems: [],
  };
  const snapshot = workspaceFixture({
    rules: { ...initial.rules, structures: [plan] },
  });
  const validation = {
    valid: true, ruleId: "quiet-plan", summary: "Plan Quiet plan.",
    triggerSummary: "White d-pawn has moved", expirationSummary: "Selection stays fixed",
    currentDecision: "d4", previewDecision: "d4", affectedOrder: ["active-center", "quiet-plan"],
    conditionExpression: { moved: "piece:white:pawn:d" }, warnings: [], errors: [],
    scopeSummary: "", unlockSummary: "White d-pawn has moved",
    currentStructure: null, previewStructure: null, dependencies: [],
    newlyApplicable: [], newlySuppressed: [], newlyShadowed: [],
  };
  const fetchMock = vi.fn()
    .mockResolvedValueOnce(jsonResponse(snapshot))
    .mockResolvedValueOnce(jsonResponse(validation))
    .mockResolvedValueOnce(jsonResponse(snapshot));
  vi.stubGlobal("fetch", fetchMock);
  renderRoute("/develop");

  expect(await screen.findByText("Available")).toBeInTheDocument();
  expect(screen.getAllByText("Active center").length).toBeGreaterThan(0);
  await userEvent.click(screen.getByText("Plans and structures"));
  await userEvent.click(screen.getByRole("button", { name: "Add plan" }));
  await userEvent.type(screen.getByLabelText("Name"), "Quiet plan");
  await userEvent.click(screen.getByRole("button", { name: "Review plan" }));
  await waitFor(() => expect(fetchMock).toHaveBeenNthCalledWith(
    2,
    "/api/sessions/session-1/structure-drafts/validate",
    expect.objectContaining({ method: "POST", body: expect.stringContaining('"name":"Quiet plan"') }),
  ));
  await userEvent.click(await screen.findByRole("button", { name: "Apply" }));
  await waitFor(() => expect(fetchMock).toHaveBeenNthCalledWith(
    3,
    "/api/sessions/session-1/structure-drafts",
    expect.objectContaining({ method: "POST" }),
  ));
});

test("later plans use the shared complete move-rule editor", async () => {
  const snapshot = workspaceFixture();
  const validation = {
    valid: true, ruleId: "continue-white-pawn-d-to-d3", summary: "Later move.",
    triggerSummary: "In any position", expirationSummary: "Stops after use",
    currentDecision: "d4", previewDecision: "d4",
    affectedOrder: ["continue-white-pawn-d-to-d3"], conditionExpression: null,
    warnings: [], errors: [], scopeSummary: "Everywhere as a fallback",
    unlockSummary: "Available immediately", currentStructure: null, previewStructure: null,
    dependencies: [], newlyApplicable: [], newlySuppressed: [], newlyShadowed: [],
  };
  const fetchMock = vi.fn()
    .mockResolvedValueOnce(jsonResponse(snapshot))
    .mockResolvedValueOnce(jsonResponse(validation))
    .mockResolvedValueOnce(jsonResponse(snapshot));
  vi.stubGlobal("fetch", fetchMock);
  renderRoute("/develop");

  await userEvent.click(await screen.findByRole("button", { name: "Click d2" }));
  await userEvent.click(screen.getByRole("button", { name: "Add continuation" }));
  await userEvent.type(screen.getByLabelText("Destination"), "d3");
  expect(screen.getByText("When should it become part of the plan?")).toBeInTheDocument();
  expect(screen.getByText("When should it apply now?")).toBeInTheDocument();
  expect(screen.getByText("When should it expire?")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Review changes" }));
  await waitFor(() => expect(fetchMock).toHaveBeenNthCalledWith(
    2,
    "/api/sessions/session-1/rules/drafts/validate",
    expect.objectContaining({ method: "POST", body: expect.stringContaining('"section":"continuation"') }),
  ));
  await userEvent.click(await screen.findByRole("button", { name: "Apply" }));
  await waitFor(() => expect(fetchMock).toHaveBeenNthCalledWith(
    3,
    "/api/sessions/session-1/rules",
    expect.objectContaining({ method: "POST" }),
  ));
});

test("exact fix uses friendly language and reviews edits before apply", async () => {
  const override = { kind: "exact-override" as const, id: "after-d4-e5", enabled: true, afterSan: ["d4", "e5"], piece: "piece:white:pawn:d", destination: "e5", moveUci: "d4e5", moveSan: "dxe5", matched: true, legal: true, selected: true, note: "Capture.", reason: "Exact position matched.", friendlyStatus: "exact-fix-active" as const, positionSummary: "1.d4 e5", moveSummary: "White d-pawn to e5", normalizedPositionKey: "after:d4,e5" };
  const initial = workspaceFixture();
  const snapshot = workspaceFixture({
    rules: { ...initial.rules, selected: override, overrides: [override] },
    startingPieces: initial.startingPieces.map((piece) => piece.ref === "piece:white:pawn:d" ? {
      ...piece,
      exactFixes: [{ id: override.id, afterSan: override.afterSan, piece: override.piece, target: override.destination, moveSan: override.moveSan, reason: override.note, friendlyStatus: override.friendlyStatus, normalizedPositionKey: override.normalizedPositionKey }],
    } : piece),
  });
  const validation = {
    valid: true, ruleId: override.id,
    summary: "After 1.d4 e5, play White d-pawn to e5.",
    triggerSummary: "Exact position after 1.d4 e5",
    expirationSummary: "Exact fixes apply only in this position",
    currentDecision: "dxe5", previewDecision: "dxe5",
    affectedOrder: [override.id], conditionExpression: null, warnings: [], errors: [],
    scopeSummary: "This exact position", unlockSummary: "Available in this position",
    currentStructure: null, previewStructure: null, dependencies: [],
    newlyApplicable: [], newlySuppressed: [],
  };
  const fetchMock = vi.fn()
    .mockResolvedValueOnce(jsonResponse(snapshot))
    .mockResolvedValueOnce(jsonResponse(validation))
    .mockResolvedValueOnce(jsonResponse(snapshot));
  vi.stubGlobal("fetch", fetchMock); renderRoute("/develop");
  await userEvent.click(await screen.findByRole("button", { name: "Click d2" }));
  expect(screen.getByText("Exact fix active")).toBeInTheDocument();
  expect(screen.getByText("1.d4 e5")).toBeInTheDocument();
  expect(screen.getByText("dxe5")).toBeInTheDocument();
  expect(screen.queryByText('["d4","e5"]')).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Edit exact fix" }));
  await userEvent.clear(screen.getByLabelText("Reason"));
  await userEvent.type(screen.getByLabelText("Reason"), "Accept the offered pawn.");
  await userEvent.click(screen.getByRole("button", { name: "Review changes" }));
  await waitFor(() => expect(fetchMock).toHaveBeenNthCalledWith(
    2,
    "/api/sessions/session-1/exact-fixes/validate",
    expect.objectContaining({ method: "POST" }),
  ));
  await userEvent.click(await screen.findByRole("button", { name: "Apply" }));
  await waitFor(() => expect(fetchMock).toHaveBeenNthCalledWith(
    3,
    "/api/sessions/session-1/exact-fixes",
    expect.objectContaining({ method: "POST" }),
  ));
});

test("policy details drawer contains TOML and failed navigation preserves the snapshot", async () => {
  const initial = workspaceFixture({ navigation: { canBack: true, canRestart: true } });
  const error = { error: { code: "FLOW_PERSISTENCE_ERROR", message: "Could not save flow", details: {} } };
  const fetchMock = vi.fn().mockResolvedValueOnce(jsonResponse(initial)).mockResolvedValueOnce(jsonResponse({ path: "flows/london.toml", content: 'version = 3\n[[development]]\nid = "develop-d-pawn"\n' })).mockResolvedValueOnce(jsonResponse(error, 500));
  vi.stubGlobal("fetch", fetchMock); renderRoute("/develop");
  await userEvent.click(await screen.findByRole("button", { name: "View policy details" }));
  expect(await screen.findByLabelText("Flow TOML source")).toHaveTextContent("version = 3");
  expect(screen.getAllByText("Lifecycle").length).toBeGreaterThan(0);
  await userEvent.click(screen.getByRole("button", { name: "Close policy details" }));
  await userEvent.click(screen.getByRole("button", { name: "Back" }));
  await waitFor(() => expect(fetchMock).toHaveBeenLastCalledWith(
    "/api/sessions/session-1/commands",
    expect.objectContaining({ method: "POST", body: JSON.stringify({ command: "go_back", source: "ui" }) }),
  ));
  expect(await screen.findByRole("alert")).toHaveTextContent("Could not save flow");
  expect(screen.getByText("Current decision")).toBeInTheDocument();
});
