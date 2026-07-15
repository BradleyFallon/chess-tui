import { render, screen, waitFor } from "@testing-library/react";
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

test("development workspace renders board, history, status feed, and policy context", async () => {
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
  expect(screen.getByLabelText("SAN move history")).toHaveTextContent("d4");
  expect(screen.getByLabelText("SAN move history")).toHaveTextContent("d5");
  expect(screen.getByRole("log")).toHaveTextContent("White played d4");
  expect(screen.getByRole("log")).toHaveTextContent("Black played d5");
  expect(screen.getByText(/Reason: Control the center/)).toBeInTheDocument();
  expect(screen.getByText(/lifecycle rules are not available yet/i)).toBeInTheDocument();
});

test("board submission updates to correct-result controls", async () => {
  const initial = workspaceFixture();
  const correct = workspaceFixture({
    phase: "white-result",
    position: {
      ...initial.position,
      fen: "rnbqkbnr/pppppppp/8/8/3P4/8/PPP1PPPP/RNBQKBNR b KQkq - 0 1",
      historySan: ["d4"],
      turn: "black",
      ply: 1,
      lastMoveUci: "d2d4",
      legalMovesUci: [],
    },
    attempt: {
      result: "correct",
      playedUci: "d2d4",
      playedSan: "d4",
      expectedUci: "d2d4",
      expectedSan: "d4",
      source: "default",
      engineReview: null,
    },
    activity: [
      { id: 1, kind: "success", title: "White played d4", message: "Correct. Control the center." },
    ],
  });
  const fetchMock = vi.fn()
    .mockResolvedValueOnce(jsonResponse(initial))
    .mockResolvedValueOnce(jsonResponse(correct));
  vi.stubGlobal("fetch", fetchMock);
  renderRoute("/develop");

  await userEvent.click(await screen.findByRole("button", { name: "Play d4" }));

  expect(await screen.findByRole("button", { name: "Continue" })).toBeInTheDocument();
  expect(screen.getByText("Correct — continue the line").closest(".side-region")).not.toBeNull();
  expect(fetchMock).toHaveBeenLastCalledWith(
    "/api/sessions/session-1/moves",
    expect.objectContaining({ method: "POST", body: JSON.stringify({ uci: "d2d4" }) }),
  );
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
