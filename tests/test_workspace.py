from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import shutil

import pytest

from chess_tui.flow import (
    AttemptResult,
    DevelopmentAssignment,
    FlowStore,
    FlowValidationError,
    FlowWorkspace,
)
from chess_tui.opening import OpeningMoveProvenance

FIXTURE = Path(__file__).parents[1] / "flows" / "london.toml"


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
    assert work.get_opening_history() == ()
    assert work.get_current_opening_context().primary_match is None
    work.retry_policy_move()
    assert work.board.fen() == mismatch.board_before.fen()

    mismatch = work.submit_policy_uci("e2e4")
    kept = work.continue_with_policy_move()
    assert kept.san == "d4"
    assert work.history == ["d4"]
    d_pawn = next(
        item for item in work.runtime.tracker.pieces if str(item.id) == "white:d2"
    )
    assert d_pawn.has_moved


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


def test_opening_history_records_policy_book_and_opponent_provenance(
    tmp_path: Path,
) -> None:
    work = workspace(tmp_path)
    work.submit_policy_san("d4")
    work.complete_correct_move()
    work.submit_opponent_san("d5")

    policy, opponent = work.get_opening_history()
    assert policy.context.primary_match
    assert policy.context.primary_match.name == "Queen's Pawn Game"
    assert policy.context.move_source is OpeningMoveProvenance.BOOK_AND_POLICY
    assert policy.context.policy_rule_id == "develop-d-pawn"
    assert policy.context.played_move_in_book is True
    assert opponent.context.move_source is OpeningMoveProvenance.MANUAL
    assert opponent.context.played_move_in_book is True


def test_opening_history_replays_and_preserves_alternate_branch_nodes(
    tmp_path: Path,
) -> None:
    work = workspace(tmp_path)
    work.submit_policy_san("d4")
    work.complete_correct_move()
    work.submit_opponent_san("a5")
    first_branch = tuple(work.history)
    first_context = work.get_current_opening_context()
    assert first_context.primary_match is None
    assert first_context.last_known_match
    assert first_context.last_known_match.name == "Queen's Pawn Game"

    work.go_back_to_previous_decision()
    assert work.history == []
    assert first_branch in work.explored_opening_nodes

    work.submit_policy_san("d4")
    work.complete_correct_move()
    work.submit_opponent_san("d5")
    second_branch = tuple(work.history)
    assert second_branch in work.explored_opening_nodes
    assert first_branch in work.explored_opening_nodes

    expected = work.get_opening_history()
    work.reload()
    assert work.get_opening_history() == expected
    work.restart()
    assert work.get_opening_history() == ()
    assert {first_branch, second_branch} <= work.explored_opening_nodes.keys()


def test_edit_revalidates_replays_and_reassesses_pending_move(tmp_path: Path) -> None:
    work = workspace(tmp_path)
    attempt = work.submit_policy_san("d3")
    assert attempt.result is AttemptResult.MISMATCH
    rule = work.author.flow.development[0]
    assert isinstance(rule, DevelopmentAssignment)
    work.update_rule(replace(rule, target="d3"))
    assert work.attempt is None
    assert work.history == ["d3"]
    saved = FlowStore().load(work.author.path).development[0]
    assert isinstance(saved, DevelopmentAssignment)
    assert saved.target == "d3"


def test_attempt_can_be_accepted_as_an_exact_rule_and_committed(tmp_path: Path) -> None:
    work = workspace(tmp_path)
    attempt = work.submit_policy_san("e4")
    assert attempt.result is AttemptResult.MISMATCH

    override = work.accept_attempt_as_override()

    assert override.id == "allow-e2e4-ply-0"
    assert override.after_san == ()
    assert str(override.move.piece) == "white:e2"
    assert override.move.to_square == "e4"
    assert work.attempt is None
    assert work.history == ["e4"]
    assert not work.is_policy_turn
    assert FlowStore().load(work.author.path).overrides[-1] == override


def test_accepting_attempt_replaces_existing_exact_rule_for_position(
    tmp_path: Path,
) -> None:
    work = workspace(tmp_path)
    work.submit_policy_san("d4")
    work.complete_correct_move()
    work.submit_opponent_san("e5")
    work.begin_policy_turn()
    assert work.submit_policy_san("Bf4").result is AttemptResult.MISMATCH
    override_count = len(work.author.flow.overrides)

    override = work.accept_attempt_as_override()

    assert override.id == "after-d4-e5"
    assert str(override.move.piece) == "white:c1"
    assert override.move.to_square == "f4"
    assert len(work.author.flow.overrides) == override_count
    assert work.history == ["d4", "e5", "Bf4"]


def test_failed_edit_preserves_file_and_live_attempt(tmp_path: Path) -> None:
    work = workspace(tmp_path)
    attempt = work.submit_policy_san("e4")
    original = work.author.path.read_text(encoding="utf-8")
    rule = work.author.flow.development[0]
    with pytest.raises(FlowValidationError):
        work.update_rule(replace(rule, structures=("unknown",)))
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
version=3
name="Black policy"
start_fen="rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"
side="black"
[[responses]]
id="reply-e5"
move={piece="piece:black:pawn:e",to="e5"}
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
