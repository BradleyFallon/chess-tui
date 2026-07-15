"""Compact White-normalized engine advantage bar."""

from __future__ import annotations

import chess
from rich.text import Text
from textual.widgets import Static

from ..renderers.colors import BLACK_HIGHLIGHT, LABEL_COLOR, WHITE_FILL


class AdvantageBar(Static):
    """Render the current engine score as a Black/White balance bar."""

    def __init__(self) -> None:
        super().__init__(id="advantage-bar")
        self.evaluation_cp: int | None = None
        self.mate_in: int | None = None
        self.outcome: chess.Outcome | None = None
        self.loading = False
        self.error: str | None = None

    @property
    def white_share(self) -> float:
        if self.outcome is not None:
            if self.outcome.winner is chess.WHITE:
                return 1.0
            if self.outcome.winner is chess.BLACK:
                return 0.0
            return 0.5
        if self.mate_in is not None:
            return 1.0 if self.mate_in >= 0 else 0.0
        if self.evaluation_cp is None:
            return 0.5
        share = 0.5 + (self.evaluation_cp / 2000)
        return max(0.05, min(0.95, share))

    def mark_loading(self) -> None:
        self.loading = True
        self.error = None
        self.refresh()

    def set_evaluation(
        self,
        *,
        evaluation_cp: int | None,
        mate_in: int | None,
    ) -> None:
        if (evaluation_cp is None) == (mate_in is None):
            raise ValueError("Engine evaluation must contain centipawns or mate.")
        self.evaluation_cp = evaluation_cp
        self.mate_in = mate_in
        self.outcome = None
        self.loading = False
        self.error = None
        self.refresh()

    def set_outcome(self, outcome: chess.Outcome) -> None:
        self.evaluation_cp = None
        self.mate_in = None
        self.outcome = outcome
        self.loading = False
        self.error = None
        self.refresh()

    def set_error(self, error: str) -> None:
        self.loading = False
        self.error = error
        self.refresh()

    def render(self) -> Text:
        score = self._score_label()
        available_width = self.size.width or 34
        bar_width = max(6, available_width - len(score) - 7)
        white_cells = round(bar_width * self.white_share)
        black_cells = bar_width - white_cells

        output = Text("B ", style=LABEL_COLOR)
        output.append("█" * black_cells, style=BLACK_HIGHLIGHT)
        output.append("█" * white_cells, style=WHITE_FILL)
        output.append(" W · ", style=LABEL_COLOR)
        output.append(score, style=f"bold {LABEL_COLOR}")
        return output

    def _score_label(self) -> str:
        if self.loading:
            return "ENGINE …"
        if self.error is not None:
            return "ENGINE —"
        if self.outcome is not None:
            if self.outcome.winner is chess.WHITE:
                return "WHITE WINS"
            if self.outcome.winner is chess.BLACK:
                return "BLACK WINS"
            return "DRAW"
        if self.mate_in is not None:
            side = "WHITE" if self.mate_in >= 0 else "BLACK"
            return f"{side} M{abs(self.mate_in)}"
        if self.evaluation_cp is None or self.evaluation_cp == 0:
            return "EQUAL 0.00"
        side = "WHITE" if self.evaluation_cp > 0 else "BLACK"
        return f"{side} +{abs(self.evaluation_cp) / 100:.2f}"
