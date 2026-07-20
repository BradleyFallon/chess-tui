from pathlib import Path
import shutil

from chess_tui.flow import AttemptResult, FlowStore, FlowWorkspace
from chess_tui.policy.runtime import FrontierReason


def copy_london(tmp_path: Path) -> Path:
    path = tmp_path / "london.toml"
    shutil.copy2("flows/london.toml", path)
    return path


def test_replay_back_and_restart_reconstruct_v4_completion(tmp_path: Path) -> None:
    workspace = FlowWorkspace(copy_london(tmp_path))
    workspace.restart()
    first = workspace.submit_policy_san("d4")
    assert first.result is AttemptResult.CORRECT
    workspace.complete_correct_move()
    workspace.submit_opponent_san("d5")
    turn = workspace.begin_policy_turn()
    assert turn.decision.move_san == "Bf4"
    workspace.go_back_to_previous_decision()
    assert workspace.history == []
    assert workspace.policy_turn
    assert workspace.policy_turn.decision.move_san == "d4"
    workspace.restart()
    assert not workspace.runtime.completed_interrupts


def test_accept_here_creates_exact_piece_interrupt_and_commits_move(
    tmp_path: Path,
) -> None:
    path = copy_london(tmp_path)
    workspace = FlowWorkspace(path)
    workspace.restart()
    attempt = workspace.submit_policy_san("e4")
    assert attempt.result is AttemptResult.MISMATCH
    exact = workspace.accept_attempt_as_interrupt()
    assert exact.after_san == ()
    assert exact.attempts[0].to_square == "e4"  # type: ignore[union-attr]
    assert workspace.history == ["e4"]
    loaded = FlowStore().load(path)
    reference = next(
        ref for ref, rule in loaded.interrupt_by_ref.items() if rule.after_san == ()
    )
    assert reference.startswith("e-pawn.")

    workspace.restart()
    replacement_attempt = workspace.submit_policy_san("d4")
    assert replacement_attempt.result is AttemptResult.MISMATCH
    workspace.accept_attempt_as_interrupt()
    reloaded = FlowStore().load(path)
    exact_references = [
        reference
        for reference, rule in reloaded.interrupt_by_ref.items()
        if rule.after_san == ()
    ]
    assert len(exact_references) == 1
    assert exact_references[0].startswith("d-pawn.")


def test_frontier_manual_move_completes_original_piece_development(
    tmp_path: Path,
) -> None:
    path = tmp_path / "frontier.toml"
    path.write_text("""
version = 4
name = "Frontier"
start_fen = "startpos"
side = "white"
development_order = []
interrupt_order = []

[pieces.knight]
ref = "piece:white:knight:kingside"
""".strip() + "\n")
    workspace = FlowWorkspace(path)
    turn = workspace.restart()
    assert turn.decision.frontier_reason is FrontierReason.DEVELOPMENT_COMPLETE
    attempt = workspace.submit_policy_san("Nf3")
    assert attempt.result is AttemptResult.FRONTIER
