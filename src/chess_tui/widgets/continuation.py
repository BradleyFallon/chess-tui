"""Inline continuation-rule editor that leaves the board visible."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.events import Key
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Button, Input, Static

from ..sessions.models import (
    ContinuationDraft,
    FrontierKind,
    FrontierState,
    RuleType,
)


class ContinuationEditor(Widget):
    class Submitted(Message):
        def __init__(self, draft: ContinuationDraft) -> None:
            self.draft = draft
            super().__init__()

    class Cancelled(Message):
        pass

    def __init__(self) -> None:
        super().__init__()
        self.frontier: FrontierState | None = None
        self.title = Static("", id="editor-title")
        self.help = Static("", id="editor-help")
        self.opponent = Input(
            placeholder="Opponent SAN move for this exception",
            id="opponent",
        )
        self.response = Input(placeholder="Your SAN response", id="response")
        self.note = Input(placeholder="Optional note", id="note")
        self.display = False

    def compose(self) -> ComposeResult:
        yield self.title
        yield self.help
        yield self.opponent
        yield self.response
        yield self.note
        with Horizontal(id="editor-actions"):
            yield Button("Set rule", id="submit", variant="primary")
            yield Button("Cancel", id="cancel")

    def show_editor(
        self,
        frontier: FrontierState,
        *,
        initial: ContinuationDraft | None = None,
    ) -> None:
        self.frontier = frontier
        is_default = frontier.kind is FrontierKind.NEEDS_FIRST_RULE
        self.title.update(
            "SET DEFAULT RESPONSE" if is_default else "ADD BRANCH EXCEPTION"
        )
        self.help.update(
            "Used after any opponent reply."
            if is_default
            else "Overrides the default after this opponent move."
        )
        self.opponent.display = (
            frontier.kind is FrontierKind.NEEDS_OPPONENT_CONTINUATION
        )
        self.opponent.value = (
            initial.opponent_move_san
            if initial is not None and initial.opponent_move_san is not None
            else ""
        )
        self.response.value = initial.response_move_san if initial is not None else ""
        self.note.value = initial.note or "" if initial is not None else ""
        self.display = True
        (self.opponent if self.opponent.display else self.response).focus()

    def cancel(self) -> None:
        self.display = False
        self.frontier = None
        self.post_message(self.Cancelled())

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel":
            self.cancel()
            return
        self._submit()

    def on_key(self, event: Key) -> None:
        if event.key == "escape":
            event.stop()
            self.cancel()

    def _submit(self) -> None:
        frontier = self.frontier
        if frontier is None:
            return
        response = self.response.value.strip()
        if not response:
            self.response.focus()
            return
        opponent = (
            self.opponent.value.strip() or None
            if frontier.kind is FrontierKind.NEEDS_OPPONENT_CONTINUATION
            else frontier.opponent_move_san
        )
        if frontier.kind is not FrontierKind.NEEDS_FIRST_RULE and opponent is None:
            self.opponent.focus()
            return
        self.post_message(
            self.Submitted(
                ContinuationDraft(
                    response_move_san=response,
                    rule_type=(
                        RuleType.DEFAULT
                        if frontier.kind is FrontierKind.NEEDS_FIRST_RULE
                        else RuleType.EXACT
                    ),
                    opponent_move_san=opponent,
                    note=self.note.value.strip() or None,
                )
            )
        )
        self.display = False
        self.frontier = None
