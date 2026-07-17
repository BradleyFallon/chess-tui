"""Compact keyboard-driven selector for opponent move suggestions."""

from __future__ import annotations

from rich.text import Text
from textual.events import Key
from textual.message import Message
from textual.widgets import Static

from ..opening import MoveSuggestion

MOVE_KEYS = ("a", "s", "d", "f")


class MoveSuggestionPanel(Static):
    can_focus = True

    class SuggestionSubmitted(Message):
        def __init__(self, suggestion: MoveSuggestion) -> None:
            self.suggestion = suggestion
            super().__init__()

    class ManualRequested(Message):
        pass

    class TextRequested(Message):
        pass

    def __init__(self) -> None:
        super().__init__(id="move-suggestions")
        self.suggestions: tuple[MoveSuggestion, ...] = ()
        self.highlighted_index: int | None = None
        self.context = ""
        self.explored_sans: frozenset[str] = frozenset()
        self.submission_enabled = False

    @property
    def highlighted_suggestion(self) -> MoveSuggestion | None:
        index = self.highlighted_index
        if index is None:
            return None
        return self.suggestions[index]

    def set_suggestions(
        self,
        suggestions: tuple[MoveSuggestion, ...],
        *,
        context: str,
        explored_sans: frozenset[str] = frozenset(),
    ) -> None:
        if len(suggestions) > len(MOVE_KEYS):
            raise ValueError("MoveSuggestionPanel supports at most four moves.")
        self.suggestions = suggestions
        self.context = context
        self.explored_sans = explored_sans
        self.highlighted_index = 0 if suggestions else None
        self.submission_enabled = bool(suggestions)
        self.refresh()

    def clear(self) -> None:
        self.suggestions = ()
        self.context = ""
        self.explored_sans = frozenset()
        self.highlighted_index = None
        self.submission_enabled = False
        self.refresh()

    def highlight(self, index: int) -> None:
        if 0 <= index < len(self.suggestions):
            self.highlighted_index = index
            self.refresh()

    def move_highlight(self, offset: int) -> None:
        if not self.suggestions:
            return
        current = self.highlighted_index if self.highlighted_index is not None else 0
        self.highlight((current + offset) % len(self.suggestions))

    def submit_highlighted(self) -> None:
        suggestion = self.highlighted_suggestion
        if not self.submission_enabled or suggestion is None:
            return
        self.submission_enabled = False
        self.post_message(self.SuggestionSubmitted(suggestion))

    def on_key(self, event: Key) -> None:
        key = event.key.lower()
        if key in MOVE_KEYS:
            self.highlight(MOVE_KEYS.index(key))
        elif key == "up":
            self.move_highlight(-1)
        elif key == "down":
            self.move_highlight(1)
        elif key == "enter":
            self.submit_highlighted()
        elif key == "m":
            self.post_message(self.ManualRequested())
        elif key == "i":
            self.post_message(self.TextRequested())
        else:
            return
        event.stop()

    def render(self) -> Text:
        output = Text("BLACK RESPONSE", style="bold")
        if self.context:
            output.append(f"\n\n{self.context}\n")
        for index, suggestion in enumerate(self.suggestions):
            marker = ">" if index == self.highlighted_index else " "
            key = MOVE_KEYS[index].upper()
            explored = " · explored" if suggestion.san in self.explored_sans else ""
            output.append(
                f"\n{marker} [{key}] {suggestion.san:<5} "
                f"{_suggestion_details(suggestion)}{explored}",
                style="bold" if index == self.highlighted_index else None,
            )
        return output


def _suggestion_details(suggestion: MoveSuggestion) -> str:
    kind = suggestion.kind.value.upper()
    label = suggestion.label.strip()
    return f"{kind} · {label}" if label and label.upper() != kind else kind
