"""End-of-demo frontier presentation."""

from __future__ import annotations

from textual.widgets import Static

from ..sessions.models import ContinuationDraft, FrontierKind, FrontierState, RuleType


class FrontierPanel(Static):
    def show_frontier(
        self,
        frontier: FrontierState,
        *,
        rules: tuple[ContinuationDraft, ...] = (),
    ) -> None:
        line = " ".join(frontier.line_san)
        default = next(
            (rule for rule in rules if rule.rule_type is RuleType.DEFAULT), None
        )
        if default is not None:
            action = "[A] Add branch exception\n[D] Edit default response"
        elif frontier.kind is FrontierKind.NEEDS_FIRST_RULE:
            action = "[A] Set default response"
        else:
            action = "[A] Add branch exception"
        text = (
            "FLOW FRONTIER\n\n"
            f"{line}\n\n"
            f"{action}\n"
            "[S] Restart demo\n"
            "[F] Exit"
        )
        if rules:
            text += "\n\nDEMO ONLY — NOT SAVED"
            if default is not None:
                text += f"\nDEFAULT: any reply -> {default.response_move_san}"
                if default.note:
                    text += f" ({default.note})"
            exceptions = tuple(
                rule for rule in rules if rule.rule_type is RuleType.EXACT
            )
            if exceptions:
                text += "\nEXCEPTIONS:"
                for exception in exceptions:
                    text += (
                        f"\n  {exception.opponent_move_san}"
                        f" -> {exception.response_move_san}"
                    )
                    if exception.note:
                        text += f" ({exception.note})"
        self.update(text)
        self.display = True

    def clear_frontier(self) -> None:
        self.update("")
        self.display = False
