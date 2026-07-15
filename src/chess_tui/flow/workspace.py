"""Interactive coordinator for replaying and testing a deterministic v2 flow."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable

import chess

from ..game import ChessMove
from ..policy.runtime import DecisionSource, PolicyDecision, PolicyRuntime
from .author import AuthorBoardController, ConfirmedAuthorMove, FlowAuthor
from .errors import FlowError, FlowValidationError
from .models import ExactOverride, Flow, PolicyRule


class AttemptResult(str, Enum):
    CORRECT = "correct"
    MISMATCH = "mismatch"
    FRONTIER = "frontier"


@dataclass(frozen=True, slots=True)
class PolicyTurn:
    decision: PolicyDecision


@dataclass(frozen=True, slots=True)
class PolicyMoveAttempt:
    board_before: chess.Board
    history_before: tuple[str, ...]
    selected_move: ConfirmedAuthorMove
    decision: PolicyDecision
    result: AttemptResult


class FlowWorkspace:
    def __init__(self, flow_path: Path) -> None:
        self.author = FlowAuthor(flow_path)
        self.runtime = PolicyRuntime(self.author.flow)
        self.controller = AuthorBoardController(_start_board(self.author.flow))
        self.history: list[str] = []
        self.policy_turn: PolicyTurn | None = None
        self.attempt: PolicyMoveAttempt | None = None

    @property
    def board(self) -> chess.Board:
        return self.controller.board

    @property
    def outcome(self) -> chess.Outcome | None:
        return self.board.outcome(claim_draw=False)

    @property
    def controlled_color(self) -> chess.Color:
        return chess.WHITE if self.author.flow.side == "white" else chess.BLACK

    @property
    def is_policy_turn(self) -> bool:
        return self.board.turn == self.controlled_color

    @property
    def can_go_back(self) -> bool:
        if self.attempt is not None:
            return True
        if self.board.turn != self.controlled_color:
            return bool(self.history)
        return len(self.history) >= 2

    @property
    def can_restart(self) -> bool:
        return bool(self.history) or self.attempt is not None

    def restart(self) -> PolicyTurn:
        self.restart_position()
        return self.begin_policy_turn()

    def restart_position(self) -> None:
        self.runtime = PolicyRuntime(self.author.flow)
        self.controller.reset(_start_board(self.author.flow))
        self.history.clear()
        self.attempt = None
        self.policy_turn = None

    def go_back_to_previous_decision(self) -> PolicyTurn:
        if not self.can_go_back:
            raise FlowValidationError("There is no earlier policy decision.")
        if self.attempt is not None:
            retained = self.attempt.history_before
        elif self.board.turn != self.controlled_color:
            retained = tuple(self.history[:-1])
        else:
            retained = tuple(self.history[:-2])
        self._restore_history(retained)
        return self.begin_policy_turn()

    def reload(self) -> PolicyTurn | None:
        history = self.attempt.history_before if self.attempt else tuple(self.history)
        self.author.reload()
        self._restore_history(history)
        return (
            self.begin_policy_turn()
            if self.is_policy_turn and self.outcome is None
            else None
        )

    def begin_policy_turn(self) -> PolicyTurn:
        if self.outcome is not None:
            raise FlowValidationError("Cannot begin a policy turn after game over.")
        if not self.is_policy_turn:
            raise FlowValidationError("Cannot resolve policy on the opponent's turn.")
        self.policy_turn = PolicyTurn(self.runtime.resolve(self.board))
        self.attempt = None
        return self.policy_turn

    def submit_pending_policy_move(self) -> PolicyMoveAttempt | None:
        return self._submit_policy(self.controller.confirm_move)

    def submit_policy_san(self, san: str) -> PolicyMoveAttempt:
        attempt = self._submit_policy(lambda: self.controller.confirm_san(san))
        assert attempt is not None
        return attempt

    def submit_policy_uci(self, uci: str) -> PolicyMoveAttempt:
        attempt = self._submit_policy(lambda: self.controller.confirm_uci(uci))
        assert attempt is not None
        return attempt

    def retry_policy_move(self) -> PolicyTurn:
        attempt = self._require_attempt()
        self._restore_history(attempt.history_before)
        return self.begin_policy_turn()

    def continue_with_policy_move(self) -> ConfirmedAuthorMove:
        attempt = self._require_attempt()
        if attempt.decision.move is None:
            raise FlowValidationError(
                "There is no selected policy move to continue with."
            )
        self._restore_history(attempt.history_before)
        board_before = self.board.copy(stack=False)
        confirmed = self.controller.confirm_uci(attempt.decision.move.uci())
        self._commit_confirmed_policy_move(confirmed, attempt.decision, board_before)
        return confirmed

    def complete_correct_move(self) -> None:
        attempt = self._require_attempt()
        if attempt.result is not AttemptResult.CORRECT:
            raise FlowValidationError("The current policy attempt is not correct.")
        self._commit_confirmed_policy_move(
            attempt.selected_move, attempt.decision, attempt.board_before
        )

    def submit_pending_opponent_move(self) -> ConfirmedAuthorMove | None:
        return self._submit_opponent(self.controller.confirm_move)

    def submit_opponent_san(self, san: str) -> ConfirmedAuthorMove:
        confirmed = self._submit_opponent(lambda: self.controller.confirm_san(san))
        assert confirmed is not None
        return confirmed

    def submit_opponent_uci(self, uci: str) -> ConfirmedAuthorMove:
        confirmed = self._submit_opponent(lambda: self.controller.confirm_uci(uci))
        assert confirmed is not None
        return confirmed

    def update_rule(self, replacement: PolicyRule) -> PolicyMoveAttempt | None:
        return self._apply_candidate(self.author.candidate_with_rule(replacement))

    def update_override(self, replacement: ExactOverride) -> PolicyMoveAttempt | None:
        return self._apply_candidate(self.author.candidate_with_override(replacement))

    def _apply_candidate(self, candidate: Flow) -> PolicyMoveAttempt | None:
        attempt_uci = self.attempt.selected_move.move.uci if self.attempt else None
        history = self.attempt.history_before if self.attempt else tuple(self.history)
        # Validate serialization and deterministic replay before touching disk or live state.
        source = self.author.store.encode(candidate)
        reparsed = self.author.store.decode(source, context="edited flow")
        PolicyRuntime.replay(reparsed, history)
        self.author.save_candidate(reparsed)
        self._restore_history(history)
        if attempt_uci is None or not self.is_policy_turn:
            if self.is_policy_turn and self.outcome is None:
                self.begin_policy_turn()
            return None
        refreshed = self.submit_policy_uci(attempt_uci)
        if refreshed.result is AttemptResult.CORRECT:
            self.complete_correct_move()
        return refreshed

    def _submit_policy(
        self, commit: Callable[[], ConfirmedAuthorMove | None]
    ) -> PolicyMoveAttempt | None:
        turn = self.policy_turn or self.begin_policy_turn()
        board_before = self.board.copy(stack=False)
        history_before = tuple(self.history)
        confirmed = commit()
        if confirmed is None:
            return None
        if confirmed.color != self.controlled_color:
            raise FlowValidationError("Expected a move by the controlled side.")
        expected = turn.decision.move
        if expected is None:
            result = AttemptResult.FRONTIER
        elif expected.uci() == confirmed.move.uci:
            result = AttemptResult.CORRECT
        else:
            result = AttemptResult.MISMATCH
        self.attempt = PolicyMoveAttempt(
            board_before, history_before, confirmed, turn.decision, result
        )
        return self.attempt

    def _submit_opponent(
        self, commit: Callable[[], ConfirmedAuthorMove | None]
    ) -> ConfirmedAuthorMove | None:
        if self.is_policy_turn:
            raise FlowValidationError("Expected an opponent move.")
        board_before = self.board.copy(stack=False)
        history_before = tuple(self.history)
        confirmed = commit()
        if confirmed is None:
            return None
        if confirmed.color == self.controlled_color:
            raise FlowValidationError("Expected a move by the opponent.")
        try:
            self.author.record_opponent_reply(
                board_before, history_before, confirmed.san
            )
        except FlowError:
            self.controller.reset(board_before)
            raise
        move = chess.Move.from_uci(confirmed.move.uci)
        self.runtime.flow = self.author.flow
        self.runtime.commit_move(
            board_before, move, self.board, ply=len(self.history) + 1
        )
        self.history.append(confirmed.san)
        self.policy_turn = None
        self.attempt = None
        return confirmed

    def _commit_confirmed_policy_move(
        self,
        confirmed: ConfirmedAuthorMove,
        decision: PolicyDecision,
        board_before: chess.Board,
    ) -> None:
        move = chess.Move.from_uci(confirmed.move.uci)
        selected_rule_id = (
            decision.source_id if decision.source is DecisionSource.RULE else None
        )
        self.runtime.commit_move(
            board_before,
            move,
            self.board,
            selected_rule_id=selected_rule_id,
            ply=len(self.history) + 1,
        )
        self.history.append(confirmed.san)
        self.attempt = None
        self.policy_turn = None

    def _restore_history(self, history: tuple[str, ...]) -> None:
        self.runtime, board = PolicyRuntime.replay(self.author.flow, history)
        last_move = board.peek().uci() if board.move_stack else None
        self.controller.reset(board)
        if last_move is not None:
            self.controller.interaction.last_move = ChessMove.from_uci(last_move)
        self.history[:] = history
        self.attempt = None
        self.policy_turn = None

    def _require_attempt(self) -> PolicyMoveAttempt:
        if self.attempt is None:
            raise FlowValidationError("No policy move attempt is active.")
        return self.attempt


def _start_board(flow: Flow) -> chess.Board:
    return (
        chess.Board() if flow.start_fen == "startpos" else chess.Board(flow.start_fen)
    )
