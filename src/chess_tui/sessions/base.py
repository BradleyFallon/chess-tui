"""Narrow interface implemented by quiz session providers."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .models import QuizSessionState


class QuizSession(Protocol):
    async def start(self) -> QuizSessionState: ...

    async def answer(self, question_id: str, choice_id: str) -> QuizSessionState: ...

    async def continue_session(self) -> QuizSessionState: ...

    async def restart(self) -> QuizSessionState: ...

    async def close(self) -> None: ...


@runtime_checkable
class EditableQuizSession(Protocol):
    async def update_correct_answer(
        self, question_id: str, choice_id: str
    ) -> QuizSessionState: ...
