"""Quiz feedback presentation."""

from __future__ import annotations

from textual.widgets import Static

from ..sessions.models import QuizFeedback


class FeedbackPanel(Static):
    def show_feedback(self, feedback: QuizFeedback, *, editable: bool = False) -> None:
        self.remove_class("correct", "mismatch")
        self.add_class("correct" if feedback.correct else "mismatch")
        if feedback.correct:
            text = f"CORRECT: {feedback.expected_san}"
        else:
            text = (
                "RULE MISMATCH\n\n"
                f"Selected: {feedback.selected_san}\n"
                f"Expected: {feedback.expected_san}"
            )
        if feedback.explanation:
            text += f"\n\n{feedback.explanation}"
        if editable and not feedback.correct:
            text += "\n\n[E] Make selected move correct"
        self.update(text)
        self.display = True

    def clear_feedback(self) -> None:
        self.update("")
        self.display = False
