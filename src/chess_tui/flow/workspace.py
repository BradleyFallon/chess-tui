"""Interactive coordinator for replaying and testing a deterministic v2 flow."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable

import chess

from ..game import ChessMove
from ..opening.classification import (
    BookContinuation,
    OpeningClassifier,
    OpeningContext,
    OpeningHistoryEntry,
    OpeningMoveProvenance,
)
from ..policy import MoveAction
from ..policy.runtime import DecisionSource, PolicyDecision, PolicyRuntime
from .author import AuthorBoardController, ConfirmedAuthorMove, FlowAuthor
from .errors import FlowError, FlowValidationError
from .models import AuthoredRule, DevelopmentRule, ExactOverride, Flow, OpeningTag
from .position import normalized_position_key


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
    def __init__(
        self,
        flow_path: Path,
        *,
        opening_classifier: OpeningClassifier | None = None,
    ) -> None:
        self.author = FlowAuthor(flow_path)
        self.runtime = PolicyRuntime(self.author.flow)
        self.controller = AuthorBoardController(_start_board(self.author.flow))
        self.opening_classifier = opening_classifier or OpeningClassifier.bundled()
        self.history: list[str] = []
        self.opening_history: list[OpeningHistoryEntry] = []
        self.explored_opening_nodes: dict[tuple[str, ...], OpeningHistoryEntry] = {}
        self._opponent_provenance: dict[
            tuple[str, ...], tuple[OpeningMoveProvenance, str | None]
        ] = {}
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
        self.opening_history.clear()
        self.attempt = None
        self.policy_turn = None

    def get_current_opening_context(self) -> OpeningContext:
        if self.opening_history:
            return self.opening_history[-1].context
        return self.opening_classifier.initial_context(self._committed_board())

    def get_opening_history(self) -> tuple[OpeningHistoryEntry, ...]:
        return tuple(self.opening_history)

    def get_book_continuations(self) -> tuple[BookContinuation, ...]:
        return self.opening_classifier.book_continuations(self._committed_board())

    def get_reachable_defenses(self) -> tuple[str, ...]:
        return self.opening_classifier.reachable_defenses(self._committed_board())

    def compare_move_to_book(self, move: chess.Move) -> bool:
        return self.opening_classifier.compare_move_to_book(
            self._committed_board(), move
        )

    def find_book_policy_transition(self) -> OpeningHistoryEntry | None:
        return next(
            (
                entry
                for entry in self.opening_history
                if entry.context.move_source
                in {
                    OpeningMoveProvenance.POLICY_ONLY,
                    OpeningMoveProvenance.EXACT_OVERRIDE,
                }
                and entry.context.played_move_in_book is False
            ),
            None,
        )

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

    def submit_opponent_san(
        self,
        san: str,
        *,
        move_source: OpeningMoveProvenance = OpeningMoveProvenance.MANUAL,
    ) -> ConfirmedAuthorMove:
        confirmed = self._submit_opponent(
            lambda: self.controller.confirm_san(san), move_source=move_source
        )
        assert confirmed is not None
        return confirmed

    def submit_opponent_uci(
        self,
        uci: str,
        *,
        move_source: OpeningMoveProvenance = OpeningMoveProvenance.MANUAL,
    ) -> ConfirmedAuthorMove:
        confirmed = self._submit_opponent(
            lambda: self.controller.confirm_uci(uci), move_source=move_source
        )
        assert confirmed is not None
        return confirmed

    def update_rule(self, replacement: AuthoredRule) -> PolicyMoveAttempt | None:
        return self._apply_candidate(self.author.candidate_with_rule(replacement))

    def add_development_rule(
        self, development_rule: DevelopmentRule
    ) -> PolicyMoveAttempt | None:
        return self._apply_candidate(
            self.author.candidate_with_added_development_rule(development_rule)
        )

    def save_development_rule(
        self, development_rule: DevelopmentRule
    ) -> PolicyMoveAttempt | None:
        if any(rule.id == development_rule.id for rule in self.author.flow.rules):
            candidate = self.author.candidate_with_rule(development_rule)
        else:
            candidate = self.author.candidate_with_added_development_rule(
                development_rule
            )
        return self._apply_candidate(candidate)

    def delete_development_rule(self, rule_id: str) -> PolicyMoveAttempt | None:
        return self._apply_candidate(
            self.author.candidate_without_development_rule(rule_id)
        )

    def reorder_development_rules(
        self, ordered_rule_ids: tuple[str, ...]
    ) -> PolicyMoveAttempt | None:
        return self._apply_candidate(
            self.author.candidate_with_development_order(ordered_rule_ids)
        )

    def update_override(self, replacement: ExactOverride) -> PolicyMoveAttempt | None:
        return self._apply_candidate(self.author.candidate_with_override(replacement))

    def add_opening_tag(self, tag: OpeningTag) -> None:
        self._apply_candidate(self.author.candidate_with_added_opening_tag(tag))

    def remove_opening_tag(self, tag: OpeningTag) -> None:
        self._apply_candidate(self.author.candidate_without_opening_tag(tag))

    def allow_mismatch_as_override(self) -> ExactOverride:
        attempt = self._require_attempt()
        if attempt.result is not AttemptResult.MISMATCH:
            raise FlowValidationError(
                "Only a mismatching policy move can be added as an exact rule."
            )
        move = chess.Move.from_uci(attempt.selected_move.move.uci)
        if move.promotion is not None:
            raise FlowValidationError(
                "Promotion moves cannot be authored because v2 actions do not encode promotion."
            )
        tracked_piece = next(
            (
                piece
                for piece in self.runtime.tracker.pieces
                if piece.current_square == move.from_square
            ),
            None,
        )
        if tracked_piece is None:
            raise FlowValidationError(
                "The attempted move does not belong to a tracked original piece."
            )
        position_key = normalized_position_key(attempt.board_before)
        existing = self.runtime.overrides_by_position.get(position_key)
        override = ExactOverride(
            id=(
                existing.id
                if existing is not None
                else self._available_override_id(
                    move.uci(), len(attempt.history_before)
                )
            ),
            after_san=attempt.history_before,
            move=MoveAction(tracked_piece.id, chess.square_name(move.to_square)),
            enabled=True,
            note=f"Added from chat to allow {attempt.selected_move.san} here.",
        )
        candidate = (
            self.author.candidate_with_override(override)
            if existing is not None
            else self.author.candidate_with_added_override(override)
        )
        self._apply_candidate(candidate)
        return override

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

    def _available_override_id(self, uci: str, ply: int) -> str:
        stem = f"allow-{uci}-ply-{ply}"
        existing = {item.id for item in self.author.flow.overrides}
        if stem not in existing:
            return stem
        suffix = 2
        while f"{stem}-{suffix}" in existing:
            suffix += 1
        return f"{stem}-{suffix}"

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
        self,
        commit: Callable[[], ConfirmedAuthorMove | None],
        *,
        move_source: OpeningMoveProvenance = OpeningMoveProvenance.MANUAL,
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
        path = tuple(self.history)
        recorded_reply_id = self._recorded_reply_id(history_before, confirmed.san)
        self._opponent_provenance[path] = (move_source, recorded_reply_id)
        self._append_opening_entry(
            board_before,
            move,
            confirmed.san,
            move_source=move_source,
            recorded_reply_id=recorded_reply_id,
        )
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
        in_book = self.opening_classifier.compare_move_to_book(board_before, move)
        if decision.source is DecisionSource.RULE:
            move_source = (
                OpeningMoveProvenance.BOOK_AND_POLICY
                if in_book
                else OpeningMoveProvenance.POLICY_ONLY
            )
            policy_rule_id = decision.source_id
            exact_override_id = None
        elif decision.source is DecisionSource.EXACT_OVERRIDE:
            move_source = OpeningMoveProvenance.EXACT_OVERRIDE
            policy_rule_id = None
            exact_override_id = decision.source_id
        else:
            move_source = OpeningMoveProvenance.FRONTIER
            policy_rule_id = None
            exact_override_id = None
        self._append_opening_entry(
            board_before,
            move,
            confirmed.san,
            move_source=move_source,
            policy_rule_id=policy_rule_id,
            exact_override_id=exact_override_id,
        )
        self.attempt = None
        self.policy_turn = None

    def _restore_history(self, history: tuple[str, ...]) -> None:
        self.runtime, board = PolicyRuntime.replay(self.author.flow, history)
        last_move = board.peek().uci() if board.move_stack else None
        self.controller.reset(board)
        if last_move is not None:
            self.controller.interaction.last_move = ChessMove.from_uci(last_move)
        self.history[:] = history
        self._rebuild_opening_history(history)
        self.attempt = None
        self.policy_turn = None

    def _append_opening_entry(
        self,
        board_before: chess.Board,
        move: chess.Move,
        san: str,
        *,
        move_source: OpeningMoveProvenance,
        policy_rule_id: str | None = None,
        exact_override_id: str | None = None,
        recorded_reply_id: str | None = None,
    ) -> None:
        previous = (
            self.opening_history[-1].context
            if self.opening_history
            else self.opening_classifier.initial_context(board_before)
        )
        context = self.opening_classifier.context_after_move(
            board_before,
            move,
            self.board,
            previous,
            move_source=move_source,
            policy_rule_id=policy_rule_id,
            exact_override_id=exact_override_id,
            recorded_reply_id=recorded_reply_id,
        )
        entry = OpeningHistoryEntry(
            ply=len(self.history),
            san=san,
            uci=move.uci(),
            position_key=normalized_position_key(self.board),
            context=context,
        )
        self.opening_history.append(entry)
        self.explored_opening_nodes[tuple(self.history)] = entry

    def _rebuild_opening_history(self, history: tuple[str, ...]) -> None:
        board = _start_board(self.author.flow)
        runtime = PolicyRuntime(self.author.flow)
        rebuilt: list[OpeningHistoryEntry] = []
        previous = self.opening_classifier.initial_context(board)
        prefix: list[str] = []
        for ply, san in enumerate(history, start=1):
            board_before = board.copy(stack=False)
            move = board.parse_san(san)
            controlled = board.turn == self.controlled_color
            decision = runtime.resolve(board) if controlled else None
            in_book = self.opening_classifier.compare_move_to_book(board, move)
            prefix.append(san)
            path = tuple(prefix)
            recorded_reply_id: str | None = None
            if decision is not None and decision.source is DecisionSource.RULE:
                source = (
                    OpeningMoveProvenance.BOOK_AND_POLICY
                    if in_book
                    else OpeningMoveProvenance.POLICY_ONLY
                )
                policy_rule_id = decision.source_id
                exact_override_id = None
            elif (
                decision is not None
                and decision.source is DecisionSource.EXACT_OVERRIDE
            ):
                source = OpeningMoveProvenance.EXACT_OVERRIDE
                policy_rule_id = None
                exact_override_id = decision.source_id
            elif controlled:
                source = OpeningMoveProvenance.FRONTIER
                policy_rule_id = None
                exact_override_id = None
            else:
                stored = self._opponent_provenance.get(path)
                if stored is not None:
                    source, recorded_reply_id = stored
                else:
                    recorded_reply_id = self._recorded_reply_id(tuple(prefix[:-1]), san)
                    source = (
                        OpeningMoveProvenance.RECORDED_BRANCH
                        if recorded_reply_id is not None
                        else OpeningMoveProvenance.MANUAL
                    )
                policy_rule_id = None
                exact_override_id = None
            board.push(move)
            context = self.opening_classifier.context_after_move(
                board_before,
                move,
                board,
                previous,
                move_source=source,
                policy_rule_id=policy_rule_id,
                exact_override_id=exact_override_id,
                recorded_reply_id=recorded_reply_id,
            )
            entry = OpeningHistoryEntry(
                ply=ply,
                san=san,
                uci=move.uci(),
                position_key=normalized_position_key(board),
                context=context,
            )
            rebuilt.append(entry)
            self.explored_opening_nodes[path] = entry
            runtime.commit_move(
                board_before,
                move,
                board,
                selected_rule_id=(
                    decision.source_id
                    if decision is not None and decision.source is DecisionSource.RULE
                    else None
                ),
                ply=ply,
            )
            previous = context
        self.opening_history[:] = rebuilt

    def _recorded_reply_id(
        self, history_before: tuple[str, ...], move_san: str
    ) -> str | None:
        return next(
            (
                reply.id
                for reply in self.author.flow.opponent_replies
                if reply.after_san == history_before and reply.move_san == move_san
            ),
            None,
        )

    def _committed_board(self) -> chess.Board:
        return self.attempt.board_before if self.attempt is not None else self.board

    def _require_attempt(self) -> PolicyMoveAttempt:
        if self.attempt is None:
            raise FlowValidationError("No policy move attempt is active.")
        return self.attempt


def _start_board(flow: Flow) -> chess.Board:
    return (
        chess.Board() if flow.start_fen == "startpos" else chess.Board(flow.start_fen)
    )
