"""Chess game state and legal move interaction."""

from __future__ import annotations

from dataclasses import dataclass

from Chessnut import Game

from .board import FILES, ParsedFen, format_fen, parse_fen

SQUARE_COUNT = 64


def square_from_name(name: str) -> int:
    """Convert algebraic coordinates to an a1-based square index."""

    if len(name) != 2 or name[0] not in FILES or name[1] not in "12345678":
        raise ValueError(f"Invalid square name: {name!r}.")
    return (int(name[1]) - 1) * 8 + FILES.index(name[0])


def square_name(square: int) -> str:
    """Convert an a1-based square index to algebraic coordinates."""

    if square < 0 or square >= SQUARE_COUNT:
        raise ValueError(f"Square index must be between 0 and 63, not {square}.")
    return f"{FILES[square % 8]}{(square // 8) + 1}"


@dataclass(frozen=True, slots=True)
class ChessMove:
    """A legal move represented independently of the rules library."""

    uci: str
    from_square: int
    to_square: int
    promotion: str | None = None

    @classmethod
    def from_uci(cls, uci: str) -> ChessMove:
        if len(uci) not in {4, 5}:
            raise ValueError(f"Invalid UCI move: {uci!r}.")
        return cls(
            uci=uci,
            from_square=square_from_name(uci[:2]),
            to_square=square_from_name(uci[2:4]),
            promotion=uci[4] if len(uci) == 5 else None,
        )


@dataclass(slots=True)
class BoardInteraction:
    """Transient interaction state owned by the game controller."""

    selected_square: int | None = None
    legal_moves: tuple[ChessMove, ...] = ()
    quiet_targets: frozenset[int] = frozenset()
    capture_targets: frozenset[int] = frozenset()
    pending_move: ChessMove | None = None
    hover_square: int | None = None
    last_move: ChessMove | None = None
    checked_king: int | None = None


class GameController:
    """Own mutable chess state and expose renderer-friendly interaction data."""

    def __init__(self, position: ParsedFen) -> None:
        self.original_fen = format_fen(position)
        self._game = Game(self.original_fen)
        self.position = position
        self.interaction = BoardInteraction()
        self._update_checked_king()

    def set_hover(self, square: int | None) -> None:
        self.interaction.hover_square = square

    def select_square(self, square: int) -> bool:
        """Select a movable piece belonging to the active player."""

        piece = self.piece_at(square)
        if piece == ".":
            self.clear_selection()
            return False
        owner = "w" if piece.isupper() else "b"
        if owner != self.position.active_color:
            return False

        legal_moves = tuple(
            ChessMove.from_uci(move)
            for move in self._game.get_moves()
            if move.startswith(square_name(square))
        )
        if not legal_moves:
            self.clear_selection()
            return False

        self.interaction.selected_square = square
        self.interaction.legal_moves = legal_moves
        self.interaction.capture_targets = frozenset(
            move.to_square for move in legal_moves if self.is_capture(move)
        )
        self.interaction.quiet_targets = frozenset(
            move.to_square for move in legal_moves if not self.is_capture(move)
        )
        self.interaction.pending_move = None
        return True

    def choose_destination(self, square: int) -> bool:
        """Create a pending move when square is a legal destination."""

        candidates = tuple(
            move for move in self.interaction.legal_moves if move.to_square == square
        )
        if not candidates:
            return False

        self.interaction.pending_move = next(
            (move for move in candidates if move.promotion == "q"), candidates[0]
        )
        return True

    def handle_square(self, square: int) -> None:
        """Apply click selection semantics to a board square."""

        if self.interaction.selected_square is not None and self.choose_destination(
            square
        ):
            return
        self.select_square(square)

    def confirm_move(self) -> ChessMove | None:
        """Apply and return the pending legal move."""

        move = self.interaction.pending_move
        if move is None:
            return None

        self._game.apply_move(move.uci)
        self.position = parse_fen(self._game.get_fen())
        hover_square = self.interaction.hover_square
        self.interaction = BoardInteraction(
            hover_square=hover_square,
            last_move=move,
        )
        self._update_checked_king()
        return move

    def clear_selection(self) -> None:
        """Cancel selection and any pending move without changing the position."""

        self.interaction.selected_square = None
        self.interaction.legal_moves = ()
        self.interaction.quiet_targets = frozenset()
        self.interaction.capture_targets = frozenset()
        self.interaction.pending_move = None

    def piece_at(self, square: int) -> str:
        rank = square // 8
        file_index = square % 8
        return self.position.board[7 - rank][file_index]

    def is_capture(self, move: ChessMove) -> bool:
        """Return whether a legal move captures a piece, including en passant."""

        if self.piece_at(move.to_square) != ".":
            return True
        piece = self.piece_at(move.from_square)
        return piece.lower() == "p" and move.from_square % 8 != move.to_square % 8

    def _update_checked_king(self) -> None:
        board_text = "".join("".join(row) for row in self.position.board)
        if board_text.count("K") != 1 or board_text.count("k") != 1:
            self.interaction.checked_king = None
            return
        if self._game.status not in {Game.CHECK, Game.CHECKMATE}:
            self.interaction.checked_king = None
            return

        king = "K" if self.position.active_color == "w" else "k"
        row_index, file_index = next(
            (row_index, file_index)
            for row_index, row in enumerate(self.position.board)
            for file_index, piece in enumerate(row)
            if piece == king
        )
        self.interaction.checked_king = ((7 - row_index) * 8) + file_index
