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
    AnalysedMove,
    DEFAULT_ANALYSIS_PROFILE,
    ENGINE_PROTOTYPE_PROFILE,
    EngineProfile,
    EngineProcessError,
    EngineResultError,
    EngineStartupError,
    EngineTimeoutError,
    FixtureEngineService,
    MoveQuality,
    QualityThresholds,
    StockfishEngineService,
    assess_white_move,
    quality_for_loss,
)
from chess_tui.opening import StockfishBotMoveSource, SuggestionKind


def _executable(tmp_path: Path) -> Path:
    path = tmp_path / "stockfish"
    path.write_text("fixture", encoding="utf-8")
    path.chmod(0o755)
    return path


class FakeEngine:
    def __init__(self, move: chess.Move) -> None:
        self.id = {"name": "Stockfish Test"}
        self.move = move
        self.play_calls = 0
        self.quit_calls = 0
        self.active_calls = 0
        self.max_active_calls = 0
        self.analysis_result: list[chess.engine.InfoDict] = []

    def play(self, board: chess.Board, limit: chess.engine.Limit):
        self.play_calls += 1
        self.active_calls += 1
        self.max_active_calls = max(self.max_active_calls, self.active_calls)
        time.sleep(0.01)
        self.active_calls -= 1
        return SimpleNamespace(move=self.move)

    def quit(self) -> None:
        self.quit_calls += 1

    def analyse(
        self,
        board: chess.Board,
        limit: chess.engine.Limit,
        *,
        multipv: int,
    ) -> list[chess.engine.InfoDict]:
        return self.analysis_result


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


def test_stockfish_analysis_is_white_normalized_and_preserves_mate_scores(
    tmp_path: Path,
) -> None:
    async def run_test() -> None:
        board = chess.Board()
        board.push_san("e4")
        fake = FakeEngine(chess.Move.from_uci("e7e5"))
        fake.analysis_result = [
            {
                "score": chess.engine.PovScore(chess.engine.Cp(75), chess.BLACK),
                "depth": 14,
                "seldepth": 21,
                "nodes": 120_000,
                "nps": 1_000_000,
                "time": 0.12,
                "pv": [
                    chess.Move.from_uci("e7e5"),
                    chess.Move.from_uci("g1f3"),
                ],
            },
            {
                "score": chess.engine.PovScore(chess.engine.Mate(3), chess.BLACK),
                "pv": [chess.Move.from_uci("e7e6")],
            },
        ]
        service = StockfishEngineService(
            _executable(tmp_path), engine_factory=lambda path: cast(Any, fake)
        )

        lines = await service.analyse(board, count=2, profile=DEFAULT_ANALYSIS_PROFILE)

        assert lines[0].uci == "e7e5"
        assert lines[0].san == "e5"
        assert lines[0].evaluation_cp == -75
        assert lines[0].principal_variation == ("e7e5", "g1f3")
        assert lines[0].engine_name == "Stockfish Test"
        assert lines[0].profile_id == "analysis"
        assert lines[0].requested_depth == 20
        assert lines[0].actual_depth == 14
        assert lines[0].selective_depth == 21
        assert lines[0].nodes == 120_000
        assert lines[0].nps == 1_000_000
        assert lines[0].time_ms == 120
        assert lines[1].uci == "e7e6"
        assert lines[1].evaluation_cp is None
        assert lines[1].mate_in == -3
        await service.close()

    asyncio.run(run_test())


@pytest.mark.parametrize(
    "analysis_result",
    [
        [{"pv": [chess.Move.from_uci("e2e4")]}],
        [
            {
                "score": chess.engine.PovScore(chess.engine.Cp(0), chess.WHITE),
                "pv": [chess.Move.from_uci("e7e5")],
            }
        ],
    ],
)
def test_stockfish_rejects_invalid_analysis_rows(
    tmp_path: Path,
    analysis_result: list[chess.engine.InfoDict],
) -> None:
    async def run_test() -> None:
        fake = FakeEngine(chess.Move.from_uci("e2e4"))
        fake.analysis_result = analysis_result
        service = StockfishEngineService(
            _executable(tmp_path), engine_factory=lambda path: cast(Any, fake)
        )

        with pytest.raises(EngineResultError, match="analysis row"):
            await service.analyse(chess.Board(), count=1)
        await service.close()

    asyncio.run(run_test())


@pytest.mark.parametrize(
    ("loss_cp", "quality"),
    [
        (0, MoveQuality.BEST),
        (20, MoveQuality.BEST),
        (21, MoveQuality.GOOD),
        (60, MoveQuality.GOOD),
        (61, MoveQuality.INACCURACY),
        (120, MoveQuality.INACCURACY),
        (121, MoveQuality.MISTAKE),
        (250, MoveQuality.MISTAKE),
        (251, MoveQuality.BLUNDER),
    ],
)
def test_move_quality_threshold_boundaries(
    loss_cp: int,
    quality: MoveQuality,
) -> None:
    assert quality_for_loss(loss_cp) is quality


def test_move_quality_thresholds_are_configurable() -> None:
    thresholds = QualityThresholds(5, 10, 15, 20)

    assert quality_for_loss(6, thresholds) is MoveQuality.GOOD
    assert quality_for_loss(21, thresholds) is MoveQuality.BLUNDER


class ScriptedAnalysisEngine:
    def __init__(self, analyses: list[tuple[AnalysedMove, ...]]) -> None:
        self.analyses = analyses

    async def choose_move(
        self,
        board: chess.Board,
        profile: EngineProfile,
    ) -> chess.Move:
        return next(iter(board.legal_moves))

    async def analyse(
        self,
        board: chess.Board,
        *,
        count: int = 4,
        profile: EngineProfile | None = None,
    ) -> tuple[AnalysedMove, ...]:
        del board, count, profile
        return self.analyses.pop(0)

    async def close(self) -> None:
        return None


def test_white_move_assessment_uses_before_minus_after_evaluation() -> None:
    async def run_test() -> None:
        engine = ScriptedAnalysisEngine(
            [
                (AnalysedMove("d2d4", "d4", 50, ("d2d4",)),),
                (AnalysedMove("e7e5", "e5", -210, ("e7e5",)),),
            ]
        )
        assessment = await assess_white_move(
            engine,
            chess.Board(),
            chess.Move.from_uci("e2e4"),
        )

        assert assessment.played_uci == "e2e4"
        assert assessment.best_uci == "d2d4"
        assert assessment.evaluation_before_cp == 50
        assert assessment.evaluation_after_cp == -210
        assert assessment.loss_cp == 260
        assert assessment.quality is MoveQuality.BLUNDER

    asyncio.run(run_test())


def test_white_move_assessment_keeps_mate_separate_from_centipawns() -> None:
    async def run_test() -> None:
        engine = ScriptedAnalysisEngine(
            [
                (AnalysedMove("d2d4", "d4", None, ("d2d4",), mate_in=3),),
                (AnalysedMove("e7e5", "e5", None, ("e7e5",), mate_in=-2),),
            ]
        )
        assessment = await assess_white_move(
            engine,
            chess.Board(),
            chess.Move.from_uci("e2e4"),
        )

        assert assessment.evaluation_before_cp is None
        assert assessment.evaluation_after_cp is None
        assert assessment.loss_cp is None
        assert assessment.mate_before == 3
        assert assessment.mate_after == -2
        assert assessment.quality is MoveQuality.BLUNDER

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
