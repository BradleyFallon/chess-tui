import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";

import App from "../App";
import { WorkspaceProvider } from "../develop/WorkspaceContext";
import { commandResponse, jsonResponse, workspaceFixture } from "./fixtures";

vi.mock("react-chessboard", () => ({
  Chessboard: ({ options }: { options: { position?: string; squareStyles?: Record<string, { background?: string }>; onPieceDrop?: (args: { sourceSquare: string; targetSquare: string }) => boolean } }) => (
    <div data-testid="chessboard" data-position={options.position} data-hint={Object.entries(options.squareStyles ?? {}).find(([, style]) => style.background === "#e2ad55")?.[0]}>
      <button onClick={() => options.onPieceDrop?.({ sourceSquare: "d2", targetSquare: "d4" })}>Play d4</button>
    </div>
  ),
}));

function renderRoute(path = "/") {
  return render(<MemoryRouter initialEntries={[path]}><WorkspaceProvider><App /></WorkspaceProvider></MemoryRouter>);
}

test("menu and development workspace show the v2 policy", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(workspaceFixture())));
  renderRoute();
  expect(await screen.findByText("London System")).toBeInTheDocument();
  expect(screen.getByText(/deterministic-v2/)).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /Develop/ })).toBeInTheDocument();
});

test("workspace renders board, grouped rule status, lifecycle, and activity", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(workspaceFixture())));
  renderRoute("/develop");
  expect(await screen.findByTestId("chessboard")).toBeInTheDocument();
  const panel = screen.getByRole("heading", { name: "Rule status" }).closest("aside");
  expect(panel).not.toBeNull();
  expect(within(panel!).getByText("develop-d-pawn")).toBeInTheDocument();
  expect(within(panel!).getByText("Dormant")).toBeInTheDocument();
  expect(screen.getByRole("log")).toHaveTextContent("Development session ready");
  expect(screen.queryByText(/legacy/i)).not.toBeInTheDocument();
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
        attachment: { kind: "decision-explanation", selected: { kind: "rule", id: "develop-d-pawn", priority: 400, moveSan: "d4", note: "Control the center.", reason: "Selected." }, higherPriorityWaiting: [], shadowedActive: [], dormant: [], conditionReasons: ["Active from start."], provenance: ["policy-trace"] },
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
    node?.tagName === "SPAN" && node.textContent === "Selected: develop-d-pawn · 400",
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

test("mismatch shows retry, selected continuation, engine review, and editor direction", async () => {
  const snapshot = workspaceFixture({
    phase: "policy-result",
    attempt: {
      result: "mismatch", playedUci: "e2e4", playedSan: "e4", expectedUci: "d2d4", expectedSan: "d4",
      source: "rule", sourceId: "develop-d-pawn", note: "Control the center.", trace: [],
      engineReview: { status: "ready", quality: "blunder", lossCp: 260, bestMoveUci: "d2d4", bestMoveSan: "d4", evaluationBeforeCp: 20, evaluationAfterCp: -240, mateBefore: null, mateAfter: null, errorMessage: null },
    },
  });
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(snapshot))); renderRoute("/develop");
  expect(await screen.findByRole("button", { name: "Retry" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Use selected move" })).toBeInTheDocument();
  expect(screen.getByText("blunder").closest("p")).toHaveTextContent("Best move: d4");
  expect(screen.getByText(/Edit in Rule Status/)).toBeInTheDocument();
});

test("mismatch chat command adds a rule for the attempted move", async () => {
  const initial = workspaceFixture();
  const mismatch = workspaceFixture({
    phase: "policy-result",
    attempt: {
      result: "mismatch", playedUci: "e2e4", playedSan: "e4",
      expectedUci: "d2d4", expectedSan: "d4", source: "rule",
      sourceId: "develop-d-pawn", note: "Control the center.", trace: [],
      engineReview: null,
    },
    availableCommands: [
      { id: "add_rule_for_mismatch", slash: "/add-rule", usage: "/add-rule", description: "Add an exact-position rule that accepts the attempted move.", arguments: [] },
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
  expect(screen.getByRole("option", { name: /\/add-rule/ })).toBeInTheDocument();
  await userEvent.clear(composer);
  await userEvent.type(composer, "/add-rule{Enter}");

  await waitFor(() => expect(fetchMock).toHaveBeenLastCalledWith(
    "/api/sessions/session-1/chat",
    expect.objectContaining({ method: "POST", body: JSON.stringify({ text: "/add-rule" }) }),
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

test("full v2 rule editor sends conditions and original-piece action", async () => {
  const fetchMock = vi.fn().mockResolvedValue(jsonResponse(workspaceFixture()));
  vi.stubGlobal("fetch", fetchMock); renderRoute("/develop");
  await userEvent.click((await screen.findAllByRole("button", { name: "Edit rule" }))[0]);
  const destination = screen.getByRole("textbox", { name: "Destination" });
  await userEvent.clear(destination); await userEvent.type(destination, "e4");
  await userEvent.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() => expect(fetchMock).toHaveBeenLastCalledWith(
    "/api/sessions/session-1/rules/develop-d-pawn",
    expect.objectContaining({ method: "PUT", body: expect.stringContaining('"piece":"white:d2"') }),
  ));
});

test("exact override editor uses its dedicated endpoint", async () => {
  const override = { kind: "exact-override" as const, id: "after-d4-e5", enabled: true, afterSan: ["d4", "e5"], piece: "white:d2", destination: "e5", moveUci: "d4e5", moveSan: "dxe5", matched: true, legal: true, selected: true, note: "Capture.", reason: "Exact position matched." };
  const snapshot = workspaceFixture({ rules: { ...workspaceFixture().rules, selected: override, overrides: [override] } });
  const fetchMock = vi.fn().mockResolvedValue(jsonResponse(snapshot)); vi.stubGlobal("fetch", fetchMock); renderRoute("/develop");
  await userEvent.click(await screen.findByRole("button", { name: "Edit override" }));
  await userEvent.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() => expect(fetchMock).toHaveBeenLastCalledWith("/api/sessions/session-1/overrides/after-d4-e5", expect.objectContaining({ method: "PUT" })));
});

test("TOML tab, Back, Restart, and failed API preserve the last snapshot", async () => {
  const initial = workspaceFixture({ navigation: { canBack: true, canRestart: true } });
  const error = { error: { code: "FLOW_PERSISTENCE_ERROR", message: "Could not save flow", details: {} } };
  const fetchMock = vi.fn().mockResolvedValueOnce(jsonResponse(initial)).mockResolvedValueOnce(jsonResponse({ path: "flows/london.toml", content: 'version = 2\n[[rules]]\nid = "develop-d-pawn"\n' })).mockResolvedValueOnce(jsonResponse(error, 500));
  vi.stubGlobal("fetch", fetchMock); renderRoute("/develop");
  await userEvent.click(await screen.findByRole("tab", { name: "TOML" }));
  expect(await screen.findByLabelText("Flow TOML source")).toHaveTextContent("version = 2");
  await userEvent.click(screen.getByRole("tab", { name: "Rules" }));
  await userEvent.click(screen.getByRole("button", { name: "Back" }));
  await waitFor(() => expect(fetchMock).toHaveBeenLastCalledWith(
    "/api/sessions/session-1/commands",
    expect.objectContaining({ method: "POST", body: JSON.stringify({ command: "go_back", source: "ui" }) }),
  ));
  expect(await screen.findByRole("alert")).toHaveTextContent("Could not save flow");
  expect(screen.getByText("develop-d-pawn")).toBeInTheDocument();
});
