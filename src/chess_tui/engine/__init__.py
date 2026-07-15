"""Reusable asynchronous chess-engine services."""

from .errors import (
    EngineConfigurationError,
    EngineError,
    EngineProcessError,
    EngineResultError,
    EngineStartupError,
    EngineTimeoutError,
)
from .assessment import assess_white_move, quality_for_loss
from .fixture import FixtureEngineService
from .models import (
    DEFAULT_QUALITY_THRESHOLDS,
    ENGINE_PROTOTYPE_PROFILE,
    AnalysedMove,
    EngineProfile,
    MoveAssessment,
    MoveQuality,
    QualityThresholds,
)
from .service import ChessEngineService
from .stockfish import StockfishEngineService, validate_engine_path

__all__ = [
    "ChessEngineService",
    "AnalysedMove",
    "DEFAULT_QUALITY_THRESHOLDS",
    "ENGINE_PROTOTYPE_PROFILE",
    "EngineConfigurationError",
    "EngineError",
    "EngineProcessError",
    "EngineProfile",
    "EngineResultError",
    "EngineStartupError",
    "EngineTimeoutError",
    "FixtureEngineService",
    "MoveAssessment",
    "MoveQuality",
    "QualityThresholds",
    "StockfishEngineService",
    "validate_engine_path",
    "assess_white_move",
    "quality_for_loss",
]
