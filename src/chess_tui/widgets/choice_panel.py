"""Single source of truth for quiz choice selection and submission."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.events import Key
from textual.message import Message
from textual.widget import Widget

from ..sessions.models import MoveChoice
from .move_choice import MoveChoiceButton

CHOICE_KEYS = ("A", "S", "D", "F")


class ChoicePanel(Widget):
    can_focus = True

    class ChoiceSubmitted(Message):
        def __init__(self, choice: MoveChoice) -> None:
            self.choice = choice
            super().__init__()

    def __init__(self) -> None:
        super().__init__()
        self.buttons = tuple(
            MoveChoiceButton(index, key) for index, key in enumerate(CHOICE_KEYS)
        )
        self.choices: tuple[MoveChoice, ...] = ()
        self.highlighted_index: int | None = None
        self.submission_enabled = False

    def compose(self) -> ComposeResult:
        yield from self.buttons

    def set_choices(self, choices: tuple[MoveChoice, ...]) -> None:
        if len(choices) > len(self.buttons):
            raise ValueError("ChoicePanel supports at most four choices.")
        self.choices = choices
        for index, button in enumerate(self.buttons):
            button.set_choice(choices[index] if index < len(choices) else None)
        self.set_submission_enabled(True)
        self.highlight(0 if choices else None)

    def clear(self) -> None:
        self.choices = ()
        for button in self.buttons:
            button.set_choice(None)
        self.set_submission_enabled(False)
        self.highlight(None)

    def set_submission_enabled(self, enabled: bool) -> None:
        self.submission_enabled = enabled
        for button in self.buttons:
            button.submission_enabled = enabled

    def highlight(self, index: int | None) -> None:
        if index is not None and not 0 <= index < len(self.choices):
            return
        self.highlighted_index = index
        for button_index, button in enumerate(self.buttons):
            button.set_selected(button_index == index)

    def highlight_key(self, key: str) -> None:
        normalized = key.upper()
        if normalized in CHOICE_KEYS:
            self.highlight(CHOICE_KEYS.index(normalized))

    def move_highlight(self, offset: int) -> None:
        if not self.choices:
            return
        current = self.highlighted_index if self.highlighted_index is not None else 0
        self.highlight((current + offset) % len(self.choices))

    def submit_highlighted(self) -> None:
        index = self.highlighted_index
        if not self.submission_enabled or index is None:
            return
        self._submit(index)

    def _submit(self, index: int) -> None:
        if not self.submission_enabled or not 0 <= index < len(self.choices):
            return
        self.set_submission_enabled(False)
        self.post_message(self.ChoiceSubmitted(self.choices[index]))

    def on_key(self, event: Key) -> None:
        if not self.submission_enabled:
            return
        key = event.key.lower()
        if key in {"a", "s", "d", "f"}:
            self.highlight_key(key)
        elif key == "up":
            self.move_highlight(-1)
        elif key == "down":
            self.move_highlight(1)
        elif key == "enter":
            self.submit_highlighted()
        else:
            return
        event.stop()

    def on_move_choice_button_highlighted(
        self, message: MoveChoiceButton.Highlighted
    ) -> None:
        self.highlight(message.index)

    def on_move_choice_button_submitted(
        self, message: MoveChoiceButton.Submitted
    ) -> None:
        self.highlight(message.index)
        self._submit(message.index)
