"""Compact keyboard-driven selector for common opening replies."""

from __future__ import annotations

from rich.text import Text
from textual.events import Key
from textual.message import Message
from textual.widgets import Static

from ..opening import OpeningMove

MOVE_KEYS = ("a", "s", "d", "f")


class OpeningMovePanel(Static):
    can_focus = True

    class MoveSubmitted(Message):
        def __init__(self, move: OpeningMove) -> None:
            self.move = move
            super().__init__()

    class ManualRequested(Message):
        pass

    class TextRequested(Message):
        pass

    def __init__(self) -> None:
        super().__init__(id="opening-moves")
        self.moves: tuple[OpeningMove, ...] = ()
        self.highlighted_index: int | None = None
        self.context = ""
        self.submission_enabled = False

    @property
    def highlighted_move(self) -> OpeningMove | None:
        index = self.highlighted_index
        if index is None:
            return None
        return self.moves[index]

    def set_moves(self, moves: tuple[OpeningMove, ...], *, context: str) -> None:
        if len(moves) > len(MOVE_KEYS):
            raise ValueError("OpeningMovePanel supports at most four moves.")
        self.moves = moves
        self.context = context
        self.highlighted_index = 0 if moves else None
        self.submission_enabled = bool(moves)
        self.refresh()

    def clear(self) -> None:
        self.moves = ()
        self.context = ""
        self.highlighted_index = None
        self.submission_enabled = False
        self.refresh()

    def highlight(self, index: int) -> None:
        if 0 <= index < len(self.moves):
            self.highlighted_index = index
            self.refresh()

    def move_highlight(self, offset: int) -> None:
        if not self.moves:
            return
        current = self.highlighted_index if self.highlighted_index is not None else 0
        self.highlight((current + offset) % len(self.moves))

    def submit_highlighted(self) -> None:
        move = self.highlighted_move
        if not self.submission_enabled or move is None:
            return
        self.submission_enabled = False
        self.post_message(self.MoveSubmitted(move))

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
        for index, move in enumerate(self.moves):
            marker = ">" if index == self.highlighted_index else " "
            key = MOVE_KEYS[index].upper()
            output.append(
                f"\n{marker} [{key}] {move.san:<5} "
                f"{move.frequency:>4.0%} · {move.games:,} games",
                style="bold" if index == self.highlighted_index else None,
            )
        return output
