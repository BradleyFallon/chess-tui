"""Interactive run coordinator for testing and editing a White flow."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path
from typing import Callable

import chess

from .author import AuthorBoardController, ConfirmedAuthorMove, WhiteFlowAuthor
from .errors import FlowError, FlowValidationError, RuleUnavailableError
from .models import Recommendation


class AttemptResult(str, Enum):
    CORRECT = "correct"
    MISMATCH_DEFAULT = "mismatch-default"
    MISMATCH_EXCEPTION = "mismatch-exception"
    FRONTIER = "frontier"
    RULE_UNAVAILABLE = "rule-unavailable"


@dataclass(frozen=True, slots=True)
class WhiteTurn:
    white_step: int
    recommendation: Recommendation | None
    unavailable_reason: str | None = None


@dataclass(frozen=True, slots=True)
class WhiteMoveAttempt:
    board_before: chess.Board
    history_before: tuple[str, ...]
    white_step: int
    selected_move: ConfirmedAuthorMove
    recommendation: Recommendation | None
    result: AttemptResult


class FlowWorkspace:
    """Coordinate one test/edit run while WhiteFlowAuthor owns persistence."""

    def __init__(self, flow_path: Path) -> None:
        self.author = WhiteFlowAuthor(flow_path)
        self.controller = AuthorBoardController(chess.Board(self.author.flow.start_fen))
        self.history: list[str] = []
        self.white_turn: WhiteTurn | None = None
        self.attempt: WhiteMoveAttempt | None = None

    @property
    def board(self) -> chess.Board:
        return self.controller.board

    @property
    def outcome(self) -> chess.Outcome | None:
        return self.board.outcome(claim_draw=False)

    @property
    def can_go_back(self) -> bool:
        if self.attempt is not None:
            return True
        if self.board.turn is chess.BLACK:
            return bool(self.history)
        return len(self.history) >= 2

    @property
    def can_restart(self) -> bool:
        return bool(self.history) or self.attempt is not None

    def restart(self) -> WhiteTurn:
        self.restart_position()
        return self.begin_white_turn()

    def restart_position(self) -> None:
        self.controller.reset(chess.Board(self.author.flow.start_fen))
        self.history.clear()
        self.attempt = None
        self.white_turn = None

    def go_back_to_previous_decision(self) -> WhiteTurn:
        """Restore the preceding White decision without changing persisted policy."""

        if not self.can_go_back:
            raise FlowValidationError("There is no earlier White decision.")
        if self.attempt is not None:
            retained = self.attempt.history_before
        elif self.board.turn is chess.BLACK:
            retained = tuple(self.history[:-1])
        else:
            retained = tuple(self.history[:-2])
        self._restore_history(retained)
        return self.begin_white_turn()

    def reload(self) -> WhiteTurn | None:
        self.author.reload()
        self.attempt = None
        return (
            self.begin_white_turn()
            if self.board.turn is chess.WHITE and self.outcome is None
            else None
        )

    def begin_white_turn(self) -> WhiteTurn:
        if self.outcome is not None:
            raise FlowValidationError("Cannot begin a White turn after game over.")
        if self.board.turn is not chess.WHITE:
            raise FlowValidationError("Cannot begin a White turn with Black to move.")
        step = (len(self.history) // 2) + 1
        try:
            recommendation = self.author.recommend(self.board, step)
            unavailable_reason = None
        except RuleUnavailableError as error:
            recommendation = error.recommendation
            unavailable_reason = str(error)
        self.white_turn = WhiteTurn(step, recommendation, unavailable_reason)
        self.attempt = None
        return self.white_turn

    def submit_pending_white_move(self) -> WhiteMoveAttempt | None:
        return self._submit_white(self.controller.confirm_move)

    def submit_white_san(self, san: str) -> WhiteMoveAttempt:
        attempt = self._submit_white(lambda: self.controller.confirm_san(san))
        assert attempt is not None
        return attempt

    def submit_white_uci(self, uci: str) -> WhiteMoveAttempt:
        attempt = self._submit_white(lambda: self.controller.confirm_uci(uci))
        assert attempt is not None
        return attempt

    def retry_white_move(self) -> WhiteTurn:
        attempt = self._require_attempt()
        self._restore(attempt)
        return self.begin_white_turn()

    def keep_saved_rule(self) -> ConfirmedAuthorMove:
        attempt = self._require_attempt()
        recommendation = attempt.recommendation
        if recommendation is None:
            raise FlowValidationError("There is no saved rule to keep.")
        self._restore(attempt)
        confirmed = self.controller.confirm_san(recommendation.move_san)
        self.history.append(confirmed.san)
        self.attempt = None
        self.white_turn = None
        return confirmed

    def complete_correct_move(self) -> None:
        attempt = self._require_attempt()
        if attempt.result is not AttemptResult.CORRECT:
            raise FlowValidationError("The current White attempt is not correct.")
        self.attempt = None
        self.white_turn = None

    def save_selected_default(self, note: str | None) -> None:
        attempt = self._require_attempt()
        self.author.replace_default(
            attempt.board_before,
            attempt.white_step,
            attempt.selected_move.san,
            note,
        )
        self.attempt = None
        self.white_turn = None

    def save_selected_exception(self, note: str | None) -> None:
        attempt = self._require_attempt()
        self.author.add_exception(
            attempt.board_before,
            attempt.white_step,
            attempt.history_before,
            attempt.selected_move.san,
            note,
        )
        self.attempt = None
        self.white_turn = None

    def edit_saved_note(self, note: str | None) -> WhiteMoveAttempt:
        attempt = self._require_attempt()
        recommendation = attempt.recommendation
        if recommendation is None:
            raise FlowValidationError("There is no saved rule note to edit.")
        if recommendation.source == "default":
            self.author.replace_default(
                attempt.board_before,
                attempt.white_step,
                recommendation.move_san,
                note,
            )
        else:
            self.author.add_exception(
                attempt.board_before,
                attempt.white_step,
                attempt.history_before,
                recommendation.move_san,
                note,
            )
        refreshed = self.author.recommend(attempt.board_before, attempt.white_step)
        assert refreshed is not None
        self.attempt = replace(attempt, recommendation=refreshed)
        return self.attempt

    def remove_exception_and_keep_default(self) -> ConfirmedAuthorMove:
        attempt = self._require_attempt()
        recommendation = attempt.recommendation
        if recommendation is None or recommendation.source != "exception":
            raise FlowValidationError("The current rule is not an exception.")
        assert recommendation.exception_id is not None
        default = next(
            (
                rule
                for rule in self.author.flow.defaults
                if rule.step == attempt.white_step
            ),
            None,
        )
        if default is None:
            raise FlowValidationError("No numbered default exists for this White step.")
        try:
            attempt.board_before.parse_san(default.move_san)
        except ValueError as error:
            raise FlowValidationError(
                "The numbered default is not legal in this position."
            ) from error

        self.author.remove_exception(recommendation.exception_id)
        self._restore(attempt)
        confirmed = self.controller.confirm_san(default.move_san)
        self.history.append(confirmed.san)
        self.attempt = None
        self.white_turn = None
        return confirmed

    def submit_pending_black_move(self) -> ConfirmedAuthorMove | None:
        return self._submit_black(self.controller.confirm_move)

    def submit_black_san(self, san: str) -> ConfirmedAuthorMove:
        confirmed = self._submit_black(lambda: self.controller.confirm_san(san))
        assert confirmed is not None
        return confirmed

    def submit_black_uci(self, uci: str) -> ConfirmedAuthorMove:
        confirmed = self._submit_black(lambda: self.controller.confirm_uci(uci))
        assert confirmed is not None
        return confirmed

    def _submit_white(
        self,
        commit: Callable[[], ConfirmedAuthorMove | None],
    ) -> WhiteMoveAttempt | None:
        turn = self.white_turn or self.begin_white_turn()
        board_before = self.board.copy(stack=False)
        history_before = tuple(self.history)
        confirmed = commit()
        if confirmed is None:
            return None
        if confirmed.color is not chess.WHITE:
            raise FlowValidationError("Expected a White move.")
        self.history.append(confirmed.san)
        result = _attempt_result(turn, board_before, confirmed)
        self.attempt = WhiteMoveAttempt(
            board_before,
            history_before,
            turn.white_step,
            confirmed,
            turn.recommendation,
            result,
        )
        return self.attempt

    def _submit_black(
        self,
        commit: Callable[[], ConfirmedAuthorMove | None],
    ) -> ConfirmedAuthorMove | None:
        board_before = self.board.copy(stack=False)
        history_before = tuple(self.history)
        confirmed = commit()
        if confirmed is None:
            return None
        if confirmed.color is not chess.BLACK:
            raise FlowValidationError("Expected a Black move.")
        try:
            self.author.record_opponent_reply(
                board_before,
                history_before,
                confirmed.san,
            )
        except FlowError:
            self.controller.reset(board_before)
            raise
        self.history.append(confirmed.san)
        self.white_turn = None
        self.attempt = None
        return confirmed

    def _restore(self, attempt: WhiteMoveAttempt) -> None:
        self.controller.reset(attempt.board_before)
        self.history[:] = attempt.history_before
        self.attempt = None
        self.white_turn = None

    def _restore_history(self, history: tuple[str, ...]) -> None:
        self.controller.reset(chess.Board(self.author.flow.start_fen))
        replayed: list[str] = []
        for san in history:
            confirmed = self.controller.confirm_san(san)
            replayed.append(confirmed.san)
        self.history[:] = replayed
        self.attempt = None
        self.white_turn = None

    def _require_attempt(self) -> WhiteMoveAttempt:
        if self.attempt is None:
            raise FlowValidationError("No White move attempt is active.")
        return self.attempt


def _attempt_result(
    turn: WhiteTurn,
    board_before: chess.Board,
    confirmed: ConfirmedAuthorMove,
) -> AttemptResult:
    if turn.unavailable_reason is not None:
        return AttemptResult.RULE_UNAVAILABLE
    recommendation = turn.recommendation
    if recommendation is None:
        return AttemptResult.FRONTIER
    expected = board_before.parse_san(recommendation.move_san)
    if expected.uci() == confirmed.move.uci:
        return AttemptResult.CORRECT
    if recommendation.source == "exception":
        return AttemptResult.MISMATCH_EXCEPTION
    return AttemptResult.MISMATCH_DEFAULT
