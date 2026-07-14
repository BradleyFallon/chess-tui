"""End-of-demo frontier presentation."""

from __future__ import annotations

from textual.widgets import Static

from ..sessions.models import FrontierState


class FrontierPanel(Static):
    def show_frontier(
        self, frontier: FrontierState, *, demo_result: str | None = None
    ) -> None:
        line = " ".join(frontier.line_san)
        text = (
            "FLOW FRONTIER\n\n"
            f"{line}\n\n"
            "[A] Add continuation\n"
            "[S] Restart demo\n"
            "[F] Exit"
        )
        if demo_result:
            text += f"\n\nDEMO ONLY — NOT SAVED\n{demo_result}"
        self.update(text)
        self.display = True

    def clear_frontier(self) -> None:
        self.update("")
        self.display = False
