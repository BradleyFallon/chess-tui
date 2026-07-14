"""Local-only quiz picker and mock continuation modals."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.events import Key
from textual.screen import ModalScreen
from textual.widgets import Static

from ..sessions.models import FlowSummary


class FlowPickerModal(ModalScreen[str | None]):
    CSS = """
    FlowPickerModal { align: center middle; background: #0008; }
    FlowPickerModal > #picker { width: 46; height: auto; padding: 1 2; background: #172019; border: solid #9eaf74; }
    FlowPickerModal .selected { color: #fffdf5; background: #405e42; }
    """

    def __init__(self, flows: tuple[FlowSummary, ...], current_id: str) -> None:
        super().__init__()
        self.flows = flows
        self.index = next(
            (index for index, flow in enumerate(flows) if flow.id == current_id), 0
        )
        self.options = tuple(Static("") for _ in flows)

    def compose(self) -> ComposeResult:
        with Vertical(id="picker"):
            yield Static("SELECT FLOW")
            yield from self.options
            yield Static("\nUP/DOWN SELECT · ENTER OPEN · ESC CANCEL")

    def on_mount(self) -> None:
        self._refresh_options()

    def on_key(self, event: Key) -> None:
        if event.key == "up":
            self.index = (self.index - 1) % len(self.flows)
        elif event.key == "down":
            self.index = (self.index + 1) % len(self.flows)
        elif event.key == "enter":
            event.stop()
            self.dismiss(self.flows[self.index].id)
            return
        elif event.key == "escape":
            event.stop()
            self.dismiss(None)
            return
        else:
            return
        event.stop()
        self._refresh_options()

    def _refresh_options(self) -> None:
        for index, (flow, option) in enumerate(
            zip(self.flows, self.options, strict=True)
        ):
            marker = "▶" if index == self.index else " "
            option.update(f"{marker} {flow.name:<22} {flow.side.title()}")
            option.set_class(index == self.index, "selected")
