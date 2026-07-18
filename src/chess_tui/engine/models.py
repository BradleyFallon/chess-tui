"""Models shared by chess-engine implementations and consumers."""

from dataclasses import dataclass
from enum import Enum


@dataclass(frozen=True, slots=True)
class EngineProfile:
    id: str
    label: str
    time_limit_seconds: float | None = None
    depth: int | None = None
    cost_label: str = "Local compute"
    cost_description: str = "No API fee; uses local CPU while the engine searches."

    def __post_init__(self) -> None:
        limits = (self.time_limit_seconds is not None, self.depth is not None)
        if not any(limits):
            raise ValueError("An engine profile must set at least one search limit.")
        if self.time_limit_seconds is not None and self.time_limit_seconds <= 0:
            raise ValueError("Engine profile time limit must be greater than zero.")
        if self.depth is not None and self.depth <= 0:
            raise ValueError("Engine profile depth must be greater than zero.")


@dataclass(frozen=True, slots=True)
class AnalysedMove:
    uci: str
    san: str
    evaluation_cp: int | None
    principal_variation: tuple[str, ...]
    mate_in: int | None = None
    engine_name: str | None = None
    profile_id: str | None = None
    requested_depth: int | None = None
    actual_depth: int | None = None
    selective_depth: int | None = None
    nodes: int | None = None
    nps: int | None = None
    time_ms: int | None = None


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

ANALYSIS_PROFILES = (
    EngineProfile(
        id="blunder-check",
        label="Blunder check",
        depth=10,
        cost_label="Lowest compute",
        cost_description="Depth 10 catches obvious tactical errors quickly.",
    ),
    EngineProfile(
        id="quick",
        label="Quick",
        depth=15,
        cost_label="Low compute",
        cost_description="Depth 15 is a fast interactive evaluation.",
    ),
    EngineProfile(
        id="analysis",
        label="Analysis",
        depth=20,
        cost_label="Moderate compute",
        cost_description="Depth 20 provides stronger routine analysis.",
    ),
    EngineProfile(
        id="deep",
        label="Deep",
        depth=26,
        cost_label="Highest compute",
        cost_description="Depth 26 is the slowest, strongest interactive search.",
    ),
)
DEFAULT_ANALYSIS_PROFILE = ANALYSIS_PROFILES[2]

DEFAULT_QUALITY_THRESHOLDS = QualityThresholds()
