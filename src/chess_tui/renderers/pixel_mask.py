"""Strict native-size renderer for the packaged 8x8 pixel masks."""

from __future__ import annotations

from dataclasses import dataclass, field
from importlib import resources
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 compatibility
    import tomli as tomllib  # pyright: ignore[reportMissingImports]

from rich.cells import cell_len
from rich.segment import Segment
from rich.style import Style

from .errors import RendererStartupError
from .colors import LAST_MOVE_SQUARE
from .mode import RendererMode

PIECE_NAMES = {
    "pawn",
    "knight",
    "bishop",
    "rook",
    "queen",
    "king",
}
PIECE_NAME_BY_SYMBOL = {
    "P": "pawn",
    "N": "knight",
    "B": "bishop",
    "R": "rook",
    "Q": "queen",
    "K": "king",
}
PIXEL_SYMBOLS = frozenset("_AB")
PALETTE_SYMBOLS = frozenset("AB")
PIXEL_MASK_SQUARE_WIDTH = 8
PIXEL_MASK_SQUARE_HEIGHT = 4

RGB = tuple[int, int, int]
RenderedSquare = tuple[tuple[Segment, ...], ...]


class PixelMaskError(RendererStartupError):
    """Raised when pixel-mask assets or geometry violate the strict contract."""


@dataclass(frozen=True, slots=True)
class PixelMaskPieceSet:
    name: str
    width: int
    height: int
    baseline: int
    transparent: str
    white_palette: dict[str, str]
    black_palette: dict[str, str]
    pieces: dict[str, tuple[str, ...]]


def load_retro_8_piece_set() -> PixelMaskPieceSet:
    """Load and validate the packaged retro-8 TOML asset."""

    asset = resources.files("chess_tui").joinpath("assets", "pieces", "retro-8.toml")
    try:
        raw = asset.read_bytes()
    except FileNotFoundError as exc:
        raise PixelMaskError(
            "Required pixel-mask asset is missing: retro-8.toml"
        ) from exc

    try:
        data = tomllib.loads(raw.decode("utf-8"))
        if data.get("version") != 1:
            raise PixelMaskError("The retro-8 piece-set version must be 1.")
        palette = _mapping(data, "palette")
        pieces = _mapping(data, "pieces")
        piece_set = PixelMaskPieceSet(
            name=_string(data, "name"),
            width=_integer(data, "width"),
            height=_integer(data, "height"),
            baseline=_integer(data, "baseline"),
            transparent=_string(data, "transparent"),
            white_palette=_string_mapping(_mapping(palette, "white")),
            black_palette=_string_mapping(_mapping(palette, "black")),
            pieces={
                name: tuple(_string_list(_mapping(pieces, name).get("pixels"), name))
                for name in pieces
            },
        )
    except PixelMaskError:
        raise
    except (KeyError, TypeError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise PixelMaskError(f"Invalid retro-8.toml: {exc}") from exc

    validate_piece_set(piece_set)
    return piece_set


def _mapping(mapping: object, key: str) -> dict[str, Any]:
    if not isinstance(mapping, dict):
        raise PixelMaskError(f"Expected a table while reading {key!r}.")
    value = mapping.get(key)
    if not isinstance(value, dict) or not all(
        isinstance(item_key, str) for item_key in value
    ):
        raise PixelMaskError(f"{key!r} must be a TOML table.")
    return value


def _string(mapping: dict[str, Any], key: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str):
        raise PixelMaskError(f"{key!r} must be a string.")
    return value


def _integer(mapping: dict[str, Any], key: str) -> int:
    value = mapping.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise PixelMaskError(f"{key!r} must be an integer.")
    return value


def _string_mapping(mapping: dict[str, Any]) -> dict[str, str]:
    if not all(isinstance(value, str) for value in mapping.values()):
        raise PixelMaskError("Palette values must be strings.")
    return dict(mapping)


def _string_list(value: object, piece_name: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(row, str) for row in value):
        raise PixelMaskError(f"{piece_name}.pixels must be an array of strings.")
    return value


def validate_piece_set(piece_set: PixelMaskPieceSet) -> None:
    """Enforce the complete retro-8 asset contract."""

    if piece_set.name != "retro-8":
        raise PixelMaskError("The pixel-mask piece set must be named 'retro-8'.")
    if piece_set.width != 8 or piece_set.height != 8:
        raise PixelMaskError("The retro-8 piece set must be exactly 8x8 pixels.")
    if piece_set.baseline != 6:
        raise PixelMaskError("The retro-8 baseline must be row 6.")
    if piece_set.transparent != "_":
        raise PixelMaskError("The retro-8 transparent symbol must be '_'.")

    actual_names = set(piece_set.pieces)
    if actual_names != PIECE_NAMES:
        missing = sorted(PIECE_NAMES - actual_names)
        unexpected = sorted(actual_names - PIECE_NAMES)
        raise PixelMaskError(
            f"Invalid piece definitions. Missing: {missing}. "
            f"Unexpected: {unexpected}."
        )

    for color_name, palette in (
        ("white", piece_set.white_palette),
        ("black", piece_set.black_palette),
    ):
        if set(palette) != PALETTE_SYMBOLS:
            raise PixelMaskError(
                f"{color_name} palette must define exactly "
                f"{sorted(PALETTE_SYMBOLS)}."
            )
        for symbol, color in palette.items():
            if (
                len(color) != 7
                or not color.startswith("#")
                or not all(
                    character in "0123456789abcdefABCDEF" for character in color[1:]
                )
            ):
                raise PixelMaskError(
                    f"Invalid color {color!r} for {color_name}.{symbol}."
                )

    for piece_name, rows in piece_set.pieces.items():
        if len(rows) != 8:
            raise PixelMaskError(f"{piece_name} has {len(rows)} rows; expected 8.")
        for row_index, row in enumerate(rows):
            if len(row) != 8:
                raise PixelMaskError(
                    f"{piece_name}, row {row_index} has width "
                    f"{len(row)}; expected 8."
                )
            invalid = set(row) - PIXEL_SYMBOLS
            if invalid:
                raise PixelMaskError(
                    f"{piece_name}, row {row_index} contains invalid symbols: "
                    f"{sorted(invalid)}."
                )

        if any(
            symbol != piece_set.transparent
            for row in rows[piece_set.baseline + 1 :]
            for symbol in row
        ):
            raise PixelMaskError(
                f"{piece_name} contains visible pixels below baseline row "
                f"{piece_set.baseline}."
            )
        if all(symbol == piece_set.transparent for symbol in rows[piece_set.baseline]):
            raise PixelMaskError(
                f"{piece_name} does not touch baseline row {piece_set.baseline}."
            )
        if all(symbol == piece_set.transparent for row in rows for symbol in row):
            raise PixelMaskError(f"{piece_name} contains no visible pixels.")


def hex_to_rgb(value: str) -> RGB:
    """Convert a validated #RRGGBB color to an RGB tuple."""

    if (
        len(value) != 7
        or not value.startswith("#")
        or not all(character in "0123456789abcdefABCDEF" for character in value[1:])
    ):
        raise PixelMaskError(f"Invalid RGB color: {value!r}.")
    return (int(value[1:3], 16), int(value[3:5], 16), int(value[5:7], 16))


def rasterize_piece(
    *,
    rows: tuple[str, ...],
    palette: dict[str, str],
    background: str,
) -> tuple[tuple[RGB, ...], ...]:
    """Resolve an 8x8 symbolic mask to concrete RGB pixels."""

    background_rgb = hex_to_rgb(background)
    resolved_palette = {symbol: hex_to_rgb(color) for symbol, color in palette.items()}
    try:
        return tuple(
            tuple(
                background_rgb if symbol == "_" else resolved_palette[symbol]
                for symbol in row
            )
            for row in rows
        )
    except KeyError as exc:
        raise PixelMaskError(f"No palette color for symbol {exc.args[0]!r}.") from exc


def rgb_string(rgb: RGB) -> str:
    red, green, blue = rgb
    return f"#{red:02x}{green:02x}{blue:02x}"


def raster_to_half_blocks(
    raster: tuple[tuple[RGB, ...], ...],
) -> RenderedSquare:
    """Map exactly 8x8 RGB pixels to 8x4 terminal half-block cells."""

    if len(raster) != 8:
        raise PixelMaskError(f"Expected raster height 8; received {len(raster)}.")
    if any(len(row) != 8 for row in raster):
        raise PixelMaskError("Every raster row must contain exactly 8 pixels.")

    output: list[tuple[Segment, ...]] = []
    for top_row_index in range(0, 8, 2):
        top_row = raster[top_row_index]
        bottom_row = raster[top_row_index + 1]
        output.append(
            tuple(
                Segment(
                    "▀",
                    Style(color=rgb_string(top), bgcolor=rgb_string(bottom)),
                )
                for top, bottom in zip(top_row, bottom_row, strict=True)
            )
        )
    return tuple(output)


def render_piece_square(
    *,
    piece: str,
    background: str,
    piece_set: PixelMaskPieceSet,
    outline: str | None = None,
) -> RenderedSquare:
    """Render one board designator at the piece set's native dimensions."""

    if piece == ".":
        background_rgb = hex_to_rgb(background)
        raster = tuple(tuple(background_rgb for _ in range(8)) for _ in range(8))
    else:
        if piece.upper() not in PIECE_NAME_BY_SYMBOL:
            raise PixelMaskError(f"Unknown chess piece designator: {piece!r}.")

        piece_name = PIECE_NAME_BY_SYMBOL[piece.upper()]
        palette = (
            piece_set.white_palette if piece.isupper() else piece_set.black_palette
        )
        raster = rasterize_piece(
            rows=piece_set.pieces[piece_name],
            palette=palette,
            background=background,
        )

    if outline is not None:
        outline_rgb = hex_to_rgb(outline)
        raster = tuple(
            tuple(
                outline_rgb if x in {0, 7} or y in {0, 7} else pixel
                for x, pixel in enumerate(row)
            )
            for y, row in enumerate(raster)
        )
    return raster_to_half_blocks(raster)


@dataclass(slots=True)
class PixelMaskPieceRenderer:
    """Render retro-8 masks without resizing or loading another piece source."""

    piece_set: PixelMaskPieceSet
    mode: RendererMode = RendererMode.PIXEL_MASK
    _cache: dict[tuple[str, str, str], RenderedSquare] = field(default_factory=dict)

    def render_square_rows(
        self,
        *,
        piece: str,
        square_width: int,
        square_height: int,
        background: str,
        visual_state: str,
        quiet_target: bool,
        capture_target: bool,
    ) -> RenderedSquare:
        if (
            square_width != PIXEL_MASK_SQUARE_WIDTH
            or square_height != PIXEL_MASK_SQUARE_HEIGHT
        ):
            raise PixelMaskError(
                "pixel-mask requires exactly 8x4 terminal cells per square; "
                f"received {square_width}x{square_height}."
            )
        cache_key = (piece, background, visual_state)
        rendered = self._cache.get(cache_key)
        if rendered is None:
            rendered = render_piece_square(
                piece=piece,
                background=background,
                piece_set=self.piece_set,
                outline=(LAST_MOVE_SQUARE if visual_state == "last-move" else None),
            )
            self._cache[cache_key] = rendered
        return rendered


def build_pixel_mask_renderer() -> PixelMaskPieceRenderer:
    """Load retro-8 and verify the terminal half-block contract."""

    if cell_len("▀") != 1:
        raise PixelMaskError(
            "The pixel-mask half-block glyph must occupy exactly one terminal cell."
        )
    renderer = PixelMaskPieceRenderer(load_retro_8_piece_set())
    sample = renderer.render_square_rows(
        piece="P",
        square_width=PIXEL_MASK_SQUARE_WIDTH,
        square_height=PIXEL_MASK_SQUARE_HEIGHT,
        background="#000000",
        visual_state="normal",
        quiet_target=False,
        capture_target=False,
    )
    if len(sample) != 4 or any(
        sum(segment.cell_length for segment in row) != 8 for row in sample
    ):
        raise PixelMaskError("Pixel-mask renderer self-test failed.")
    return renderer
