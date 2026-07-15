from __future__ import annotations

import os
from pathlib import Path
import sys
from typing import TextIO, cast

import pytest
import textual

from chess_tui import AppMode, DEFAULT_STARTING_FEN, RendererMode, parse_fen
from chess_tui import runtime
from chess_tui.board import PIECE_GLYPHS, PIECE_SPRITES
from chess_tui.cli import build_parser, main
from chess_tui.runtime import (
    REQUIRED_PYTHON_CHESS_VERSION,
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


def _executable(tmp_path: Path) -> Path:
    engine = tmp_path / "stockfish"
    engine.write_text("fixture", encoding="utf-8")
    engine.chmod(0o755)
    return engine


def test_required_textual_runtime_is_available() -> None:
    validate_textual_runtime(cast(TextIO, FakeTty("utf-8")))

    assert textual.__version__ == REQUIRED_TEXTUAL_VERSION


def test_required_pixel_mask_renderer_is_available() -> None:
    renderer = validate_textual_runtime(
        cast(TextIO, FakeTty("utf-8")),
        renderer_mode=RendererMode.PIXEL_MASK,
    )

    assert renderer is not None
    assert renderer.mode is RendererMode.PIXEL_MASK


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


def test_runtime_rejects_wrong_python_chess_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_version(package: str) -> str:
        versions = {
            "rich": REQUIRED_RICH_VERSION,
            "textual": REQUIRED_TEXTUAL_VERSION,
            "python-chess": "0.0.0",
        }
        return versions[package]

    monkeypatch.setattr(runtime, "version", fake_version)

    with pytest.raises(
        RuntimeRequirementError,
        match=f"Python-chess {REQUIRED_PYTHON_CHESS_VERSION} is required",
    ):
        validate_textual_runtime(cast(TextIO, FakeTty("utf-8")))


def test_runtime_rejects_non_single_cell_glyph(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invalid_glyphs = dict(PIECE_GLYPHS)
    invalid_glyphs["K"] = "🙂"
    monkeypatch.setattr("chess_tui.renderers.unicode.PIECE_GLYPHS", invalid_glyphs)

    with pytest.raises(RuntimeRequirementError, match="exactly one terminal cell"):
        validate_textual_runtime(
            cast(TextIO, FakeTty("utf-8")),
            renderer_mode=RendererMode.UNICODE,
        )


def test_runtime_rejects_wrong_sprite_cell_width(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invalid_sprites = dict(PIECE_SPRITES)
    invalid_sprites["K"] = ("too wide", "  █   ", "▀███▀ ")
    monkeypatch.setattr(
        "chess_tui.renderers.legacy_sprite.PIECE_SPRITES", invalid_sprites
    )

    with pytest.raises(RuntimeRequirementError, match="sprite rows must occupy"):
        validate_textual_runtime(
            cast(TextIO, FakeTty("utf-8")),
            renderer_mode=RendererMode.LEGACY_SPRITE,
        )


def test_cli_rejects_non_interactive_output(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("chess_tui.cli.shutil.which", lambda name: sys.executable)
    with pytest.raises(SystemExit) as exc_info:
        main([])

    assert exc_info.value.code == 2
    assert "requires an interactive TTY" in capsys.readouterr().err


def test_cli_parser_accepts_explicit_renderer_mode() -> None:
    args = build_parser().parse_args(["--renderer", "legacy-sprite"])

    assert args.renderer == "legacy-sprite"


def test_cli_parser_defaults_to_flow_mode() -> None:
    args = build_parser().parse_args([])

    assert args.mode == "flow"


def test_cli_parser_accepts_quiz_demo_mode() -> None:
    args = build_parser().parse_args(["--mode", "quiz-demo"])

    assert args.mode == "quiz-demo"


def test_cli_parser_accepts_flow_mode_with_flow() -> None:
    args = build_parser().parse_args(["--mode", "flow", "--flow", "flows/london.toml"])

    assert args.mode == "flow"
    assert str(args.flow) == "flows/london.toml"


def test_cli_parser_accepts_explicit_engine_path() -> None:
    args = build_parser().parse_args(
        [
            "--mode",
            "flow",
            "--flow",
            "flows/london.toml",
            "--engine",
            "/opt/stockfish",
        ]
    )

    assert str(args.engine) == "/opt/stockfish"


def test_cli_parser_accepts_black_selection_opt_out() -> None:
    args = build_parser().parse_args(["--select-black"])

    assert args.select_black


def test_cli_flow_mode_fails_when_stockfish_is_unavailable(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("chess_tui.cli.shutil.which", lambda name: None)
    with pytest.raises(SystemExit) as exc_info:
        main(["--mode", "flow"])

    assert exc_info.value.code == 2
    assert "Stockfish is required for flow mode" in capsys.readouterr().err


def test_cli_rejects_engine_outside_flow_mode(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["--mode", "local-game", "--engine", "/missing/stockfish"])

    assert exc_info.value.code == 2
    assert "--engine is only supported with --mode flow" in capsys.readouterr().err


def test_cli_rejects_black_selection_outside_flow_mode(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["--mode", "local-game", "--select-black"])

    assert exc_info.value.code == 2
    assert "--select-black is only supported" in capsys.readouterr().err


def test_cli_rejects_missing_engine_executable(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(
            [
                "--mode",
                "flow",
                "--flow",
                "flows/london.toml",
                "--engine",
                "/missing/stockfish",
            ]
        )

    assert exc_info.value.code == 2
    assert "Engine executable does not exist" in capsys.readouterr().err


def test_cli_renderer_flag_overrides_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[RendererMode] = []

    def fake_validate(
        stream: TextIO, *, renderer_mode: RendererMode | str | None = None
    ):
        assert renderer_mode is not None
        captured.append(RendererMode(renderer_mode))
        return object()

    def fake_run(position, *, renderer=None, mode=AppMode.LOCAL_GAME):
        assert renderer is not None
        assert mode is AppMode.LOCAL_GAME

    monkeypatch.setenv("CHESS_TUI_RENDERER", "unicode")
    monkeypatch.setattr("chess_tui.cli.validate_textual_runtime", fake_validate)
    monkeypatch.setattr("chess_tui.cli.run_chess_app", fake_run)

    assert main(["--mode", "local-game", "--renderer", "legacy-sprite"]) == 0
    assert captured == [RendererMode.LEGACY_SPRITE]


def test_cli_environment_renderer_is_used_when_flag_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[RendererMode] = []

    def fake_validate(
        stream: TextIO, *, renderer_mode: RendererMode | str | None = None
    ):
        assert renderer_mode is not None
        captured.append(RendererMode(renderer_mode))
        return object()

    monkeypatch.setenv("CHESS_TUI_RENDERER", "unicode")
    monkeypatch.setattr("chess_tui.cli.validate_textual_runtime", fake_validate)
    monkeypatch.setattr(
        "chess_tui.cli.run_chess_app",
        lambda position, *, renderer=None, mode=AppMode.LOCAL_GAME: None,
    )

    assert main(["--mode", "local-game"]) == 0
    assert captured == [RendererMode.UNICODE]


def test_cli_passes_quiz_demo_mode_to_app(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[AppMode] = []

    monkeypatch.setattr(
        "chess_tui.cli.validate_textual_runtime",
        lambda stream, *, renderer_mode=None: object(),
    )
    monkeypatch.setattr(
        "chess_tui.cli.run_chess_app",
        lambda position, *, renderer=None, mode=AppMode.LOCAL_GAME: captured.append(
            mode
        ),
    )

    assert main(["--mode", "quiz-demo"]) == 0
    assert captured == [AppMode.QUIZ_DEMO]


def test_cli_default_uses_most_recent_flow_and_stockfish_from_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    flow_directory = tmp_path / "flows"
    flow_directory.mkdir()
    older = flow_directory / "other.toml"
    london = flow_directory / "london.toml"
    older.write_text("older", encoding="utf-8")
    london.write_text("recent", encoding="utf-8")
    os.utime(older, ns=(1, 1))
    os.utime(london, ns=(2, 2))
    engine = _executable(tmp_path)
    captured: list[tuple[AppMode, str, str, bool, bool]] = []
    monkeypatch.setattr("chess_tui.cli.DEFAULT_FLOW_DIRECTORY", flow_directory)
    monkeypatch.setattr("chess_tui.cli.shutil.which", lambda name: str(engine))
    monkeypatch.setattr(
        "chess_tui.cli.validate_textual_runtime",
        lambda stream, *, renderer_mode=None: object(),
    )

    def fake_run(
        position,
        *,
        renderer=None,
        mode=AppMode.LOCAL_GAME,
        flow_path=None,
        engine_path=None,
        auto_play_black=False,
        focus_san_on_white_turn=False,
    ) -> None:
        captured.append(
            (
                mode,
                str(flow_path),
                str(engine_path),
                auto_play_black,
                focus_san_on_white_turn,
            )
        )

    monkeypatch.setattr("chess_tui.cli.run_chess_app", fake_run)

    assert main([]) == 0
    assert captured == [(AppMode.FLOW, str(london), str(engine.resolve()), True, True)]


def test_cli_passes_explicit_engine_to_flow_app(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = _executable(tmp_path)
    captured: list[tuple[AppMode, str, str, bool, bool]] = []
    monkeypatch.setattr(
        "chess_tui.cli.validate_textual_runtime",
        lambda stream, *, renderer_mode=None: object(),
    )

    def fake_run(
        position,
        *,
        renderer=None,
        mode=AppMode.LOCAL_GAME,
        flow_path=None,
        engine_path=None,
        auto_play_black=False,
        focus_san_on_white_turn=False,
    ) -> None:
        captured.append(
            (
                mode,
                str(flow_path),
                str(engine_path),
                auto_play_black,
                focus_san_on_white_turn,
            )
        )

    monkeypatch.setattr("chess_tui.cli.run_chess_app", fake_run)

    assert (
        main(
            [
                "--mode",
                "flow",
                "--flow",
                "flows/london.toml",
                "--engine",
                str(engine),
                "--select-black",
            ]
        )
        == 0
    )
    assert captured == [
        (AppMode.FLOW, "flows/london.toml", str(engine.resolve()), False, True)
    ]


def test_package_smoke() -> None:
    position = parse_fen(DEFAULT_STARTING_FEN)

    assert position.board[0] == tuple("rnbqkbnr")
