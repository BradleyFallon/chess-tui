from __future__ import annotations

from pathlib import Path
import shutil

import pytest

from chess_tui import DEFAULT_STARTING_FEN
from chess_tui.flow import (
    AttemptResult,
    FlowStore,
    FlowValidationError,
    FlowWorkspace,
    WhiteFlow,
    replay_san,
)

PROJECT_ROOT = Path(__file__).parents[1]
LONDON_FLOW = PROJECT_ROOT / "flows" / "london.toml"


def test_workspace_retries_and_keeps_saved_rule_from_original_position(
    tmp_path: Path,
) -> None:
    path = tmp_path / "london.toml"
    shutil.copy2(LONDON_FLOW, path)
    workspace = FlowWorkspace(path)

    turn = workspace.restart()
    assert turn.recommendation is not None
    assert turn.recommendation.move_san == "d4"

    mismatch = workspace.submit_white_uci("e2e4")
    assert mismatch.result is AttemptResult.MISMATCH_DEFAULT
    assert workspace.history == ["e4"]

    workspace.retry_white_move()
    assert workspace.history == []
    assert workspace.board.fen() == replay_san(DEFAULT_STARTING_FEN, ()).fen()

    workspace.submit_white_uci("e2e4")
    kept = workspace.keep_saved_rule()
    assert kept.san == "d4"
    assert workspace.history == ["d4"]
    assert workspace.board.piece_at(27) is not None


def test_workspace_saves_frontier_move_as_next_default(tmp_path: Path) -> None:
    path = tmp_path / "empty.toml"
    FlowStore().save(path, WhiteFlow(1, "Empty", DEFAULT_STARTING_FEN, (), ()))
    workspace = FlowWorkspace(path)

    turn = workspace.restart()
    assert turn.recommendation is None
    attempt = workspace.submit_white_uci("d2d4")
    assert attempt.result is AttemptResult.FRONTIER

    workspace.save_selected_default("Control the center.")
    saved = FlowStore().load(path)
    assert saved.defaults[0].move_san == "d4"
    assert saved.defaults[0].note == "Control the center."


def test_workspace_requires_exception_when_numbered_default_is_illegal(
    tmp_path: Path,
) -> None:
    path = tmp_path / "london.toml"
    shutil.copy2(LONDON_FLOW, path)
    workspace = FlowWorkspace(path)
    history = ("d4", "d5", "e4", "e6")
    workspace.controller.reset(replay_san(workspace.author.flow.start_fen, history))
    workspace.history[:] = history

    turn = workspace.begin_white_turn()
    assert turn.recommendation is not None
    assert turn.recommendation.move_san == "e3"
    assert turn.unavailable_reason is not None

    attempt = workspace.submit_white_uci("g1f3")
    assert attempt.result is AttemptResult.RULE_UNAVAILABLE
    workspace.save_selected_exception("Develop instead.")

    saved = FlowStore().load(path)
    assert saved.exceptions[-1].after_san == history
    assert saved.exceptions[-1].move_san == "Nf3"


def test_workspace_does_not_remove_exception_without_a_legal_default(
    tmp_path: Path,
) -> None:
    path = tmp_path / "flow.toml"
    FlowStore().save(
        path,
        WhiteFlow(1, "Exception only", DEFAULT_STARTING_FEN, (), ()),
    )
    workspace = FlowWorkspace(path)
    workspace.author.add_exception(
        workspace.board,
        1,
        (),
        "d4",
        "Only rule.",
    )
    workspace.begin_white_turn()
    attempt = workspace.submit_white_uci("e2e4")
    assert attempt.result is AttemptResult.MISMATCH_EXCEPTION

    with pytest.raises(FlowValidationError, match="No numbered default"):
        workspace.remove_exception_and_keep_default()

    assert FlowStore().load(path).exceptions[0].move_san == "d4"
