"""Top-level application modes."""

from __future__ import annotations

from enum import Enum


class AppMode(str, Enum):
    LOCAL_GAME = "local-game"
    QUIZ_DEMO = "quiz-demo"
