"""Interactive coordinator shared by the TUI and web Rulebook clients."""

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
from ..policy.models import MoveAttempt, StartingPieceRef
from ..policy.runtime import DecisionSource, PolicyDecision, PolicyRuntime
from .author import AuthorBoardController, ConfirmedAuthorMove, RulebookAuthor
from .errors import FlowError, FlowValidationError
from .models import (
    DevelopmentInstruction,
    InterruptRule,
    OpeningTag,
    Rulebook,
)
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
        self.author = RulebookAuthor(flow_path)
        self.runtime = PolicyRuntime(self.author.rulebook)
        self.controller = AuthorBoardController(_start_board(self.author.rulebook))
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
        return chess.WHITE if self.author.rulebook.side == "white" else chess.BLACK

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
        self.runtime = PolicyRuntime(self.author.rulebook)
        self.controller.reset(_start_board(self.author.rulebook))
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
                    OpeningMoveProvenance.EXACT_INTERRUPT,
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
            if self.is_policy_turn and not self.outcome
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
            raise FlowValidationError("There is no selected Rulebook move.")
        self._restore_history(attempt.history_before)
        board_before = self.board.copy(stack=False)
        confirmed = self.controller.confirm_uci(attempt.decision.move.uci())
        self._commit_confirmed_policy_move(confirmed, attempt.decision, board_before)
        return confirmed

    def complete_correct_move(self) -> None:
        attempt = self._require_attempt()
        if attempt.result is not AttemptResult.CORRECT:
            raise FlowValidationError("The current Rulebook attempt is not correct.")
        self._commit_confirmed_policy_move(
            attempt.selected_move, attempt.decision, attempt.board_before
        )

    def submit_pending_opponent_move(self) -> ConfirmedAuthorMove | None:
        return self._submit_opponent(
            self.controller.confirm_move,
            move_source=OpeningMoveProvenance.MANUAL,
        )

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

    def save_development(
        self, alias: str, development: DevelopmentInstruction | None
    ) -> PolicyMoveAttempt | None:
        return self._apply_candidate(
            self.author.candidate_with_development(alias, development)
        )

    def save_interrupt(
        self, alias: str, rule: InterruptRule
    ) -> PolicyMoveAttempt | None:
        return self._apply_candidate(self.author.candidate_with_interrupt(alias, rule))

    def delete_interrupt(self, alias: str, rule_id: str) -> PolicyMoveAttempt | None:
        return self._apply_candidate(
            self.author.candidate_without_interrupt(alias, rule_id)
        )

    def reorder_development(self, aliases: tuple[str, ...]) -> PolicyMoveAttempt | None:
        return self._apply_candidate(
            self.author.candidate_with_development_order(aliases)
        )

    def reorder_interrupts(
        self, references: tuple[str, ...]
    ) -> PolicyMoveAttempt | None:
        return self._apply_candidate(
            self.author.candidate_with_interrupt_order(references)
        )

    def add_opening_tag(self, tag: OpeningTag) -> None:
        self._apply_candidate(self.author.candidate_with_added_opening_tag(tag))

    def remove_opening_tag(self, tag: OpeningTag) -> None:
        self._apply_candidate(self.author.candidate_without_opening_tag(tag))

    def accept_attempt_as_interrupt(self) -> InterruptRule:
        attempt = self._require_attempt()
        if attempt.result not in {AttemptResult.MISMATCH, AttemptResult.FRONTIER}:
            raise FlowValidationError(
                "Only a mismatch or frontier move can be accepted here."
            )
        move = chess.Move.from_uci(attempt.selected_move.move.uci)
        if move.promotion is not None:
            raise FlowValidationError("Promotion actions are deferred in v4.")
        tracked = self.runtime.tracker.piece_id_at(move.from_square)
        if tracked is None:
            raise FlowValidationError("Attempted move has no original-piece identity.")
        ref = StartingPieceRef.from_original(tracked)
        try:
            alias = self.author.rulebook.alias_by_ref[ref]
        except KeyError as exc:
            raise FlowValidationError(
                f"Attempted piece {ref} requires a Rulebook alias."
            ) from exc
        existing_reference = next(
            (
                reference
                for reference, rule in self.author.rulebook.interrupt_by_ref.items()
                if rule.after_san is not None
                and normalized_position_key(attempt.board_before)
                in self.runtime.exact_positions
                and reference
                in self.runtime.exact_positions[
                    normalized_position_key(attempt.board_before)
                ]
            ),
            None,
        )
        rule_id = (
            existing_reference.split(".", 1)[1]
            if existing_reference is not None
            and existing_reference.startswith(f"{alias}.")
            else self._available_interrupt_id(
                alias, move.uci(), len(attempt.history_before)
            )
        )
        rule = InterruptRule(
            piece=ref,
            id=rule_id,
            requires=(),
            after_san=attempt.history_before,
            when=None,
            required=True,
            attempts=(MoveAttempt(chess.square_name(move.to_square)),),
            why=f"Accepted {attempt.selected_move.san} in this exact position.",
        )
        candidate = self.author.rulebook
        if existing_reference is not None:
            existing_alias, existing_id = existing_reference.split(".", 1)
            if existing_alias != alias or existing_id != rule.id:
                candidate = self.author.candidate_without_interrupt(
                    existing_alias, existing_id
                )
                candidate = self.author.candidate_with_interrupt(
                    alias,
                    rule,
                    base=candidate,
                )
            else:
                candidate = self.author.candidate_with_interrupt(alias, rule)
        else:
            candidate = self.author.candidate_with_interrupt(alias, rule)
        self._apply_candidate(candidate)
        return rule

    def _apply_candidate(self, candidate: Rulebook) -> PolicyMoveAttempt | None:
        attempt_uci = self.attempt.selected_move.move.uci if self.attempt else None
        history = self.attempt.history_before if self.attempt else tuple(self.history)
        source = self.author.store.encode(candidate)
        reparsed = self.author.store.decode(source, context="edited Rulebook")
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

    def _available_interrupt_id(self, alias: str, uci: str, ply: int) -> str:
        stem = f"accept-{uci}-ply-{ply}"
        ids = {item.id for item in self.author.rulebook.piece_by_alias[alias].rules}
        if stem not in ids:
            return stem
        suffix = 2
        while f"{stem}-{suffix}" in ids:
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
        result = (
            AttemptResult.FRONTIER
            if expected is None
            else (
                AttemptResult.CORRECT
                if expected.uci() == confirmed.move.uci
                else AttemptResult.MISMATCH
            )
        )
        self.attempt = PolicyMoveAttempt(
            board_before, history_before, confirmed, turn.decision, result
        )
        return self.attempt

    def _submit_opponent(
        self,
        commit: Callable[[], ConfirmedAuthorMove | None],
        *,
        move_source: OpeningMoveProvenance,
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
        self.runtime.rulebook = self.author.rulebook
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
        self.runtime.commit_move(
            board_before,
            move,
            self.board,
            selected_rule_id=decision.source_id,
            ply=len(self.history) + 1,
        )
        self.history.append(confirmed.san)
        in_book = self.opening_classifier.compare_move_to_book(board_before, move)
        exact = decision.source_id is not None and self._is_exact(decision.source_id)
        if exact:
            move_source = OpeningMoveProvenance.EXACT_INTERRUPT
            policy_rule_id = None
            exact_interrupt_id = decision.source_id
        elif decision.source in {DecisionSource.INTERRUPT, DecisionSource.DEVELOPMENT}:
            move_source = (
                OpeningMoveProvenance.BOOK_AND_POLICY
                if in_book
                else OpeningMoveProvenance.POLICY_ONLY
            )
            policy_rule_id = decision.source_id
            exact_interrupt_id = None
        else:
            move_source = OpeningMoveProvenance.FRONTIER
            policy_rule_id = None
            exact_interrupt_id = None
        self._append_opening_entry(
            board_before,
            move,
            confirmed.san,
            move_source=move_source,
            policy_rule_id=policy_rule_id,
            exact_interrupt_id=exact_interrupt_id,
        )
        self.attempt = None
        self.policy_turn = None

    def _restore_history(self, history: tuple[str, ...]) -> None:
        self.runtime, board = PolicyRuntime.replay(self.author.rulebook, history)
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
        exact_interrupt_id: str | None = None,
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
            exact_interrupt_id=exact_interrupt_id,
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
        board = _start_board(self.author.rulebook)
        runtime = PolicyRuntime(self.author.rulebook)
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
            if decision is not None and decision.move == move:
                exact = decision.source_id is not None and self._is_exact(
                    decision.source_id
                )
                if exact:
                    source = OpeningMoveProvenance.EXACT_INTERRUPT
                    policy_rule_id = None
                    exact_interrupt_id = decision.source_id
                else:
                    source = (
                        OpeningMoveProvenance.BOOK_AND_POLICY
                        if in_book
                        else OpeningMoveProvenance.POLICY_ONLY
                    )
                    policy_rule_id = decision.source_id
                    exact_interrupt_id = None
            elif controlled:
                source = OpeningMoveProvenance.FRONTIER
                policy_rule_id = None
                exact_interrupt_id = None
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
                exact_interrupt_id = None
            board.push(move)
            context = self.opening_classifier.context_after_move(
                board_before,
                move,
                board,
                previous,
                move_source=source,
                policy_rule_id=policy_rule_id,
                exact_interrupt_id=exact_interrupt_id,
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
                    if decision is not None and decision.move == move
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
                for reply in self.author.rulebook.opponent_replies
                if reply.after_san == history_before and reply.move_san == move_san
            ),
            None,
        )

    def _is_exact(self, reference: str) -> bool:
        rule = self.author.rulebook.interrupt_by_ref.get(reference)
        return rule is not None and rule.after_san is not None

    def _committed_board(self) -> chess.Board:
        return self.attempt.board_before if self.attempt is not None else self.board

    def _require_attempt(self) -> PolicyMoveAttempt:
        if self.attempt is None:
            raise FlowValidationError("No policy move attempt is active.")
        return self.attempt


def _start_board(rulebook: Rulebook) -> chess.Board:
    return (
        chess.Board()
        if rulebook.start_fen == "startpos"
        else chess.Board(rulebook.start_fen)
    )
