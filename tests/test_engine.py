from __future__ import annotations

import asyncio
from pathlib import Path
import time
from types import SimpleNamespace
from typing import Any, cast

import chess
import chess.engine
import pytest

from chess_tui.engine import (
    ENGINE_PROTOTYPE_PROFILE,
    EngineProcessError,
    EngineResultError,
    EngineStartupError,
    EngineTimeoutError,
    FixtureEngineService,
    StockfishEngineService,
)
from chess_tui.opening import StockfishBotMoveSource, SuggestionKind


def _executable(tmp_path: Path) -> Path:
    path = tmp_path / "stockfish"
    path.write_text("fixture", encoding="utf-8")
    path.chmod(0o755)
    return path


class FakeEngine:
    def __init__(self, move: chess.Move) -> None:
        self.move = move
        self.play_calls = 0
        self.quit_calls = 0
        self.active_calls = 0
        self.max_active_calls = 0

    def play(self, board: chess.Board, limit: chess.engine.Limit):
        self.play_calls += 1
        self.active_calls += 1
        self.max_active_calls = max(self.max_active_calls, self.active_calls)
        time.sleep(0.01)
        self.active_calls -= 1
        return SimpleNamespace(move=self.move)

    def quit(self) -> None:
        self.quit_calls += 1


def test_fixture_engine_returns_one_deterministic_legal_move() -> None:
    async def run_test() -> None:
        board = chess.Board()
        service = FixtureEngineService(session_seed=7)
        first = await service.choose_move(board, ENGINE_PROTOTYPE_PROFILE)
        repeated = await service.choose_move(board, ENGINE_PROTOTYPE_PROFILE)

        assert first == repeated
        assert first in board.legal_moves
        await service.close()
        with pytest.raises(EngineProcessError, match="closed"):
            await service.choose_move(board, ENGINE_PROTOTYPE_PROFILE)

    asyncio.run(run_test())


def test_stockfish_service_is_lazy_persistent_serialized_and_idempotent(
    tmp_path: Path,
) -> None:
    async def run_test() -> None:
        board = chess.Board()
        fake = FakeEngine(chess.Move.from_uci("e2e4"))
        factory_calls: list[str] = []

        def factory(path: str):
            factory_calls.append(path)
            return cast(Any, fake)

        service = StockfishEngineService(_executable(tmp_path), engine_factory=factory)
        assert factory_calls == []

        first, second = await asyncio.gather(
            service.choose_move(board, ENGINE_PROTOTYPE_PROFILE),
            service.choose_move(board, ENGINE_PROTOTYPE_PROFILE),
        )
        assert first == second == chess.Move.from_uci("e2e4")
        assert len(factory_calls) == 1
        assert fake.play_calls == 2
        assert fake.max_active_calls == 1

        await service.close()
        await service.close()
        assert fake.quit_calls == 1

    asyncio.run(run_test())


@pytest.mark.parametrize(
    ("failure", "error_type"),
    [
        (OSError("not a UCI engine"), EngineStartupError),
        (TimeoutError("startup timeout"), EngineTimeoutError),
    ],
)
def test_stockfish_startup_failures_are_typed(
    tmp_path: Path,
    failure: Exception,
    error_type: type[Exception],
) -> None:
    async def run_test() -> None:
        def factory(path: str):
            raise failure

        service = StockfishEngineService(_executable(tmp_path), engine_factory=factory)
        with pytest.raises(error_type):
            await service.choose_move(chess.Board(), ENGINE_PROTOTYPE_PROFILE)
        await service.close()

    asyncio.run(run_test())


@pytest.mark.parametrize(
    ("failure", "error_type"),
    [
        (TimeoutError("play timeout"), EngineTimeoutError),
        (chess.engine.EngineTerminatedError("process exited"), EngineProcessError),
    ],
)
def test_stockfish_request_failures_are_typed(
    tmp_path: Path,
    failure: Exception,
    error_type: type[Exception],
) -> None:
    async def run_test() -> None:
        class FailingEngine(FakeEngine):
            def play(self, board: chess.Board, limit: chess.engine.Limit):
                raise failure

        fake = FailingEngine(chess.Move.from_uci("e2e4"))
        service = StockfishEngineService(
            _executable(tmp_path), engine_factory=lambda path: cast(Any, fake)
        )
        with pytest.raises(error_type):
            await service.choose_move(chess.Board(), ENGINE_PROTOTYPE_PROFILE)
        await service.close()

    asyncio.run(run_test())


def test_stockfish_rejects_invalid_engine_result(tmp_path: Path) -> None:
    async def run_test() -> None:
        fake = FakeEngine(chess.Move.from_uci("e7e5"))
        service = StockfishEngineService(
            _executable(tmp_path), engine_factory=lambda path: cast(Any, fake)
        )
        with pytest.raises(EngineResultError, match="illegal move"):
            await service.choose_move(chess.Board(), ENGINE_PROTOTYPE_PROFILE)
        await service.close()

    asyncio.run(run_test())


def test_stockfish_bot_source_returns_one_canonical_prototype_suggestion() -> None:
    async def run_test() -> None:
        board = chess.Board()
        engine = FixtureEngineService(session_seed=2)
        source = StockfishBotMoveSource(engine)
        suggestions = await source.moves_for(board)

        assert len(suggestions) == 1
        suggestion = suggestions[0]
        move = chess.Move.from_uci(suggestion.uci)
        assert suggestion.san == board.san(move)
        assert suggestion.kind is SuggestionKind.BOT
        assert suggestion.label == "ENGINE PROTOTYPE"
        assert suggestion.profile_id == "engine-prototype"
        await source.close()

    asyncio.run(run_test())
