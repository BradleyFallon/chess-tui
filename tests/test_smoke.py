from __future__ import annotations

from typing import TextIO, cast

import pytest
import textual

from chess_tui import DEFAULT_STARTING_FEN, parse_fen
from chess_tui import runtime
from chess_tui.board import PIECE_GLYPHS
from chess_tui.cli import main
from chess_tui.runtime import (
    REQUIRED_RICH_VERSION,
    REQUIRED_TEXTUAL_VERSION,
    RuntimeRequirementError,
    TerminalCapabilityError,
    validate_textual_runtime,
)


class FakeTty:
    def __init__(self, encoding: str) -> None:
        self.encoding = encoding

    def isatty(self) -> bool:
        return True


def test_required_textual_runtime_is_available() -> None:
    validate_textual_runtime(cast(TextIO, FakeTty("utf-8")))

    assert textual.__version__ == REQUIRED_TEXTUAL_VERSION


def test_runtime_rejects_non_utf8_terminal() -> None:
    with pytest.raises(TerminalCapabilityError, match="requires UTF-8"):
        validate_textual_runtime(cast(TextIO, FakeTty("ascii")))


def test_runtime_rejects_wrong_textual_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_version(package: str) -> str:
        return REQUIRED_RICH_VERSION if package == "rich" else "0.0.0"

    monkeypatch.setattr(runtime, "version", fake_version)

    with pytest.raises(RuntimeRequirementError, match="Textual 8.2.8 is required"):
        validate_textual_runtime(cast(TextIO, FakeTty("utf-8")))


def test_runtime_rejects_non_single_cell_glyph(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invalid_glyphs = dict(PIECE_GLYPHS)
    invalid_glyphs["K"] = "🙂"
    monkeypatch.setattr(runtime, "PIECE_GLYPHS", invalid_glyphs)

    with pytest.raises(TerminalCapabilityError, match="exactly one terminal cell"):
        validate_textual_runtime(cast(TextIO, FakeTty("utf-8")))


def test_cli_rejects_non_interactive_output(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main([])

    assert exc_info.value.code == 2
    assert "requires an interactive TTY" in capsys.readouterr().err


def test_package_smoke() -> None:
    position = parse_fen(DEFAULT_STARTING_FEN)

    assert position.board[0] == tuple("rnbqkbnr")
