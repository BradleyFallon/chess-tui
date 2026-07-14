"""Resolve exact-position exceptions before numbered defaults."""

from __future__ import annotations

import chess

from .errors import FlowValidationError, RuleUnavailableError
from .models import Recommendation, WhiteFlow
from .position import normalized_position_key, replay_san


class WhitePolicy:
    def __init__(self, flow: WhiteFlow) -> None:
        self.flow = flow
        self.defaults_by_step = {rule.step: rule for rule in flow.defaults}
        self.exceptions_by_position = {}
        for exception in flow.exceptions:
            board = replay_san(
                flow.start_fen,
                exception.after_san,
                context=f"Exception {exception.id!r}",
            )
            key = normalized_position_key(board)
            if key in self.exceptions_by_position:
                raise FlowValidationError(
                    f"Multiple exceptions resolve to position {key!r}."
                )
            self.exceptions_by_position[key] = exception

    def recommend(self, board: chess.Board, white_step: int) -> Recommendation | None:
        exception = self.exceptions_by_position.get(normalized_position_key(board))
        if exception is not None:
            recommendation = Recommendation(
                step=white_step,
                move_san=exception.move_san,
                note=exception.note,
                source="exception",
                exception_id=exception.id,
            )
        else:
            default = self.defaults_by_step.get(white_step)
            if default is None:
                return None
            recommendation = Recommendation(
                step=white_step,
                move_san=default.move_san,
                note=default.note,
                source="default",
            )

        try:
            board.parse_san(recommendation.move_san)
        except ValueError as exc:
            label = (
                f"Exception {recommendation.exception_id!r}"
                if recommendation.source == "exception"
                else f"Step {white_step} default"
            )
            raise RuleUnavailableError(
                recommendation,
                "DEFAULT MOVE UNAVAILABLE\n\n"
                f"{label}:\n{recommendation.move_san}\n\n"
                f"{recommendation.move_san} is not legal in this position.\n\n"
                "Play a legal move to create an exception.",
            ) from exc
        return recommendation
