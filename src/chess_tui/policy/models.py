"""Typed primitives shared by the Opening Rule Engine v4."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Mapping, TypeAlias

ColorName: TypeAlias = Literal["white", "black"]
PieceTypeName: TypeAlias = Literal["pawn", "knight", "bishop", "rook", "queen", "king"]
PieceQualifier: TypeAlias = Literal[
    "a", "b", "c", "d", "e", "f", "g", "h", "queenside", "kingside"
]


@dataclass(frozen=True, slots=True)
class OriginalPieceId:
    color: ColorName
    start_square: str

    @classmethod
    def parse(cls, value: str) -> OriginalPieceId:
        parts = value.split(":")
        if len(parts) != 2 or parts[0] not in {"white", "black"}:
            raise ValueError(
                f"Invalid original-piece id {value!r}; expected 'white:e2'."
            )
        import chess

        if parts[1] not in chess.SQUARE_NAMES:
            raise ValueError(f"Invalid original-piece square {parts[1]!r}.")
        return cls(parts[0], parts[1])  # type: ignore[arg-type]

    def __str__(self) -> str:
        return f"{self.color}:{self.start_square}"


@dataclass(frozen=True, slots=True)
class StartingPieceRef:
    color: ColorName
    piece_type: PieceTypeName
    qualifier: PieceQualifier | None = None

    @classmethod
    def parse(cls, value: str) -> StartingPieceRef:
        parts = value.split(":")
        if len(parts) not in {3, 4} or parts[0] != "piece":
            raise ValueError(
                f"Invalid starting-piece reference {value!r}; expected "
                "'piece:white:bishop:queenside'."
            )
        color, piece_type = parts[1:3]
        qualifier = parts[3] if len(parts) == 4 else None
        if color not in {"white", "black"}:
            raise ValueError(
                f"Invalid starting-piece color {color!r}; expected white or black."
            )
        if piece_type not in {
            "pawn",
            "rook",
            "knight",
            "bishop",
            "queen",
            "king",
        }:
            raise ValueError(f"Invalid starting-piece type {piece_type!r}.")
        if piece_type == "pawn":
            if qualifier not in tuple("abcdefgh"):
                raise ValueError(
                    f"Starting-piece pawn reference {value!r} requires a file "
                    "qualifier from a through h."
                )
        elif piece_type in {"rook", "knight", "bishop"}:
            if qualifier not in {"queenside", "kingside"}:
                raise ValueError(
                    f"Starting-piece {piece_type} reference {value!r} requires "
                    "queenside or kingside."
                )
        elif qualifier is not None:
            raise ValueError(
                f"Starting-piece {piece_type} reference {value!r} does not accept "
                "a qualifier."
            )
        return cls(color, piece_type, qualifier)  # type: ignore[arg-type]

    @classmethod
    def from_original(cls, piece_id: OriginalPieceId) -> StartingPieceRef:
        rank = "1" if piece_id.color == "white" else "8"
        pawn_rank = "2" if piece_id.color == "white" else "7"
        square = piece_id.start_square
        if square[1] == pawn_rank:
            return cls(piece_id.color, "pawn", square[0])  # type: ignore[arg-type]
        back_rank: dict[str, tuple[PieceTypeName, PieceQualifier | None]] = {
            f"a{rank}": ("rook", "queenside"),
            f"b{rank}": ("knight", "queenside"),
            f"c{rank}": ("bishop", "queenside"),
            f"d{rank}": ("queen", None),
            f"e{rank}": ("king", None),
            f"f{rank}": ("bishop", "kingside"),
            f"g{rank}": ("knight", "kingside"),
            f"h{rank}": ("rook", "kingside"),
        }
        try:
            piece_type, qualifier = back_rank[square]
        except KeyError as error:
            raise ValueError(
                f"Original piece {piece_id} has no canonical starting-piece reference."
            ) from error
        return cls(piece_id.color, piece_type, qualifier)

    @property
    def original_piece_id(self) -> OriginalPieceId:
        back_files = {
            ("rook", "queenside"): "a",
            ("knight", "queenside"): "b",
            ("bishop", "queenside"): "c",
            ("queen", None): "d",
            ("king", None): "e",
            ("bishop", "kingside"): "f",
            ("knight", "kingside"): "g",
            ("rook", "kingside"): "h",
        }
        if self.piece_type == "pawn":
            assert self.qualifier is not None
            file_name = self.qualifier
            rank = "2" if self.color == "white" else "7"
        else:
            file_name = back_files[(self.piece_type, self.qualifier)]
            rank = "1" if self.color == "white" else "8"
        return OriginalPieceId(self.color, f"{file_name}{rank}")

    @property
    def label(self) -> str:
        color = self.color.capitalize()
        if self.piece_type == "pawn":
            return f"{color} {self.qualifier}-pawn"
        if self.qualifier is not None:
            return f"{color} {self.qualifier} {self.piece_type}"
        return f"{color} {self.piece_type}"

    def __str__(self) -> str:
        suffix = f":{self.qualifier}" if self.qualifier is not None else ""
        return f"piece:{self.color}:{self.piece_type}{suffix}"


PieceSubject: TypeAlias = StartingPieceRef | Literal["self"]


@dataclass(frozen=True, slots=True)
class MovedCondition:
    piece: PieceSubject


@dataclass(frozen=True, slots=True)
class UnmovedCondition:
    piece: PieceSubject


@dataclass(frozen=True, slots=True)
class CapturedCondition:
    piece: PieceSubject


@dataclass(frozen=True, slots=True)
class AtCondition:
    piece: PieceSubject
    square: str


@dataclass(frozen=True, slots=True)
class OccupiedCondition:
    square: str


@dataclass(frozen=True, slots=True)
class EmptyCondition:
    square: str


@dataclass(frozen=True, slots=True)
class OccupiedByCondition:
    square: str
    color: ColorName
    piece_type: PieceTypeName


@dataclass(frozen=True, slots=True)
class AttackedCondition:
    target: PieceSubject


@dataclass(frozen=True, slots=True)
class AttackedByCondition:
    target: PieceSubject
    attacker: StartingPieceRef | None = None
    attacker_type: PieceTypeName | None = None


@dataclass(frozen=True, slots=True)
class UndefendedCondition:
    target: PieceSubject


@dataclass(frozen=True, slots=True)
class UnderDefendedCondition:
    target: PieceSubject


@dataclass(frozen=True, slots=True)
class AttackBalanceCondition:
    target: PieceSubject
    at_least: int


@dataclass(frozen=True, slots=True)
class CapturableCondition:
    target: StartingPieceRef


@dataclass(frozen=True, slots=True)
class InCheckCondition:
    color: ColorName


@dataclass(frozen=True, slots=True)
class LastMoveCondition:
    piece: PieceSubject
    to_square: str


@dataclass(frozen=True, slots=True)
class AllCondition:
    conditions: tuple[Condition, ...]


@dataclass(frozen=True, slots=True)
class AnyCondition:
    conditions: tuple[Condition, ...]


@dataclass(frozen=True, slots=True)
class NotCondition:
    condition: Condition


Condition: TypeAlias = (
    MovedCondition
    | UnmovedCondition
    | CapturedCondition
    | AtCondition
    | OccupiedCondition
    | EmptyCondition
    | OccupiedByCondition
    | AttackedCondition
    | AttackedByCondition
    | UndefendedCondition
    | UnderDefendedCondition
    | AttackBalanceCondition
    | CapturableCondition
    | InCheckCondition
    | LastMoveCondition
    | AllCondition
    | AnyCondition
    | NotCondition
)


@dataclass(frozen=True, slots=True)
class MoveAttempt:
    to_square: str


@dataclass(frozen=True, slots=True)
class CaptureAttempt:
    target_piece: StartingPieceRef | None = None
    target_type: PieceTypeName | None = None
    triggering_attacker: bool = False


ActionAttempt: TypeAlias = MoveAttempt | CaptureAttempt


@dataclass(frozen=True, slots=True)
class LastMove:
    piece: OriginalPieceId
    to_square: str


@dataclass(frozen=True, slots=True)
class ConditionResult:
    value: bool
    explanation: str
    details: Mapping[str, object] = field(default_factory=dict)
