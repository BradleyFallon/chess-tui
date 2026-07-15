from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import shutil

import pytest

from chess_tui.flow import AttemptResult, FlowStore, FlowValidationError, FlowWorkspace
from chess_tui.policy import MoveAction, OriginalPieceId

FIXTURE = Path(__file__).parent / "fixtures" / "london-flow.toml"


def workspace(tmp_path: Path) -> FlowWorkspace:
    path = tmp_path / "flow.toml"
    shutil.copy2(FIXTURE, path)
    result = FlowWorkspace(path)
    result.restart()
    return result


def test_correct_mismatch_retry_and_continue(tmp_path: Path) -> None:
    work = workspace(tmp_path)
    assert work.policy_turn and work.policy_turn.decision.move_san == "d4"
    mismatch = work.submit_policy_uci("e2e4")
    assert mismatch.result is AttemptResult.MISMATCH
    assert work.history == []
    work.retry_policy_move()
    assert work.board.fen() == mismatch.board_before.fen()

    mismatch = work.submit_policy_uci("e2e4")
    kept = work.continue_with_policy_move()
    assert kept.san == "d4"
    assert work.history == ["d4"]
    assert work.runtime.rule_states["develop-d-pawn"].lifecycle.value == "retired"


def test_correct_move_commits_and_opponent_reply_recomputes_decision(
    tmp_path: Path,
) -> None:
    work = workspace(tmp_path)
    attempt = work.submit_policy_san("d4")
    assert attempt.result is AttemptResult.CORRECT
    work.complete_correct_move()
    work.submit_opponent_san("d5")
    decision = work.begin_policy_turn().decision
    assert work.history == ["d4", "d5"]
    assert decision.move_san == "Bf4"


def test_back_from_attempt_opponent_turn_and_later_policy_turn(tmp_path: Path) -> None:
    work = workspace(tmp_path)
    work.submit_policy_san("e4")
    work.go_back_to_previous_decision()
    assert work.history == []

    work.submit_policy_san("d4")
    work.complete_correct_move()
    work.go_back_to_previous_decision()
    assert work.history == []

    work.submit_policy_san("d4")
    work.complete_correct_move()
    work.submit_opponent_san("d5")
    work.begin_policy_turn()
    work.go_back_to_previous_decision()
    assert work.history == []
    assert work.policy_turn and work.policy_turn.decision.move_san == "d4"


def test_restart_and_replay_are_deterministic_and_non_destructive(
    tmp_path: Path,
) -> None:
    work = workspace(tmp_path)
    work.submit_policy_san("d4")
    work.complete_correct_move()
    work.submit_opponent_san("d5")
    work.begin_policy_turn()
    before_file = work.author.path.read_text(encoding="utf-8")
    assert work.policy_turn is not None
    first = work.policy_turn.decision.trace
    work.reload()
    assert work.policy_turn and work.policy_turn.decision.trace == first
    work.restart()
    assert work.history == [] and not work.can_restart
    assert work.author.path.read_text(encoding="utf-8") == before_file


def test_edit_revalidates_replays_and_reassesses_pending_move(tmp_path: Path) -> None:
    work = workspace(tmp_path)
    attempt = work.submit_policy_san("e4")
    assert attempt.result is AttemptResult.MISMATCH
    rule = work.author.flow.rules[0]
    work.update_rule(
        replace(rule, move=MoveAction(OriginalPieceId.parse("white:e2"), "e4"))
    )
    assert work.attempt is None
    assert work.history == ["e4"]
    assert FlowStore().load(work.author.path).rules[0].move.to_square == "e4"


def test_mismatch_can_be_added_as_an_exact_rule_and_committed(tmp_path: Path) -> None:
    work = workspace(tmp_path)
    attempt = work.submit_policy_san("e4")
    assert attempt.result is AttemptResult.MISMATCH

    override = work.allow_mismatch_as_override()

    assert override.id == "allow-e2e4-ply-0"
    assert override.after_san == ()
    assert str(override.move.piece) == "white:e2"
    assert override.move.to_square == "e4"
    assert work.attempt is None
    assert work.history == ["e4"]
    assert not work.is_policy_turn
    assert FlowStore().load(work.author.path).overrides[-1] == override


def test_adding_mismatch_replaces_existing_exact_rule_for_position(
    tmp_path: Path,
) -> None:
    work = workspace(tmp_path)
    work.submit_policy_san("d4")
    work.complete_correct_move()
    work.submit_opponent_san("e5")
    work.begin_policy_turn()
    assert work.submit_policy_san("Bf4").result is AttemptResult.MISMATCH
    override_count = len(work.author.flow.overrides)

    override = work.allow_mismatch_as_override()

    assert override.id == "after-d4-e5"
    assert str(override.move.piece) == "white:c1"
    assert override.move.to_square == "f4"
    assert len(work.author.flow.overrides) == override_count
    assert work.history == ["d4", "e5", "Bf4"]


def test_failed_edit_preserves_file_and_live_attempt(tmp_path: Path) -> None:
    work = workspace(tmp_path)
    attempt = work.submit_policy_san("e4")
    original = work.author.path.read_text(encoding="utf-8")
    rule = work.author.flow.rules[0]
    with pytest.raises(FlowValidationError):
        work.update_rule(replace(rule, priority=work.author.flow.rules[1].priority))
    assert work.author.path.read_text(encoding="utf-8") == original
    assert work.attempt is attempt


def test_beginning_of_line_back_fails(tmp_path: Path) -> None:
    work = workspace(tmp_path)
    with pytest.raises(FlowValidationError, match="no earlier"):
        work.go_back_to_previous_decision()


def test_black_controlled_flow_uses_generic_policy_and_opponent_turns(
    tmp_path: Path,
) -> None:
    path = tmp_path / "black.toml"
    path.write_text(
        """
version=2
name="Black policy"
start_fen="rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"
side="black"
[[rules]]
id="reply-e5"
priority=10
move={piece="black:e7",to="e5"}
""",
        encoding="utf-8",
    )
    work = FlowWorkspace(path)
    assert work.restart().decision.move_san == "e5"
    attempt = work.submit_policy_san("e5")
    assert attempt.result is AttemptResult.CORRECT
    work.complete_correct_move()
    assert not work.is_policy_turn
    work.submit_opponent_san("Nf3")
    assert work.is_policy_turn
