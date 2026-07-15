"""Persistent Stockfish service implemented with python-chess UCI support."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Callable, TypeVar

import chess
import chess.engine

from .errors import (
    EngineConfigurationError,
    EngineProcessError,
    EngineResultError,
    EngineStartupError,
    EngineTimeoutError,
)
from .models import AnalysedMove, EngineProfile

EngineFactory = Callable[[str], chess.engine.SimpleEngine]
ResultT = TypeVar("ResultT")


def validate_engine_path(path: Path | str) -> Path:
    """Validate an explicitly supplied engine executable without searching."""

    candidate = Path(path).expanduser()
    if not candidate.exists():
        raise EngineConfigurationError(f"Engine executable does not exist: {candidate}")
    if not candidate.is_file():
        raise EngineConfigurationError(f"Engine path is not a file: {candidate}")
    if not os.access(candidate, os.X_OK):
        raise EngineConfigurationError(
            f"Engine executable is not executable: {candidate}"
        )
    return candidate.resolve()


class StockfishEngineService:
    """Own one lazily started, serialized Stockfish UCI process."""

    def __init__(
        self,
        executable_path: Path | str,
        *,
        engine_factory: EngineFactory | None = None,
        analysis_time_limit_seconds: float = 0.1,
    ) -> None:
        self.executable_path = validate_engine_path(executable_path)
        if analysis_time_limit_seconds <= 0:
            raise EngineConfigurationError(
                "analysis_time_limit_seconds must be greater than zero."
            )
        self._engine_factory = engine_factory or _start_uci_engine
        self.analysis_time_limit_seconds = analysis_time_limit_seconds
        self._engine: chess.engine.SimpleEngine | None = None
        self._lock = asyncio.Lock()
        self._closed = False

    async def choose_move(
        self,
        board: chess.Board,
        profile: EngineProfile,
    ) -> chess.Move:
        if profile.time_limit_seconds <= 0:
            raise EngineConfigurationError(
                "Engine profile time_limit_seconds must be greater than zero."
            )
        position = board.copy(stack=False)
        if position.outcome() is not None:
            raise EngineResultError("The completed position has no engine move.")

        async with self._lock:
            if self._closed:
                raise EngineProcessError("The Stockfish engine service is closed.")
            engine = await self._ensure_engine()
            try:
                result = await _run_blocking(
                    engine.play,
                    position,
                    chess.engine.Limit(time=profile.time_limit_seconds),
                )
            except TimeoutError as error:
                raise EngineTimeoutError(
                    f"Stockfish timed out while choosing a move for {profile.label}."
                ) from error
            except chess.engine.EngineTerminatedError as error:
                self._engine = None
                raise EngineProcessError(
                    "Stockfish exited while choosing a move."
                ) from error
            except chess.engine.EngineError as error:
                raise EngineProcessError(
                    f"Stockfish could not choose a move: {error}"
                ) from error
            except (OSError, RuntimeError) as error:
                raise EngineProcessError(
                    f"Stockfish process failed while choosing a move: {error}"
                ) from error

            move = result.move
            if move is None:
                raise EngineResultError("Stockfish returned no move.")
            if move not in position.legal_moves:
                raise EngineResultError(
                    f"Stockfish returned illegal move {move.uci()!r}."
                )
            return move

    async def analyse(
        self,
        board: chess.Board,
        *,
        count: int = 4,
    ) -> tuple[AnalysedMove, ...]:
        if not 1 <= count <= 4:
            raise EngineConfigurationError("Analysis count must be between 1 and 4.")
        position = board.copy(stack=False)
        if position.outcome(claim_draw=False) is not None:
            raise EngineResultError("The completed position has no engine analysis.")

        async with self._lock:
            if self._closed:
                raise EngineProcessError("The Stockfish engine service is closed.")
            engine = await self._ensure_engine()
            try:
                result = await _run_blocking(
                    engine.analyse,
                    position,
                    chess.engine.Limit(time=self.analysis_time_limit_seconds),
                    multipv=count,
                )
            except TimeoutError as error:
                raise EngineTimeoutError(
                    "Stockfish timed out while analysing the position."
                ) from error
            except chess.engine.EngineTerminatedError as error:
                self._engine = None
                raise EngineProcessError(
                    "Stockfish exited while analysing the position."
                ) from error
            except chess.engine.EngineError as error:
                raise EngineProcessError(
                    f"Stockfish could not analyse the position: {error}"
                ) from error
            except (OSError, RuntimeError) as error:
                raise EngineProcessError(
                    f"Stockfish process failed during analysis: {error}"
                ) from error
            return _validated_analysis(position, result, count)

    async def close(self) -> None:
        async with self._lock:
            if self._closed:
                return
            self._closed = True
            engine, self._engine = self._engine, None
            if engine is None:
                return
            try:
                await _run_blocking(engine.quit)
            except chess.engine.EngineTerminatedError:
                return
            except (chess.engine.EngineError, OSError, RuntimeError) as error:
                raise EngineProcessError(
                    f"Stockfish could not be closed cleanly: {error}"
                ) from error

    async def _ensure_engine(self) -> chess.engine.SimpleEngine:
        if self._engine is not None:
            return self._engine
        try:
            engine = await _run_blocking(
                self._engine_factory,
                str(self.executable_path),
            )
        except TimeoutError as error:
            raise EngineTimeoutError(
                f"Stockfish timed out during startup: {self.executable_path}"
            ) from error
        except chess.engine.EngineTerminatedError as error:
            raise EngineStartupError(
                f"Stockfish exited during startup: {self.executable_path}"
            ) from error
        except (chess.engine.EngineError, OSError, RuntimeError) as error:
            raise EngineStartupError(
                f"Could not start Stockfish at {self.executable_path}: {error}"
            ) from error
        self._engine = engine
        return engine


def _start_uci_engine(path: str) -> chess.engine.SimpleEngine:
    return chess.engine.SimpleEngine.popen_uci(path)


async def _run_blocking(
    function: Callable[..., ResultT],
    *args: object,
    **kwargs: object,
) -> ResultT:
    """Keep the serialized lock held until a cancelled thread call really ends."""

    task = asyncio.create_task(asyncio.to_thread(function, *args, **kwargs))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        try:
            await task
        except Exception:
            pass
        raise


def _validated_analysis(
    board: chess.Board,
    result: chess.engine.InfoDict | list[chess.engine.InfoDict],
    count: int,
) -> tuple[AnalysedMove, ...]:
    rows = result if isinstance(result, list) else [result]
    suggestions: list[AnalysedMove] = []
    seen: set[str] = set()
    for index, info in enumerate(rows[:count], start=1):
        pv = info.get("pv")
        score = info.get("score")
        if not pv or not isinstance(score, chess.engine.PovScore):
            raise EngineResultError(
                f"Stockfish analysis row {index} has no score or principal variation."
            )
        pv_board = board.copy(stack=False)
        for ply, pv_move in enumerate(pv, start=1):
            if (
                not isinstance(pv_move, chess.Move)
                or pv_move not in pv_board.legal_moves
            ):
                raise EngineResultError(
                    f"Stockfish analysis row {index} has an illegal principal-"
                    f"variation move at ply {ply}."
                )
            pv_board.push(pv_move)
        move = pv[0]
        if move.uci() in seen:
            raise EngineResultError(
                f"Stockfish analysis duplicated root move {move.uci()!r}."
            )
        seen.add(move.uci())
        white_score = score.pov(chess.WHITE)
        evaluation_cp = white_score.score()
        mate_in = white_score.mate()
        if evaluation_cp is None and mate_in is None:
            raise EngineResultError(
                f"Stockfish analysis row {index} returned an unsupported score."
            )
        suggestions.append(
            AnalysedMove(
                uci=move.uci(),
                san=board.san(move),
                evaluation_cp=evaluation_cp,
                principal_variation=tuple(item.uci() for item in pv),
                mate_in=mate_in,
            )
        )
    if not suggestions:
        raise EngineResultError("Stockfish returned no analysis rows.")
    return tuple(suggestions)
