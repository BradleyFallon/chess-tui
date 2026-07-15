import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";

import App from "../App";
import { WorkspaceProvider } from "../develop/WorkspaceContext";
import { jsonResponse, workspaceFixture } from "./fixtures";

vi.mock("react-chessboard", () => ({
  Chessboard: ({ options }: { options: {
    position?: string;
    squareStyles?: Record<string, { background?: string }>;
    onPieceDrop?: (args: { sourceSquare: string; targetSquare: string }) => boolean;
  } }) => (
    <div
      data-testid="chessboard"
      data-position={options.position}
      data-hint={Object.entries(options.squareStyles ?? {}).find(([, style]) => style.background === "#e2ad55")?.[0]}
    >
      <button onClick={() => options.onPieceDrop?.({ sourceSquare: "d2", targetSquare: "d4" })}>
        Play d4
      </button>
    </div>
  ),
}));

function renderRoute(path = "/") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <WorkspaceProvider>
        <App />
      </WorkspaceProvider>
    </MemoryRouter>,
  );
}

test("main menu shows selected flow and both modes", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(workspaceFixture())));
  renderRoute();

  expect(await screen.findByText("London System")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /Quiz/ })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /Develop/ })).toBeInTheDocument();
});

test("development workspace renders board, rule status, status feed, and policy context", async () => {
  const snapshot = workspaceFixture({
    position: {
      ...workspaceFixture().position,
      historySan: ["d4", "d5"],
      ply: 2,
      lastMoveUci: "d7d5",
    },
    activity: [
      { id: 1, kind: "success", title: "White played d4", message: "Correct. Control the center." },
      { id: 2, kind: "move", title: "Black played d5", message: "This is the selected Black reply for the current flow line." },
    ],
  });
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(snapshot)));
  renderRoute("/develop");

  expect(await screen.findByTestId("chessboard")).toHaveAttribute("data-position", snapshot.position.fen);
  const advantageMeter = screen.getByRole("meter", { name: /White-perspective evaluation/ });
  const boardHeading = screen.getByRole("heading", { name: "Board" });
  expect(advantageMeter.compareDocumentPosition(boardHeading) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  const rulesPanel = screen.getByRole("heading", { name: "Rule status" }).closest("aside");
  expect(rulesPanel).not.toBeNull();
  expect(within(rulesPanel!).getByText("selected")).toBeInTheDocument();
  expect(within(rulesPanel!).getByText("d4")).toBeInTheDocument();
  expect(within(rulesPanel!).getByText("d4 d5")).toBeInTheDocument();
  expect(screen.getByRole("log")).toHaveTextContent("White played d4");
  expect(screen.getByRole("log")).toHaveTextContent("Black played d5");
  expect(screen.getByText(/Reason: Control the center/)).toBeInTheDocument();
  expect(screen.getByText(/lifecycle rules are not available yet/i)).toBeInTheDocument();
});

test("a correct board move advances directly to Black", async () => {
  const initial = workspaceFixture();
  const blackReady = workspaceFixture({
    phase: "black-ready",
    decision: null,
    position: {
      ...initial.position,
      fen: "rnbqkbnr/pppppppp/8/8/3P4/8/PPP1PPPP/RNBQKBNR b KQkq - 0 1",
      historySan: ["d4"],
      turn: "black",
      ply: 1,
      lastMoveUci: "d2d4",
      legalMovesUci: ["d7d5", "g8f6"],
    },
    activity: [
      { id: 1, kind: "success", title: "White played d4", message: "Correct. Control the center." },
    ],
  });
  const fetchMock = vi.fn()
    .mockResolvedValueOnce(jsonResponse(initial))
    .mockResolvedValueOnce(jsonResponse(blackReady));
  vi.stubGlobal("fetch", fetchMock);
  renderRoute("/develop");

  await userEvent.click(await screen.findByRole("button", { name: "Play d4" }));

  expect(await screen.findByRole("button", { name: "Next" })).toBeInTheDocument();
  expect(screen.getByRole("log")).toHaveTextContent("Correct. Control the center.");
  expect(screen.queryByRole("button", { name: "Continue" })).not.toBeInTheDocument();
  expect(fetchMock).toHaveBeenLastCalledWith(
    "/api/sessions/session-1/moves",
    expect.objectContaining({ method: "POST", body: JSON.stringify({ uci: "d2d4" }) }),
  );
});

test("chat composer submits a SAN move when Enter is pressed", async () => {
  const initial = workspaceFixture();
  const blackReady = workspaceFixture({
    phase: "black-ready",
    decision: null,
    position: {
      ...initial.position,
      historySan: ["d4"],
      turn: "black",
      ply: 1,
      legalMovesUci: ["d7d5"],
    },
  });
  const fetchMock = vi.fn()
    .mockResolvedValueOnce(jsonResponse(initial))
    .mockResolvedValueOnce(jsonResponse(blackReady));
  vi.stubGlobal("fetch", fetchMock);
  renderRoute("/develop");

  const composer = await screen.findByRole("textbox", { name: "Enter move in SAN" });
  await userEvent.type(composer, "d4{Enter}");

  await waitFor(() => expect(fetchMock).toHaveBeenLastCalledWith(
    "/api/sessions/session-1/moves/san",
    expect.objectContaining({ method: "POST", body: JSON.stringify({ san: "d4" }) }),
  ));
  expect(await screen.findByRole("button", { name: "Next" })).toBeInTheDocument();
});

test("Enter on Black’s turn asks the engine to play Next", async () => {
  const initial = workspaceFixture({
    phase: "black-ready",
    decision: null,
    position: {
      ...workspaceFixture().position,
      turn: "black",
      historySan: ["d4"],
      ply: 1,
      legalMovesUci: ["d7d5"],
    },
  });
  const advanced = workspaceFixture({
    position: { ...workspaceFixture().position, historySan: ["d4", "d5"], ply: 2 },
  });
  const fetchMock = vi.fn()
    .mockResolvedValueOnce(jsonResponse(initial))
    .mockResolvedValueOnce(jsonResponse(advanced));
  vi.stubGlobal("fetch", fetchMock);
  renderRoute("/develop");

  expect(await screen.findByRole("button", { name: "Next" })).toHaveAttribute("aria-keyshortcuts", "Enter");
  const emptyComposer = screen.getByRole("textbox", { name: "Enter move in SAN" });
  emptyComposer.focus();
  fireEvent.keyDown(emptyComposer, { key: "Enter" });

  await waitFor(() => expect(fetchMock).toHaveBeenLastCalledWith(
    "/api/sessions/session-1/black/next",
    expect.objectContaining({ method: "POST" }),
  ));
});

test("mismatch displays retry, expected continuation, and engine review", async () => {
  const snapshot = workspaceFixture({
    phase: "white-result",
    attempt: {
      result: "mismatch-default",
      playedUci: "e2e4",
      playedSan: "e4",
      expectedUci: "d2d4",
      expectedSan: "d4",
      source: "default",
      engineReview: {
        status: "ready",
        quality: "blunder",
        lossCp: 260,
        bestMoveUci: "d2d4",
        bestMoveSan: "d4",
        evaluationBeforeCp: 20,
        evaluationAfterCp: -240,
        mateBefore: null,
        mateAfter: null,
        errorMessage: null,
      },
    },
    activity: [
      { id: 1, kind: "warning", title: "White played e4", message: "Incorrect for this flow. The saved rule expects d4." },
    ],
  });
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(snapshot)));
  renderRoute("/develop");

  expect(await screen.findByRole("button", { name: "Retry" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Use saved move" })).toBeInTheDocument();
  expect(screen.getByText("blunder").closest("p")).toHaveTextContent("Best move: d4");
  await userEvent.click(screen.getByRole("button", { name: "Edit rules" }));
  expect(screen.getByText(/Rule editing is not available/)).toHaveTextContent("flows/london.toml");
});

test("ask for hint highlights only the expected source square", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(workspaceFixture())));
  renderRoute("/develop");

  const board = await screen.findByTestId("chessboard");
  expect(board).not.toHaveAttribute("data-hint");
  await userEvent.click(screen.getByRole("button", { name: "Hint" }));
  expect(board).toHaveAttribute("data-hint", "d2");
  expect(screen.getByRole("button", { name: "Hint shown" })).toBeDisabled();
});

test("Next asks the engine to play Black while the board remains selectable", async () => {
  const initial = workspaceFixture({
    phase: "black-ready",
    decision: null,
    position: {
      ...workspaceFixture().position,
      turn: "black",
      ply: 1,
      historySan: ["d4"],
      legalMovesUci: ["d7d5", "g8f6"],
    },
  });
  const advanced = workspaceFixture({
    position: {
      ...workspaceFixture().position,
      ply: 2,
      historySan: ["d4", "d5"],
      lastMoveUci: "d7d5",
    },
  });
  const fetchMock = vi.fn()
    .mockResolvedValueOnce(jsonResponse(initial))
    .mockResolvedValueOnce(jsonResponse(advanced));
  vi.stubGlobal("fetch", fetchMock);
  renderRoute("/develop");

  expect(await screen.findByText(/Pick Black’s reply on the board/)).toBeInTheDocument();
  expect(screen.getByTestId("chessboard")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Next" }));

  await waitFor(() => expect(fetchMock).toHaveBeenLastCalledWith(
    "/api/sessions/session-1/black/next",
    expect.objectContaining({ method: "POST" }),
  ));
});

test("applicable rules can be edited from the left panel", async () => {
  const initial = workspaceFixture();
  const edited = workspaceFixture({
    decision: { ...initial.decision!, moveUci: "e2e4", moveSan: "e4", note: "Claim the center." },
    rules: {
      ...initial.rules,
      selected: { ...initial.rules.selected!, moveSan: "e4", note: "Claim the center." },
      applicable: [
        { ...initial.rules.applicable[0], moveSan: "e4", note: "Claim the center." },
      ],
    },
  });
  const fetchMock = vi.fn()
    .mockResolvedValueOnce(jsonResponse(initial))
    .mockResolvedValueOnce(jsonResponse(edited));
  vi.stubGlobal("fetch", fetchMock);
  renderRoute("/develop");
  const user = userEvent.setup();

  await user.click(await screen.findByRole("button", { name: "Edit rule" }));
  await user.clear(screen.getByRole("textbox", { name: "Move in SAN" }));
  await user.type(screen.getByRole("textbox", { name: "Move in SAN" }), "e4");
  await user.clear(screen.getByRole("textbox", { name: "Reason / note" }));
  await user.type(screen.getByRole("textbox", { name: "Reason / note" }), "Claim the center.");
  await user.click(screen.getByRole("button", { name: "Save rule" }));

  await waitFor(() => expect(fetchMock).toHaveBeenLastCalledWith(
    "/api/sessions/session-1/rules/update",
    expect.objectContaining({
      method: "POST",
      body: JSON.stringify({
        ruleId: "default-step-1",
        kind: "default",
        moveSan: "e4",
        note: "Claim the center.",
      }),
    }),
  ));
});

test("left panel can switch to the active flow TOML", async () => {
  const fetchMock = vi.fn()
    .mockResolvedValueOnce(jsonResponse(workspaceFixture()))
    .mockResolvedValueOnce(jsonResponse({
      path: "flows/london.toml",
      content: 'version = 1\nname = "London System"\n\n[[defaults]]\nstep = 1\nmove = "d4"\n',
    }));
  vi.stubGlobal("fetch", fetchMock);
  renderRoute("/develop");

  const tomlTab = await screen.findByRole("tab", { name: "TOML" });
  expect(screen.getByRole("tab", { name: "Rules" })).toHaveAttribute("aria-selected", "true");
  await userEvent.click(tomlTab);

  expect(await screen.findByLabelText("Flow TOML source")).toHaveTextContent('name = "London System"');
  expect(tomlTab).toHaveAttribute("aria-selected", "true");
  expect(fetchMock).toHaveBeenLastCalledWith(
    "/api/sessions/session-1/flow/source",
    expect.objectContaining({ headers: expect.objectContaining({ "Content-Type": "application/json" }) }),
  );
});

test("development workspace tolerates an older snapshot without activity", async () => {
  const snapshot: Partial<ReturnType<typeof workspaceFixture>> = workspaceFixture();
  delete snapshot.activity;
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(snapshot)));

  renderRoute("/develop");

  expect(await screen.findByRole("heading", { name: "Game status" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Hint" })).toBeInTheDocument();
});

test("back and restart use centralized API operations", async () => {
  const initial = workspaceFixture({ navigation: { canBack: true, canRestart: true } });
  const afterBack = workspaceFixture({ navigation: { canBack: false, canRestart: true } });
  const reset = workspaceFixture();
  const fetchMock = vi.fn()
    .mockResolvedValueOnce(jsonResponse(initial))
    .mockResolvedValueOnce(jsonResponse(afterBack))
    .mockResolvedValueOnce(jsonResponse(reset));
  vi.stubGlobal("fetch", fetchMock);
  renderRoute("/develop");
  const user = userEvent.setup();

  await user.click(await screen.findByRole("button", { name: "Back" }));
  await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
    "/api/sessions/session-1/back",
    expect.objectContaining({ method: "POST" }),
  ));

  await user.click(screen.getByRole("button", { name: "Restart" }));
  await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
    "/api/sessions/session-1/restart",
    expect.objectContaining({ method: "POST" }),
  ));
});

test("an API failure preserves the last valid workspace", async () => {
  const initial = workspaceFixture({ navigation: { canBack: false, canRestart: true } });
  const fetchMock = vi.fn()
    .mockResolvedValueOnce(jsonResponse(initial))
    .mockResolvedValueOnce(jsonResponse({
      error: { code: "FLOW_PERSISTENCE_ERROR", message: "Could not save flow", details: {} },
    }, 500));
  vi.stubGlobal("fetch", fetchMock);
  renderRoute("/develop");

  await userEvent.click(await screen.findByRole("button", { name: "Restart" }));

  expect(await screen.findByRole("alert")).toHaveTextContent("Could not save flow");
  expect(screen.getByText(/Reason: Control the center/)).toBeInTheDocument();
  expect(screen.getByTestId("chessboard")).toBeInTheDocument();
});
