"""FEN parsing and terminal board rendering."""

from __future__ import annotations

from dataclasses import dataclass

FILES = "abcdefgh"
PIECE_GLYPHS = {
    "P": "♙",
    "N": "♘",
    "B": "♗",
    "R": "♖",
    "Q": "♕",
    "K": "♔",
    "p": "♟",
    "n": "♞",
    "b": "♝",
    "r": "♜",
    "q": "♛",
    "k": "♚",
}
PIXEL_SPRITE_WIDTH = 5
PIXEL_SPRITE_HEIGHT = 3
PIECE_SPRITES: dict[str, tuple[str, str, str]] = {
    "P": (
        "  ●  ",
        " ▄█▄ ",
        "▀███▀",
    ),
    "N": (
        " ▄██ ",
        " ██▄ ",
        "▀███▀",
    ),
    "B": (
        "  ◆  ",
        " ▄█▄ ",
        "▀███▀",
    ),
    "R": (
        "█ █ █",
        " ███ ",
        "▀███▀",
    ),
    "Q": (
        "◆ ◆ ◆",
        " ███ ",
        "▀███▀",
    ),
    "K": (
        "  ╬  ",
        " ▄█▄ ",
        "▀███▀",
    ),
}
VALID_PIECES = frozenset(PIECE_GLYPHS)
DEFAULT_STARTING_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


class FenError(ValueError):
    """Raised when a FEN string cannot be parsed."""


@dataclass(frozen=True, slots=True)
class ParsedFen:
    """Normalized representation of a parsed FEN."""

    board: tuple[tuple[str, ...], ...]
    active_color: str
    castling: str
    en_passant: str
    halfmove_clock: int
    fullmove_number: int


def parse_fen(fen: str) -> ParsedFen:
    """Parse a FEN string into a normalized board representation."""

    text = fen.strip()
    if not text:
        raise FenError("FEN cannot be empty.")

    parts = text.split()
    if not parts:
        raise FenError("FEN cannot be empty.")
    if len(parts) > 6:
        raise FenError("FEN cannot contain more than 6 fields.")

    board_part = parts[0]
    rows = board_part.split("/")
    if len(rows) != 8:
        raise FenError("FEN board description must contain 8 ranks.")

    board: list[tuple[str, ...]] = []
    for rank_index, row in enumerate(rows, start=1):
        squares: list[str] = []
        for char in row:
            if char.isdigit():
                count = int(char)
                if count < 1 or count > 8:
                    raise FenError(
                        f"Rank {rank_index} contains an invalid empty-square count: {char!r}."
                    )
                squares.extend(["."] * count)
                continue
            if char not in VALID_PIECES:
                raise FenError(
                    f"Rank {rank_index} contains an invalid piece designator: {char!r}."
                )
            squares.append(char)

        if len(squares) != 8:
            raise FenError(
                f"Rank {rank_index} expands to {len(squares)} squares instead of 8."
            )
        board.append(tuple(squares))

    active_color = parts[1] if len(parts) > 1 else "w"
    castling = parts[2] if len(parts) > 2 else "-"
    en_passant = parts[3] if len(parts) > 3 else "-"
    halfmove_clock = _parse_int(parts, index=4, default=0, label="halfmove clock")
    fullmove_number = _parse_int(parts, index=5, default=1, label="fullmove number")

    if active_color not in {"w", "b"}:
        raise FenError(f"Active color must be 'w' or 'b', not {active_color!r}.")
    if castling == "-":
        pass
    elif "-" in castling or any(ch not in "KQkq" for ch in castling):
        raise FenError(f"Castling rights contain invalid characters: {castling!r}.")
    if en_passant != "-" and not _is_valid_square(en_passant):
        raise FenError(f"En passant square is invalid: {en_passant!r}.")
    if halfmove_clock < 0:
        raise FenError("Halfmove clock cannot be negative.")
    if fullmove_number < 1:
        raise FenError("Fullmove number must be at least 1.")

    return ParsedFen(
        board=tuple(board),
        active_color=active_color,
        castling=castling,
        en_passant=en_passant,
        halfmove_clock=halfmove_clock,
        fullmove_number=fullmove_number,
    )


def format_fen(position: ParsedFen) -> str:
    """Serialize a parsed position as a complete FEN string."""

    ranks: list[str] = []
    for row in position.board:
        fields: list[str] = []
        empty_count = 0
        for square in row:
            if square == ".":
                empty_count += 1
                continue
            if empty_count:
                fields.append(str(empty_count))
                empty_count = 0
            fields.append(square)
        if empty_count:
            fields.append(str(empty_count))
        ranks.append("".join(fields))

    return " ".join(
        (
            "/".join(ranks),
            position.active_color,
            position.castling,
            position.en_passant,
            str(position.halfmove_clock),
            str(position.fullmove_number),
        )
    )


def _parse_int(parts: list[str], *, index: int, default: int, label: str) -> int:
    if len(parts) <= index:
        return default
    try:
        return int(parts[index])
    except ValueError as exc:
        raise FenError(f"Invalid {label}: {parts[index]!r}.") from exc


def _is_valid_square(square: str) -> bool:
    if len(square) != 2:
        return False
    file_, rank = square[0], square[1]
    return file_ in FILES and rank in "12345678"
