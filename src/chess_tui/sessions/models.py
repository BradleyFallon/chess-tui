"""Provider-independent quiz presentation models."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


@dataclass(frozen=True, slots=True)
class MoveChoice:
    id: str
    san: str
    uci: str

    def __post_init__(self) -> None:
        if not self.id or not self.san or not self.uci:
            raise ValueError("Move choices require non-empty id, SAN, and UCI values.")


@dataclass(frozen=True, slots=True)
class QuizQuestion:
    id: str
    prompt: str
    choices: tuple[MoveChoice, ...]

    def __post_init__(self) -> None:
        if not self.id or not self.prompt:
            raise ValueError("Quiz questions require an id and prompt.")
        if not self.choices:
            raise ValueError("Quiz questions require at least one choice.")
        ids = tuple(choice.id for choice in self.choices)
        if len(set(ids)) != len(ids):
            raise ValueError("Quiz question choice ids must be unique.")


@dataclass(frozen=True, slots=True)
class QuizFeedback:
    correct: bool
    selected_san: str
    expected_san: str
    explanation: str | None


class QuizPhase(str, Enum):
    QUESTION = "question"
    CORRECT_FEEDBACK = "correct-feedback"
    MISMATCH_FEEDBACK = "mismatch-feedback"
    FRONTIER = "frontier"
    COMPLETE = "complete"


@dataclass(frozen=True, slots=True)
class FrontierState:
    line_san: tuple[str, ...]
    message: str = "The packaged demo line ends here."


@dataclass(frozen=True, slots=True)
class QuizSessionState:
    phase: QuizPhase
    fen: str
    line_san: tuple[str, ...]
    question: QuizQuestion | None = None
    feedback: QuizFeedback | None = None
    frontier: FrontierState | None = None

    def __post_init__(self) -> None:
        if self.phase is QuizPhase.QUESTION and self.question is None:
            raise ValueError("Question phase requires a question.")
        if (
            self.phase
            in {
                QuizPhase.CORRECT_FEEDBACK,
                QuizPhase.MISMATCH_FEEDBACK,
            }
            and self.feedback is None
        ):
            raise ValueError("Feedback phase requires feedback.")
        if self.phase is QuizPhase.FRONTIER and self.frontier is None:
            raise ValueError("Frontier phase requires frontier state.")
