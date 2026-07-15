from __future__ import annotations

from pathlib import Path
import shutil

import chess
import pytest

from chess_tui.flow import (
    DefaultRule,
    ExceptionRule,
    FlowStore,
    FlowStorageError,
    FlowValidationError,
    OpponentReply,
    RuleUnavailableError,
    WhiteFlow,
    WhiteFlowAuthor,
    WhitePolicy,
    normalized_position_key,
    replay_san,
)

PROJECT_ROOT = Path(__file__).parents[1]
LONDON_FLOW = PROJECT_ROOT / "tests" / "fixtures" / "london-flow.toml"


def test_store_loads_human_readable_london_flow() -> None:
    flow = FlowStore().load(LONDON_FLOW)

    assert flow.name == "London System"
    assert [rule.move_san for rule in flow.defaults] == ["d4", "Bf4", "e3", "Nf3"]
    assert flow.exceptions == (
        ExceptionRule(
            "after-d4-e5",
            2,
            ("d4", "e5"),
            "dxe5",
            "Capture the offered pawn.",
        ),
    )
    assert [reply.move_san for reply in flow.opponent_replies] == [
        "d5",
        "Nf6",
        "e6",
        "c5",
    ]


def test_author_persists_explored_opponent_reply_without_statistics(
    tmp_path: Path,
) -> None:
    path = tmp_path / "london.toml"
    shutil.copy2(LONDON_FLOW, path)
    author = WhiteFlowAuthor(path)
    after_d4 = replay_san(author.flow.start_fen, ("d4",))

    author.record_opponent_reply(after_d4, ("d4",), "d5")
    author.record_opponent_reply(after_d4, ("d4",), "d5")

    reloaded = FlowStore().load(path)
    expected = OpponentReply("after-d4-d5", ("d4",), "d5")
    assert reloaded.opponent_replies.count(expected) == 1
    assert len(reloaded.opponent_replies) == 4
    encoded = path.read_text(encoding="utf-8")
    assert "[[opponent_replies]]" in encoded
    assert "games" not in encoded
    assert "frequency" not in encoded


def test_normalized_position_key_ignores_only_move_clocks() -> None:
    first = chess.Board()
    second = chess.Board()
    second.halfmove_clock = 17
    second.fullmove_number = 42

    assert normalized_position_key(first) == normalized_position_key(second)

    second.turn = chess.BLACK
    assert normalized_position_key(first) != normalized_position_key(second)

    without_castling = first.copy(stack=False)
    without_castling.castling_rights = chess.BB_EMPTY
    assert normalized_position_key(first) != normalized_position_key(without_castling)

    after_e4 = chess.Board()
    after_e4.push_san("e4")
    without_en_passant = after_e4.copy(stack=False)
    without_en_passant.ep_square = None
    assert normalized_position_key(after_e4) != normalized_position_key(
        without_en_passant
    )


def test_policy_uses_default_then_exact_position_exception(tmp_path: Path) -> None:
    path = tmp_path / "london.toml"
    shutil.copy2(LONDON_FLOW, path)
    author = WhiteFlowAuthor(path)
    author.remove_exception("after-d4-e5")

    after_d5 = replay_san(author.flow.start_fen, ("d4", "d5"))
    after_e5 = replay_san(author.flow.start_fen, ("d4", "e5"))
    assert author.recommend(after_d5, 2).move_san == "Bf4"  # type: ignore[union-attr]
    assert author.recommend(after_e5, 2).move_san == "Bf4"  # type: ignore[union-attr]

    author.add_exception(
        after_e5,
        2,
        ("d4", "e5"),
        "dxe5",
        "Capture the offered pawn.",
    )

    d5_recommendation = author.recommend(after_d5, 2)
    e5_recommendation = author.recommend(after_e5, 2)
    assert d5_recommendation is not None
    assert d5_recommendation.move_san == "Bf4"
    assert d5_recommendation.source == "default"
    assert e5_recommendation is not None
    assert e5_recommendation.move_san == "dxe5"
    assert e5_recommendation.source == "exception"
    assert e5_recommendation.exception_id == "after-d4-e5"


def test_store_writes_atomically_and_keeps_backup(tmp_path: Path) -> None:
    path = tmp_path / "london.toml"
    shutil.copy2(LONDON_FLOW, path)
    original = path.read_text(encoding="utf-8")

    updated = FlowStore().replace_default(path, 2, "Bg5", "Pin the knight.")

    assert updated.defaults[1] == DefaultRule(2, "Bg5", "Pin the knight.")
    assert FlowStore().load(path) == updated
    assert path.with_suffix(".toml.bak").read_text(encoding="utf-8") == original
    assert not [item for item in tmp_path.iterdir() if item.suffix == ".tmp"]


def test_invalid_save_leaves_original_unchanged(tmp_path: Path) -> None:
    path = tmp_path / "london.toml"
    shutil.copy2(LONDON_FLOW, path)
    original = path.read_bytes()
    flow = FlowStore().load(path)
    invalid = WhiteFlow(
        flow.version,
        flow.name,
        flow.start_fen,
        (flow.defaults[1],),
        flow.exceptions,
    )

    with pytest.raises(FlowValidationError, match="start at 1"):
        FlowStore().save(path, invalid)

    assert path.read_bytes() == original


def test_later_default_must_be_legal_in_a_realizable_line() -> None:
    flow = FlowStore().load(LONDON_FLOW)
    invalid = WhiteFlow(
        flow.version,
        flow.name,
        flow.start_fen,
        (
            DefaultRule(1, "e4"),
            DefaultRule(2, "e3"),
        ),
        (),
    )

    with pytest.raises(FlowValidationError, match="legal realization"):
        FlowStore().validate(invalid)


def test_failed_atomic_replace_leaves_original_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "london.toml"
    shutil.copy2(LONDON_FLOW, path)
    original = path.read_bytes()
    flow = FlowStore().load(path)

    def fail_replace(source: Path, destination: Path) -> None:
        raise OSError("simulated rename failure")

    monkeypatch.setattr("chess_tui.flow.store.os.replace", fail_replace)

    with pytest.raises(FlowStorageError, match="simulated rename failure"):
        FlowStore().save(path, flow)

    assert path.read_bytes() == original
    assert not [item for item in tmp_path.iterdir() if item.suffix == ".tmp"]


def test_duplicate_exception_positions_are_rejected() -> None:
    base = FlowStore().load(LONDON_FLOW)
    flow = WhiteFlow(
        base.version,
        base.name,
        base.start_fen,
        base.defaults,
        (
            ExceptionRule(
                "knight-first",
                3,
                ("Nf3", "Nf6", "g3", "g6"),
                "Bg2",
            ),
            ExceptionRule(
                "pawn-first",
                3,
                ("g3", "g6", "Nf3", "Nf6"),
                "Bg2",
            ),
        ),
    )

    with pytest.raises(FlowValidationError, match="duplicates a normalized position"):
        FlowStore().validate(flow)


def test_policy_reports_illegal_default_without_skipping() -> None:
    flow = FlowStore().load(LONDON_FLOW)
    board = replay_san(flow.start_fen, ("d4", "d5", "e4", "e6"))

    with pytest.raises(RuleUnavailableError, match="e3 is not legal") as exc_info:
        WhitePolicy(flow).recommend(board, 3)

    assert exc_info.value.recommendation.step == 3
    assert exc_info.value.recommendation.move_san == "e3"


def test_reload_failure_keeps_current_policy_in_memory(tmp_path: Path) -> None:
    path = tmp_path / "london.toml"
    shutil.copy2(LONDON_FLOW, path)
    author = WhiteFlowAuthor(path)
    previous_flow = author.flow
    previous_policy = author.policy
    path.write_text("version = 99\n", encoding="utf-8")

    with pytest.raises(FlowValidationError):
        author.reload()

    assert author.flow is previous_flow
    assert author.policy is previous_policy
