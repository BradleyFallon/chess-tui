import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";

import App from "../App";
import { WorkspaceProvider } from "../develop/WorkspaceContext";
import { jsonResponse, workspaceFixture } from "./fixtures";

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

test("correct move advances directly to opponent and Enter calls Next", async () => {
  const initial = workspaceFixture();
  const opponent = workspaceFixture({
    phase: "opponent-ready", decision: null,
    position: { ...initial.position, turn: "black", historySan: ["d4"], ply: 1, lastMoveUci: "d2d4", legalMovesUci: ["d7d5"] },
    activity: [{ id: 2, kind: "success", title: "White played d4", message: "Correct. Control the center." }],
  });
  const advanced = workspaceFixture({ position: { ...initial.position, historySan: ["d4", "d5"], ply: 2 } });
  const fetchMock = vi.fn().mockResolvedValueOnce(jsonResponse(initial)).mockResolvedValueOnce(jsonResponse(opponent)).mockResolvedValueOnce(jsonResponse(advanced));
  vi.stubGlobal("fetch", fetchMock); renderRoute("/develop");
  await userEvent.click(await screen.findByRole("button", { name: "Play d4" }));
  expect(await screen.findByRole("button", { name: "Next" })).toBeInTheDocument();
  const composer = screen.getByRole("combobox", { name: "Enter move in SAN" });
  composer.focus(); fireEvent.keyDown(composer, { key: "Enter" });
  await waitFor(() => expect(fetchMock).toHaveBeenLastCalledWith("/api/sessions/session-1/opponent/next", expect.objectContaining({ method: "POST" })));
});

test("SAN composer submits moves", async () => {
  const fetchMock = vi.fn().mockResolvedValue(jsonResponse(workspaceFixture()));
  vi.stubGlobal("fetch", fetchMock); renderRoute("/develop");
  await userEvent.type(await screen.findByRole("combobox", { name: "Enter move in SAN" }), "d4{Enter}");
  await waitFor(() => expect(fetchMock).toHaveBeenLastCalledWith("/api/sessions/session-1/moves/san", expect.objectContaining({ method: "POST", body: JSON.stringify({ san: "d4" }) })));
});

test("slash commands show concise help, filter, and execute from the composer", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(workspaceFixture())));
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
        id: 2,
        kind: "info",
        title: "Position analysis",
        message: "Candidate moves for White from the local book and Stockfish.",
        analysis: {
          bookMoves: [
            { uci: "d2d4", san: "d4", source: "policy", games: null, frequency: null },
          ],
          engineMoves: [
            { uci: "d2d4", san: "d4", evaluationCp: 32, mateIn: null, principalVariation: ["d2d4", "g8f6"] },
            { uci: "g1f3", san: "Nf3", evaluationCp: 20, mateIn: null, principalVariation: ["g1f3"] },
          ],
        },
      },
    ],
  });
  const fetchMock = vi.fn()
    .mockResolvedValueOnce(jsonResponse(initial))
    .mockResolvedValueOnce(jsonResponse(analysed));
  vi.stubGlobal("fetch", fetchMock);
  renderRoute("/develop");

  await userEvent.type(
    await screen.findByRole("combobox", { name: "Enter move in SAN" }),
    "/analyse{Enter}",
  );
  await waitFor(() => expect(fetchMock).toHaveBeenLastCalledWith(
    "/api/sessions/session-1/analysis",
    expect.objectContaining({ method: "POST" }),
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
  expect(screen.getByText(/Use Edit in Rule Status/)).toBeInTheDocument();
});

test("hint highlights the expected original piece square", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(workspaceFixture()))); renderRoute("/develop");
  const board = await screen.findByTestId("chessboard");
  await userEvent.click(screen.getByRole("button", { name: "Hint" }));
  expect(board).toHaveAttribute("data-hint", "d2");
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
  expect(await screen.findByRole("alert")).toHaveTextContent("Could not save flow");
  expect(screen.getByText("develop-d-pawn")).toBeInTheDocument();
});
