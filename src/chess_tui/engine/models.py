"""Models shared by chess-engine implementations and consumers."""

from dataclasses import dataclass
from enum import Enum


@dataclass(frozen=True, slots=True)
class EngineProfile:
    id: str
    label: str
    time_limit_seconds: float


@dataclass(frozen=True, slots=True)
class AnalysedMove:
    uci: str
    san: str
    evaluation_cp: int | None
    principal_variation: tuple[str, ...]
    mate_in: int | None = None


class MoveQuality(str, Enum):
    BEST = "best"
    GOOD = "good"
    INACCURACY = "inaccuracy"
    MISTAKE = "mistake"
    BLUNDER = "blunder"


@dataclass(frozen=True, slots=True)
class MoveAssessment:
    played_uci: str
    best_uci: str
    evaluation_before_cp: int | None
    evaluation_after_cp: int | None
    loss_cp: int | None
    quality: MoveQuality
    mate_before: int | None = None
    mate_after: int | None = None


@dataclass(frozen=True, slots=True)
class QualityThresholds:
    best_max_cp: int = 20
    good_max_cp: int = 60
    inaccuracy_max_cp: int = 120
    mistake_max_cp: int = 250

    def __post_init__(self) -> None:
        values = (
            self.best_max_cp,
            self.good_max_cp,
            self.inaccuracy_max_cp,
            self.mistake_max_cp,
        )
        if values[0] < 0 or tuple(sorted(values)) != values:
            raise ValueError("Move-quality thresholds must be nonnegative and ordered.")


ENGINE_PROTOTYPE_PROFILE = EngineProfile(
    id="engine-prototype",
    label="ENGINE PROTOTYPE",
    time_limit_seconds=0.1,
)

DEFAULT_QUALITY_THRESHOLDS = QualityThresholds()
