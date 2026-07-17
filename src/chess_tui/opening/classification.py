"""Offline deterministic classification over the bundled Lichess position graph."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
import json
from pathlib import Path
from typing import Any

import chess

from ..flow.position import normalized_position_key
from .errors import OpeningDataError


class OpeningMoveProvenance(str, Enum):
    BOOK_AND_POLICY = "book-and-policy"
    POLICY_ONLY = "policy-only"
    EXACT_OVERRIDE = "exact-override"
    RECORDED_BRANCH = "recorded-branch"
    BOOK = "book"
    ENGINE = "engine"
    MANUAL = "manual"
    FRONTIER = "frontier"


@dataclass(frozen=True, slots=True)
class OpeningMatch:
    record_id: int
    eco: str
    name: str
    family: str
    variation: str | None
    line_depth: int
    specificity: int


@dataclass(frozen=True, slots=True)
class BookContinuation:
    uci: str
    san: str
    opening_names: tuple[str, ...]
    defense_names: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class OpeningContext:
    primary_match: OpeningMatch | None
    current_matches: tuple[OpeningMatch, ...]
    last_known_match: OpeningMatch | None
    entered: tuple[OpeningMatch, ...]
    maintained: tuple[OpeningMatch, ...]
    exited: tuple[OpeningMatch, ...]
    played_move_in_book: bool | None
    book_continuations: tuple[BookContinuation, ...]
    reachable_defenses: tuple[str, ...]
    move_source: OpeningMoveProvenance | None
    policy_rule_id: str | None = None
    exact_override_id: str | None = None
    recorded_reply_id: str | None = None


@dataclass(frozen=True, slots=True)
class OpeningHistoryEntry:
    ply: int
    san: str
    uci: str
    position_key: str
    context: OpeningContext


class OpeningClassifier:
    """Read-only classifier backed by one generated position graph."""

    def __init__(self, index: dict[str, Any]) -> None:
        if index.get("schemaVersion") != 1:
            raise OpeningDataError("Unsupported bundled opening-index schema.")
        source = index.get("source")
        records = index.get("records")
        positions = index.get("positions")
        if not isinstance(source, dict) or not isinstance(source.get("revision"), str):
            raise OpeningDataError("Opening index has invalid source metadata.")
        if not isinstance(records, list) or not isinstance(positions, dict):
            raise OpeningDataError("Opening index has invalid records or positions.")
        self.revision = source["revision"]
        self._records = tuple(
            self._decode_match(item, record_id)
            for record_id, item in enumerate(records)
        )
        self._positions = positions

    @classmethod
    def from_path(cls, path: Path) -> OpeningClassifier:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise OpeningDataError(
                f"Could not load opening index {path}: {error}"
            ) from error
        if not isinstance(value, dict):
            raise OpeningDataError(f"Opening index {path} must contain an object.")
        return cls(value)

    @classmethod
    def bundled(cls) -> OpeningClassifier:
        return _bundled_classifier()

    def matches_for(self, board: chess.Board) -> tuple[OpeningMatch, ...]:
        node = self._node(board)
        if node is None:
            return ()
        record_ids = node.get("matches", [])
        if not isinstance(record_ids, list):
            raise OpeningDataError("Opening index position has invalid matches.")
        matches = [self._record(record_id) for record_id in record_ids]
        return tuple(sorted(matches, key=_match_sort_key))

    def primary_match_for(self, board: chess.Board) -> OpeningMatch | None:
        matches = self.matches_for(board)
        return matches[0] if matches else None

    def match_by_id(self, record_id: int) -> OpeningMatch:
        return self._record(record_id)

    def match_for_identity(self, eco: str, name: str) -> OpeningMatch | None:
        return next(
            (
                match
                for match in self._records
                if match.eco == eco and match.name == name
            ),
            None,
        )

    def book_continuations(self, board: chess.Board) -> tuple[BookContinuation, ...]:
        node = self._node(board)
        if node is None:
            return ()
        rows = node.get("continuations", [])
        if not isinstance(rows, list):
            raise OpeningDataError("Opening index position has invalid continuations.")
        continuations: list[BookContinuation] = []
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("uci"), str):
                raise OpeningDataError(
                    "Opening index contains an invalid continuation."
                )
            uci = row["uci"]
            try:
                move = chess.Move.from_uci(uci)
            except ValueError as error:
                raise OpeningDataError(
                    f"Opening index has invalid UCI {uci!r}."
                ) from error
            if move not in board.legal_moves:
                raise OpeningDataError(
                    f"Opening-index continuation {uci!r} is illegal in {board.fen()}."
                )
            record_ids = row.get("records", [])
            records = tuple(self._record(record_id) for record_id in record_ids)
            continuations.append(
                BookContinuation(
                    uci=uci,
                    san=board.san(move),
                    opening_names=tuple(sorted({record.name for record in records})),
                    defense_names=tuple(
                        sorted(
                            {
                                record.family
                                for record in records
                                if "Defense" in record.family
                            }
                        )
                    ),
                )
            )
        return tuple(sorted(continuations, key=lambda item: (item.san, item.uci)))

    def reachable_defenses(self, board: chess.Board) -> tuple[str, ...]:
        node = self._node(board)
        if node is None:
            return ()
        values = node.get("reachableDefenses", [])
        if not isinstance(values, list) or any(
            not isinstance(value, str) for value in values
        ):
            raise OpeningDataError(
                "Opening index position has invalid reachable defenses."
            )
        return tuple(values)

    def compare_move_to_book(self, board: chess.Board, move: chess.Move) -> bool:
        return any(item.uci == move.uci() for item in self.book_continuations(board))

    def initial_context(self, board: chess.Board) -> OpeningContext:
        matches = self.matches_for(board)
        return OpeningContext(
            primary_match=matches[0] if matches else None,
            current_matches=matches,
            last_known_match=None,
            entered=matches,
            maintained=(),
            exited=(),
            played_move_in_book=None,
            book_continuations=self.book_continuations(board),
            reachable_defenses=self.reachable_defenses(board),
            move_source=None,
        )

    def context_after_move(
        self,
        board_before: chess.Board,
        move: chess.Move,
        board_after: chess.Board,
        previous: OpeningContext,
        *,
        move_source: OpeningMoveProvenance,
        policy_rule_id: str | None = None,
        exact_override_id: str | None = None,
        recorded_reply_id: str | None = None,
    ) -> OpeningContext:
        current = self.matches_for(board_after)
        current_ids = {item.record_id for item in current}
        previous_ids = {item.record_id for item in previous.current_matches}
        entered = tuple(item for item in current if item.record_id not in previous_ids)
        maintained = tuple(item for item in current if item.record_id in previous_ids)
        exited = tuple(
            item
            for item in previous.current_matches
            if item.record_id not in current_ids
        )
        return OpeningContext(
            primary_match=current[0] if current else None,
            current_matches=current,
            last_known_match=(
                previous.primary_match
                if previous.primary_match is not None
                else previous.last_known_match
            ),
            entered=entered,
            maintained=maintained,
            exited=exited,
            played_move_in_book=self.compare_move_to_book(board_before, move),
            book_continuations=self.book_continuations(board_after),
            reachable_defenses=self.reachable_defenses(board_after),
            move_source=move_source,
            policy_rule_id=policy_rule_id,
            exact_override_id=exact_override_id,
            recorded_reply_id=recorded_reply_id,
        )

    def _node(self, board: chess.Board) -> dict[str, Any] | None:
        value = self._positions.get(normalized_position_key(board))
        if value is None:
            return None
        if not isinstance(value, dict):
            raise OpeningDataError("Opening index contains an invalid position node.")
        return value

    def _record(self, record_id: object) -> OpeningMatch:
        if not isinstance(record_id, int) or not 0 <= record_id < len(self._records):
            raise OpeningDataError(
                f"Opening index has invalid record id {record_id!r}."
            )
        return self._records[record_id]

    @staticmethod
    def _decode_match(value: object, record_id: int) -> OpeningMatch:
        if not isinstance(value, dict):
            raise OpeningDataError(f"Opening record {record_id} must be an object.")
        try:
            return OpeningMatch(
                record_id=record_id,
                eco=str(value["eco"]),
                name=str(value["name"]),
                family=str(value["family"]),
                variation=(
                    str(value["variation"])
                    if value.get("variation") is not None
                    else None
                ),
                line_depth=int(value["lineDepth"]),
                specificity=int(value["specificity"]),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise OpeningDataError(f"Opening record {record_id} is invalid.") from error


def _match_sort_key(match: OpeningMatch) -> tuple[int, int, str, str, int]:
    return (
        -match.specificity,
        -match.line_depth,
        match.eco,
        match.name,
        match.record_id,
    )


@lru_cache(maxsize=1)
def _bundled_classifier() -> OpeningClassifier:
    path = Path(__file__).with_name("data") / "lichess-index.json"
    return OpeningClassifier.from_path(path)
