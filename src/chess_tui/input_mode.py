"""Shared navigation and text-entry mode state."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TypeAlias

from textual.widgets import Input, TextArea


class InputMode(str, Enum):
    NAVIGATION = "navigation"
    TEXT = "text"


TextField: TypeAlias = Input | TextArea


@dataclass(slots=True)
class InputModeController:
    mode: InputMode = InputMode.NAVIGATION
    active_field: TextField | None = None

    @property
    def handles_global_shortcuts(self) -> bool:
        return self.mode is InputMode.NAVIGATION

    def enter_text(self, field: TextField) -> None:
        self.mode = InputMode.TEXT
        self.active_field = field
        field.focus()

    def leave_text(self, *, blur: bool = True) -> TextField | None:
        field = self.active_field
        self.mode = InputMode.NAVIGATION
        self.active_field = None
        if blur and field is not None:
            field.blur()
        return field

    def field_blurred(self, field: TextField) -> bool:
        if field is not self.active_field:
            return False
        self.leave_text(blur=False)
        return True
