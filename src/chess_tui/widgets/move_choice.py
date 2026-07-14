"""One focusable quiz move choice."""

from __future__ import annotations

from textual.events import Click, Enter
from textual.message import Message
from textual.widgets import Static

from ..sessions.models import MoveChoice


class MoveChoiceButton(Static):
    can_focus = True

    class Highlighted(Message):
        def __init__(self, index: int) -> None:
            self.index = index
            super().__init__()

    class Submitted(Message):
        def __init__(self, index: int) -> None:
            self.index = index
            super().__init__()

    def __init__(self, index: int, key_label: str) -> None:
        super().__init__("", id=f"choice-{key_label.lower()}")
        self.index = index
        self.key_label = key_label
        self.choice: MoveChoice | None = None
        self.submission_enabled = False

    def set_choice(self, choice: MoveChoice | None) -> None:
        self.choice = choice
        self.display = choice is not None
        self.update(f"[{self.key_label}] {choice.san}" if choice is not None else "")

    def set_selected(self, selected: bool) -> None:
        self.set_class(selected, "selected")

    def on_enter(self, event: Enter) -> None:
        if self.choice is not None:
            self.post_message(self.Highlighted(self.index))

    def on_click(self, event: Click) -> None:
        if self.choice is not None and self.submission_enabled:
            event.stop()
            self.post_message(self.Submitted(self.index))
