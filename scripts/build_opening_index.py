#!/usr/bin/env python3
"""Build the deterministic runtime index for the pinned Lichess opening data."""

from __future__ import annotations

import argparse
import csv
import io
import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
import sys

import chess
import chess.pgn

SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class SourceRecord:
    eco: str
    name: str
    uci: tuple[str, ...]

    @property
    def family(self) -> str:
        return self.name.split(":", 1)[0]

    @property
    def variation(self) -> str | None:
        _, separator, value = self.name.partition(":")
        return value.strip() if separator else None

    @property
    def specificity(self) -> int:
        return 1 + self.name.count(":") + self.name.count(",")


@dataclass(slots=True)
class PositionNode:
    matches: set[int]
    routes: set[int]
    continuations: dict[str, set[int]]

    @classmethod
    def empty(cls) -> PositionNode:
        return cls(set(), set(), defaultdict(set))


def normalized_position_key(board: chess.Board) -> str:
    turn = "w" if board.turn is chess.WHITE else "b"
    castling = board.castling_xfen() or "-"
    en_passant = chess.square_name(board.ep_square) if board.ep_square else "-"
    return " ".join((board.board_fen(), turn, castling, en_passant))


def parse_source(path: Path) -> list[SourceRecord]:
    records: list[SourceRecord] = []
    seen_rows: set[tuple[str, str, tuple[str, ...]]] = set()
    with path.open(encoding="utf-8", newline="") as source:
        reader = csv.DictReader(source, dialect="excel-tab")
        if reader.fieldnames != ["eco", "name", "pgn"]:
            raise ValueError(
                f"{path}: expected TSV columns eco, name, pgn; got {reader.fieldnames!r}"
            )
        for row_number, row in enumerate(reader, start=2):
            eco = (row.get("eco") or "").strip()
            name = (row.get("name") or "").strip()
            pgn = (row.get("pgn") or "").strip()
            if len(eco) != 3 or eco[0] not in "ABCDE" or not eco[1:].isdigit():
                raise ValueError(f"{path}:{row_number}: invalid ECO code {eco!r}")
            if not name or not pgn:
                raise ValueError(f"{path}:{row_number}: name and PGN are required")
            game = chess.pgn.read_game(io.StringIO(pgn))
            if game is None or game.errors:
                raise ValueError(
                    f"{path}:{row_number}: invalid PGN {pgn!r}: "
                    f"{game.errors if game else 'no game'}"
                )
            moves = tuple(move.uci() for move in game.mainline_moves())
            if not moves:
                raise ValueError(f"{path}:{row_number}: opening line has no moves")
            key = (eco, name, moves)
            if key in seen_rows:
                raise ValueError(f"{path}:{row_number}: duplicate opening row {name!r}")
            seen_rows.add(key)
            records.append(SourceRecord(eco, name, moves))
    return sorted(records, key=lambda item: (item.eco, item.name, item.uci))


def build_index(records: list[SourceRecord], revision: str) -> dict[str, object]:
    positions: dict[str, PositionNode] = defaultdict(PositionNode.empty)
    for record_id, record in enumerate(records):
        board = chess.Board()
        for ply, uci in enumerate(record.uci, start=1):
            node = positions[normalized_position_key(board)]
            node.routes.add(record_id)
            node.continuations[uci].add(record_id)
            move = chess.Move.from_uci(uci)
            if move not in board.legal_moves:
                raise ValueError(
                    f"{record.eco} {record.name!r}: illegal move {uci!r} at ply {ply}"
                )
            board.push(move)
        final_node = positions[normalized_position_key(board)]
        final_node.routes.add(record_id)
        final_node.matches.add(record_id)

    encoded_records = [
        {
            "eco": record.eco,
            "name": record.name,
            "family": record.family,
            "variation": record.variation,
            "lineDepth": len(record.uci),
            "specificity": record.specificity,
            "uci": list(record.uci),
        }
        for record in records
    ]
    encoded_positions: dict[str, object] = {}
    for key in sorted(positions):
        node = positions[key]
        defenses = sorted(
            {
                records[record_id].family
                for record_id in node.routes
                if "Defense" in records[record_id].family
            }
        )
        encoded_positions[key] = {
            "matches": sorted(node.matches),
            "continuations": [
                {"uci": uci, "records": sorted(record_ids)}
                for uci, record_ids in sorted(node.continuations.items())
            ],
            "reachableDefenses": defenses,
        }
    return {
        "schemaVersion": SCHEMA_VERSION,
        "source": {
            "repository": "https://github.com/lichess-org/chess-openings",
            "revision": revision,
        },
        "records": encoded_records,
        "positions": encoded_positions,
    }


def write_index(index: dict[str, object], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(index, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source",
        type=Path,
        default=Path("data/openings/lichess/openings.tsv"),
    )
    parser.add_argument(
        "--version",
        type=Path,
        default=Path("data/openings/lichess/VERSION"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("src/chess_tui/opening/data/lichess-index.json"),
    )
    args = parser.parse_args()
    try:
        revision = args.version.read_text(encoding="utf-8").strip()
        if len(revision) != 40 or any(
            char not in "0123456789abcdef" for char in revision
        ):
            raise ValueError(
                f"{args.version}: expected one full lowercase Git revision"
            )
        records = parse_source(args.source)
        index = build_index(records, revision)
        write_index(index, args.output)
    except (OSError, ValueError) as error:
        print(error, file=sys.stderr)
        return 1
    print(
        f"Wrote {len(index['records'])} records and "
        f"{len(index['positions'])} positions to {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
