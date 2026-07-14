"""Chess TUI package."""

from .board import DEFAULT_STARTING_FEN, FenError, ParsedFen, parse_fen

__all__ = [
    "__version__",
    "DEFAULT_STARTING_FEN",
    "FenError",
    "ParsedFen",
    "parse_fen",
]

__version__ = "0.1.0"
