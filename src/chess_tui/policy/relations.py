"""Legal attack and recapture relationships for tracked original pieces."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

import chess

from .models import OriginalPieceId
from .tracker import OriginalPieceTracker


@dataclass(frozen=True, slots=True)
class AttackRelation:
    attacker: OriginalPieceId
    target: OriginalPieceId
    capture: chess.Move


@dataclass(frozen=True, slots=True)
class DefenseRelation:
    defender: OriginalPieceId
    defended: OriginalPieceId
    against: OriginalPieceId
    recapture: chess.Move


@dataclass(frozen=True, slots=True)
class PieceRelationFacts:
    piece: OriginalPieceId
    square: chess.Square | None
    attacks: tuple[AttackRelation, ...]
    attackers: tuple[AttackRelation, ...]
    defenders_by_attacker: Mapping[OriginalPieceId, tuple[DefenseRelation, ...]]
    distinct_defenders: tuple[OriginalPieceId, ...]
    king_pinned: bool
    pinned_by: OriginalPieceId | None
    pin_ray: tuple[chess.Square, ...]
    legal_moves: tuple[chess.Move, ...]
    legal_captures: tuple[chess.Move, ...]

    @property
    def attacker_count(self) -> int:
        return len({relation.attacker for relation in self.attackers})

    @property
    def defender_count(self) -> int:
        return len(self.distinct_defenders)

    @property
    def attack_balance(self) -> int:
        return self.attacker_count - self.defender_count

    @property
    def attacked(self) -> bool:
        return self.attacker_count > 0

    @property
    def undefended(self) -> bool:
        return self.attacked and self.defender_count == 0

    @property
    def under_defended(self) -> bool:
        return self.attacker_count > self.defender_count


class PositionRelations:
    def __init__(self, facts: Mapping[OriginalPieceId, PieceRelationFacts]) -> None:
        self._facts = MappingProxyType(dict(facts))

    @property
    def pieces(self) -> tuple[PieceRelationFacts, ...]:
        return tuple(self._facts.values())

    def get(self, piece: OriginalPieceId) -> PieceRelationFacts:
        return self._facts[piece]


class PositionAnalyzer:
    """Analyze both colors without mutating the live board or tracker."""

    def analyze(
        self, board: chess.Board, tracker: OriginalPieceTracker
    ) -> PositionRelations:
        live_fen = board.fen(en_passant="fen")
        legal_by_piece: dict[OriginalPieceId, tuple[chess.Move, ...]] = {}
        captures_by_piece: dict[OriginalPieceId, tuple[chess.Move, ...]] = {}
        attacks: list[AttackRelation] = []

        for runtime in tracker.pieces:
            if runtime.current_square is None or runtime.captured:
                legal_by_piece[runtime.id] = ()
                captures_by_piece[runtime.id] = ()
                continue
            color = _color(runtime.id.color)
            analysis_board = board_for_color(board, color)
            legal = tuple(
                move
                for move in analysis_board.legal_moves
                if move.from_square == runtime.current_square
            )
            captures = tuple(
                move
                for move in legal
                if analysis_board.is_capture(move)
                and tracker.piece_id_at(_capture_square(analysis_board, move))
                is not None
            )
            legal_by_piece[runtime.id] = legal
            captures_by_piece[runtime.id] = captures
            for move in captures:
                target = tracker.piece_id_at(_capture_square(analysis_board, move))
                if target is not None and target.color != runtime.id.color:
                    attacks.append(AttackRelation(runtime.id, target, move))

        defenses: dict[
            OriginalPieceId, dict[OriginalPieceId, list[DefenseRelation]]
        ] = {}
        for attack in attacks:
            analysis_board = board_for_color(board, _color(attack.attacker.color))
            if attack.capture not in analysis_board.legal_moves:
                continue
            analysis_board.push(attack.capture)
            recaptures: list[DefenseRelation] = []
            for move in analysis_board.legal_moves:
                if (
                    move.to_square != attack.capture.to_square
                    or not analysis_board.is_capture(move)
                ):
                    continue
                defender = tracker.piece_id_at(move.from_square)
                if (
                    defender is None
                    or defender == attack.target
                    or defender.color != attack.target.color
                ):
                    continue
                recaptures.append(
                    DefenseRelation(
                        defender=defender,
                        defended=attack.target,
                        against=attack.attacker,
                        recapture=move,
                    )
                )
            defenses.setdefault(attack.target, {})[attack.attacker] = recaptures

        facts: dict[OriginalPieceId, PieceRelationFacts] = {}
        for runtime in tracker.pieces:
            incoming = tuple(item for item in attacks if item.target == runtime.id)
            by_attacker = defenses.get(runtime.id, {})
            defender_ids = sorted(
                {
                    defense.defender
                    for relations in by_attacker.values()
                    for defense in relations
                },
                key=str,
            )
            pinned, pinner, ray = _pin_facts(board, tracker, runtime.id)
            facts[runtime.id] = PieceRelationFacts(
                piece=runtime.id,
                square=runtime.current_square,
                attacks=tuple(item for item in attacks if item.attacker == runtime.id),
                attackers=incoming,
                defenders_by_attacker=MappingProxyType(
                    {
                        attacker: tuple(relations)
                        for attacker, relations in by_attacker.items()
                    }
                ),
                distinct_defenders=tuple(defender_ids),
                king_pinned=pinned,
                pinned_by=pinner,
                pin_ray=ray,
                legal_moves=legal_by_piece[runtime.id],
                legal_captures=captures_by_piece[runtime.id],
            )

        if board.fen(en_passant="fen") != live_fen:
            raise RuntimeError("Position analysis mutated the live board.")
        return PositionRelations(facts)


def board_for_color(board: chess.Board, color: chess.Color) -> chess.Board:
    """Return an isolated position whose legal generator evaluates ``color``."""

    candidate = board.copy(stack=False)
    if candidate.turn != color:
        candidate.turn = color
        candidate.ep_square = None
    return candidate


def _capture_square(board: chess.Board, move: chess.Move) -> chess.Square:
    if board.is_en_passant(move):
        return move.to_square + (-8 if board.turn == chess.WHITE else 8)
    return move.to_square


def _pin_facts(
    board: chess.Board,
    tracker: OriginalPieceTracker,
    piece: OriginalPieceId,
) -> tuple[bool, OriginalPieceId | None, tuple[chess.Square, ...]]:
    runtime = tracker.get(piece)
    square = runtime.current_square
    if square is None:
        return False, None, ()
    color = _color(piece.color)
    if not board.is_pinned(color, square):
        return False, None, ()
    king = board.king(color)
    if king is None:
        return True, None, ()
    mask = board.pin(color, square)
    ray = tuple(sorted(mask))
    pinner: OriginalPieceId | None = None
    direction = _direction(king, square)
    if direction is not None:
        cursor = square + direction
        while 0 <= cursor < 64 and _same_line(square, cursor, direction):
            occupant = board.piece_at(cursor)
            if occupant is not None:
                if occupant.color != color:
                    pinner = tracker.piece_id_at(cursor)
                break
            cursor += direction
    return True, pinner, ray


def _direction(origin: int, target: int) -> int | None:
    file_delta = chess.square_file(target) - chess.square_file(origin)
    rank_delta = chess.square_rank(target) - chess.square_rank(origin)
    if file_delta == 0:
        return 8 if rank_delta > 0 else -8
    if rank_delta == 0:
        return 1 if file_delta > 0 else -1
    if abs(file_delta) == abs(rank_delta):
        return (8 if rank_delta > 0 else -8) + (1 if file_delta > 0 else -1)
    return None


def _same_line(origin: int, square: int, direction: int) -> bool:
    if direction in {-1, 1}:
        return chess.square_rank(origin) == chess.square_rank(square)
    if direction in {-7, 7, -9, 9}:
        return abs(chess.square_file(square) - chess.square_file(origin)) == abs(
            chess.square_rank(square) - chess.square_rank(origin)
        )
    return True


def _color(name: str) -> chess.Color:
    return chess.WHITE if name == "white" else chess.BLACK
