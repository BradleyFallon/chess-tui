"""Chess TUI package."""

from .board import DEFAULT_STARTING_FEN, FenError, ParsedFen, format_fen, parse_fen
from .modes import AppMode
from .renderers.mode import RendererMode

__all__ = [
    "__version__",
    "AppMode",
    "DEFAULT_STARTING_FEN",
    "FenError",
    "ParsedFen",
    "RendererMode",
    "format_fen",
    "parse_fen",
]

__version__ = "0.1.0"
