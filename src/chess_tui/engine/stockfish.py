"""Persistent Stockfish service implemented with python-chess UCI support."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Callable

import chess
import chess.engine

from .errors import (
    EngineConfigurationError,
    EngineProcessError,
    EngineResultError,
    EngineStartupError,
    EngineTimeoutError,
)
from .models import EngineProfile

EngineFactory = Callable[[str], chess.engine.SimpleEngine]


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
    ) -> None:
        self.executable_path = validate_engine_path(executable_path)
        self._engine_factory = engine_factory or _start_uci_engine
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
                result = await asyncio.to_thread(
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

    async def close(self) -> None:
        async with self._lock:
            if self._closed:
                return
            self._closed = True
            engine, self._engine = self._engine, None
            if engine is None:
                return
            try:
                await asyncio.to_thread(engine.quit)
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
            engine = await asyncio.to_thread(
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
