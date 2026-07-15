"""Models shared by chess-engine implementations and consumers."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EngineProfile:
    id: str
    label: str
    time_limit_seconds: float


ENGINE_PROTOTYPE_PROFILE = EngineProfile(
    id="engine-prototype",
    label="ENGINE PROTOTYPE",
    time_limit_seconds=0.1,
)
