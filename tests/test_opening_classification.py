from __future__ import annotations

import csv
import importlib.util
from pathlib import Path
import sys

import chess

from chess_tui.opening import OpeningClassifier, OpeningMoveProvenance


def _board_after(*moves: str) -> chess.Board:
    board = chess.Board()
    for san in moves:
        board.push_san(san)
    return board


def _build_module():
    path = Path(__file__).parents[1] / "scripts" / "build_opening_index.py"
    spec = importlib.util.spec_from_file_location("build_opening_index", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_pinned_dataset_parses_and_generated_index_is_reproducible(
    tmp_path: Path,
) -> None:
    root = Path(__file__).parents[1]
    module = _build_module()
    records = module.parse_source(root / "data/openings/lichess/openings.tsv")
    revision = (root / "data/openings/lichess/VERSION").read_text().strip()
    rebuilt = module.build_index(records, revision)
    output = tmp_path / "index.json"
    module.write_index(rebuilt, output)

    assert len(records) == 3803
    assert rebuilt["source"]["revision"] == revision
    assert (
        output.read_bytes()
        == (root / "src/chess_tui/opening/data/lichess-index.json").read_bytes()
    )


def test_dataset_parser_rejects_invalid_rows(tmp_path: Path) -> None:
    source = tmp_path / "openings.tsv"
    with source.open("w", encoding="utf-8", newline="") as target:
        writer = csv.writer(target, dialect="excel-tab")
        writer.writerow(("eco", "name", "pgn"))
        writer.writerow(("not-eco", "Broken", "1. e4"))

    module = _build_module()
    try:
        module.parse_source(source)
    except ValueError as error:
        assert "invalid ECO" in str(error)
    else:
        raise AssertionError("invalid source row was accepted")


def test_exact_position_and_transposition_match_the_same_opening() -> None:
    classifier = OpeningClassifier.bundled()
    canonical = _board_after("Nh3", "d5", "g3", "e5", "f4")
    transposed = _board_after("g3", "e5", "Nh3", "d5", "f4")
    primary = classifier.primary_match_for(canonical)

    assert primary is not None
    assert primary.name == "Amar Opening: Paris Gambit"
    assert classifier.matches_for(transposed) == classifier.matches_for(canonical)


def test_multiple_matches_preserve_ambiguity_and_stable_primary() -> None:
    module = _build_module()
    records = [
        module.SourceRecord("A00", "Alpha Opening", ("g1h3",)),
        module.SourceRecord("A00", "Alpha Opening: Specific Variation", ("g1h3",)),
    ]
    classifier = OpeningClassifier(module.build_index(records, "0" * 40))
    board = _board_after("Nh3")

    assert [match.name for match in classifier.matches_for(board)] == [
        "Alpha Opening: Specific Variation",
        "Alpha Opening",
    ]
    primary = classifier.primary_match_for(board)
    assert primary is not None
    assert primary.name.endswith("Specific Variation")


def test_transitions_last_known_book_moves_and_reachable_defenses() -> None:
    classifier = OpeningClassifier.bundled()
    start = chess.Board()
    first_move = start.parse_san("d4")
    after_d4 = start.copy(stack=False)
    after_d4.push(first_move)
    initial = classifier.initial_context(start)
    d4_context = classifier.context_after_move(
        start,
        first_move,
        after_d4,
        initial,
        move_source=OpeningMoveProvenance.BOOK_AND_POLICY,
        policy_rule_id="develop-d-pawn",
    )

    assert d4_context.primary_match is not None
    assert d4_context.primary_match.name == "Queen's Pawn Game"
    assert [item.name for item in d4_context.entered] == ["Queen's Pawn Game"]
    assert d4_context.played_move_in_book is True
    assert "Dutch Defense" in d4_context.reachable_defenses
    assert any(item.san == "d5" for item in d4_context.book_continuations)

    off_book = after_d4.copy(stack=False)
    move = off_book.parse_san("a5")
    off_book.push(move)
    ended = classifier.context_after_move(
        after_d4,
        move,
        off_book,
        d4_context,
        move_source=OpeningMoveProvenance.MANUAL,
    )
    assert ended.primary_match is None
    assert ended.last_known_match is not None
    assert ended.last_known_match.name == "Queen's Pawn Game"
    assert ended.played_move_in_book is False
    assert [item.name for item in ended.exited] == ["Queen's Pawn Game"]
