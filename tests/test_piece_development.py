import chess
import pytest

from chess_tui.flow import (
    CaptureAttempt,
    InterruptRule,
    MoveAttempt,
    PieceScript,
    Rulebook,
)
from chess_tui.policy import (
    AttackBalanceCondition,
    AttackedByCondition,
    AttackedCondition,
    CapturableCondition,
    ConditionEvaluator,
    LastMove,
    OriginalPieceTracker,
    PositionAnalyzer,
    StartingPieceRef,
    UndefendedCondition,
    UnderDefendedCondition,
    condition_to_data,
    parse_condition,
)
from chess_tui.policy.actions import ActionResolver, ActionStatus
from chess_tui.policy.runtime import DecisionSource, PolicyRuntime


def ref(value: str) -> StartingPieceRef:
    return StartingPieceRef.parse(value)


def tactical_position():
    board = chess.Board(None)
    placements = {
        "e1": chess.Piece(chess.KING, chess.WHITE),
        "a1": chess.Piece(chess.ROOK, chess.WHITE),
        "b1": chess.Piece(chess.KNIGHT, chess.WHITE),
        "e8": chess.Piece(chess.KING, chess.BLACK),
        "a8": chess.Piece(chess.ROOK, chess.BLACK),
        "b8": chess.Piece(chess.KNIGHT, chess.BLACK),
        "c8": chess.Piece(chess.BISHOP, chess.BLACK),
    }
    for square, piece in placements.items():
        board.set_piece_at(chess.parse_square(square), piece)
    tracker = OriginalPieceTracker(board)
    relocate(board, tracker, "a8", "b2", 1)
    relocate(board, tracker, "b8", "c3", 2)
    relocate(board, tracker, "c8", "a3", 3)
    board.turn = chess.WHITE
    return board, tracker


def relocate(board, tracker, source: str, target: str, ply: int) -> None:
    before = board.copy(stack=False)
    move = chess.Move.from_uci(source + target)
    tracker.apply_move(before, move, ply=ply)
    piece = board.remove_piece_at(move.from_square)
    assert piece
    board.remove_piece_at(move.to_square)
    board.set_piece_at(move.to_square, piece)


def evaluator():
    board, tracker = tactical_position()
    relations = PositionAnalyzer().analyze(board, tracker)
    subject = ref("piece:white:knight:queenside")
    return (
        board,
        tracker,
        relations,
        subject,
        ConditionEvaluator(board, tracker, relations=relations, subject=subject),
    )


def test_relation_backed_conditions_include_structured_details() -> None:
    _, _, _, subject, evaluate = evaluator()
    cases = (
        AttackedCondition("self"),
        AttackedByCondition("self", attacker=ref("piece:black:rook:queenside")),
        AttackedByCondition("self", attacker_type="knight"),
        UnderDefendedCondition("self"),
        AttackBalanceCondition("self", 1),
    )
    for condition in cases:
        result = evaluate.evaluate(condition)
        assert result.value
        assert result.details["target"] == str(subject)
        assert result.details["attackerCount"] == 2
        assert result.details["defenderCount"] == 1
    assert not evaluate.evaluate(UndefendedCondition("self")).value


def test_capturable_condition_uses_owning_piece_and_unique_legal_capture() -> None:
    board, tracker, relations, subject, evaluate = evaluator()
    result = evaluate.evaluate(CapturableCondition(ref("piece:black:bishop:queenside")))
    # The knight on b1 captures a3.
    assert result.value
    assert result.details["candidateMoves"] == ["b1a3"]
    resolved = ActionResolver().resolve(
        CaptureAttempt(target_piece=ref("piece:black:bishop:queenside")),
        board=board,
        tracker=tracker,
        relations=relations,
        subject=subject,
    )
    assert resolved.status is ActionStatus.RESOLVED
    assert resolved.move is not None
    assert resolved.move.uci() == "b1a3"


def test_move_capture_attacker_capture_type_and_failed_action() -> None:
    board, tracker, relations, subject, evaluate = evaluator()
    resolver = ActionResolver()
    move = resolver.resolve(
        MoveAttempt("d2"),
        board=board,
        tracker=tracker,
        relations=relations,
        subject=subject,
    )
    assert move.status is ActionStatus.RESOLVED

    trigger = evaluate.evaluate(AttackedCondition("self"))
    attacker = resolver.resolve(
        CaptureAttempt(triggering_attacker=True),
        board=board,
        tracker=tracker,
        relations=relations,
        subject=subject,
        trigger=trigger,
    )
    assert attacker.status is ActionStatus.RESOLVED
    assert attacker.move is not None
    assert attacker.move.uci() == "b1c3"

    bishop = resolver.resolve(
        CaptureAttempt(target_type="bishop"),
        board=board,
        tracker=tracker,
        relations=relations,
        subject=subject,
    )
    assert bishop.status is ActionStatus.RESOLVED

    queen = resolver.resolve(
        CaptureAttempt(target_type="queen"),
        board=board,
        tracker=tracker,
        relations=relations,
        subject=subject,
    )
    assert queen.status is ActionStatus.FAILED


def test_capture_type_ambiguity_fails_loudly() -> None:
    board = chess.Board(None)
    for square, piece in {
        "e1": chess.Piece(chess.KING, chess.WHITE),
        "b1": chess.Piece(chess.KNIGHT, chess.WHITE),
        "e8": chess.Piece(chess.KING, chess.BLACK),
        "c8": chess.Piece(chess.BISHOP, chess.BLACK),
        "f8": chess.Piece(chess.BISHOP, chess.BLACK),
    }.items():
        board.set_piece_at(chess.parse_square(square), piece)
    tracker = OriginalPieceTracker(board)
    relocate(board, tracker, "b1", "c3", 1)
    relocate(board, tracker, "c8", "b5", 2)
    relocate(board, tracker, "f8", "d5", 3)
    board.turn = chess.WHITE
    relations = PositionAnalyzer().analyze(board, tracker)
    result = ActionResolver().resolve(
        CaptureAttempt(target_type="bishop"),
        board=board,
        tracker=tracker,
        relations=relations,
        subject=ref("piece:white:knight:queenside"),
    )
    assert result.status is ActionStatus.AMBIGUOUS
    assert {move.uci() for move in result.candidates} == {"c3b5", "c3d5"}


def test_ambiguous_attempt_falls_through_to_later_resolving_attempt() -> None:
    knight = ref("piece:white:knight:queenside")
    interrupt = InterruptRule(
        piece=knight,
        id="ordered-fallback",
        requires=(),
        after_san=None,
        when=None,
        required=True,
        attempts=(
            CaptureAttempt(target_type="bishop"),
            MoveAttempt("d2"),
        ),
        why="Try a deterministic fallback after an ambiguous capture.",
    )
    rulebook = Rulebook(
        version=4,
        name="Ambiguous fallback",
        start_fen="4k3/8/8/8/8/b1b5/8/1N5K w - - 0 1",
        side="white",
        development_order=(),
        interrupt_order=("knight.ordered-fallback",),
        pieces=(PieceScript("knight", knight, None, (interrupt,)),),
    )
    decision = PolicyRuntime(rulebook).resolve(chess.Board(rulebook.start_fen))
    assert decision.source is DecisionSource.INTERRUPT
    assert decision.move_san == "Nd2"
    attempts = decision.interrupt_resolutions[0].attempts
    assert [attempt.status for attempt in attempts] == [
        ActionStatus.AMBIGUOUS,
        ActionStatus.RESOLVED,
    ]


def test_illegal_capture_caused_by_king_pin_is_filtered() -> None:
    board = chess.Board("4r1k1/8/8/8/8/8/4R2b/4K3 w - - 0 1")
    tracker = OriginalPieceTracker(board)
    relations = PositionAnalyzer().analyze(board, tracker)
    subject = tracker.piece_id_at(chess.E2)
    assert subject is not None
    assert [item.capture.uci() for item in relations.get(subject).attacks] == ["e2e8"]


def test_self_requires_an_owning_subject() -> None:
    board, tracker = tactical_position()[:2]
    with pytest.raises(ValueError, match="owning piece"):
        ConditionEvaluator(board, tracker).evaluate(AttackedCondition("self"))


def test_surviving_history_position_and_boolean_conditions_round_trip() -> None:
    board = chess.Board()
    tracker = OriginalPieceTracker(board)
    before = board.copy(stack=False)
    move = board.parse_san("e4")
    board.push(move)
    tracker.apply_move(before, move, ply=1)
    aliases = {
        "e-pawn": ref("piece:white:pawn:e"),
        "d-pawn": ref("piece:white:pawn:d"),
    }
    evaluator = ConditionEvaluator(
        board,
        tracker,
        subject=aliases["e-pawn"],
        last_move=LastMove(
            aliases["e-pawn"].original_piece_id,
            "e4",
        ),
    )
    cases = (
        ({"moved": "self"}, True),
        ({"unmoved": "d-pawn"}, True),
        ({"captured": "self"}, False),
        ({"at": {"piece": "self", "square": "e4"}}, True),
        ({"occupied": "e4"}, True),
        ({"empty": "e2"}, True),
        (
            {
                "occupied_by": {
                    "square": "e4",
                    "color": "white",
                    "type": "pawn",
                }
            },
            True,
        ),
        ({"in_check": "black"}, False),
        ({"last_move": {"piece": "e-pawn", "to": "e4"}}, True),
        ({"last_move": {"piece": "self", "to": "e4"}}, True),
        ({"all": [{"moved": "self"}, {"empty": "e2"}]}, True),
        ({"any": [{"captured": "self"}, {"occupied": "e4"}]}, True),
        ({"not": {"captured": "self"}}, True),
    )
    alias_by_ref = {piece: alias for alias, piece in aliases.items()}
    for source, expected in cases:
        condition = parse_condition(source, aliases=aliases)
        assert evaluator.evaluate(condition).value is expected
        serialized = condition_to_data(condition, aliases=alias_by_ref)
        assert parse_condition(serialized, aliases=aliases) == condition
