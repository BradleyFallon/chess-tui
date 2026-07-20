from __future__ import annotations

from pathlib import Path
import shutil

from chess_tui.flow import FlowStore, FlowWorkspace

FIXTURE = Path(__file__).parents[1] / "flows" / "london.toml"


def test_opponent_reply_is_branch_data_not_policy_rule(tmp_path: Path) -> None:
    path = tmp_path / "flow.toml"
    shutil.copy2(FIXTURE, path)
    workspace = FlowWorkspace(path)
    workspace.restart()
    workspace.submit_policy_san("d4")
    workspace.complete_correct_move()
    workspace.submit_opponent_san("Nf6")
    rulebook = FlowStore().load(path)
    assert any(
        reply.move_san == "Nf6" and reply.after_san == ("d4",)
        for reply in rulebook.opponent_replies
    )
    assert all(
        rule.id != "after-d4-nf6" for piece in rulebook.pieces for rule in piece.rules
    )


def test_replaying_existing_opponent_reply_preserves_authored_order(
    tmp_path: Path,
) -> None:
    path = tmp_path / "flow.toml"
    shutil.copy2(FIXTURE, path)
    source_before = path.read_text(encoding="utf-8")
    workspace = FlowWorkspace(path)
    ids_before = [item.id for item in workspace.author.rulebook.opponent_replies]
    workspace.submit_policy_san("d4")
    workspace.complete_correct_move()
    workspace.submit_opponent_san("d5")

    assert path.read_text(encoding="utf-8") == source_before
    assert [
        reply.id for reply in workspace.author.rulebook.opponent_replies
    ] == ids_before
