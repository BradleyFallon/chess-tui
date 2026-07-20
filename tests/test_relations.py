import chess

from chess_tui.policy import (
    OriginalPieceTracker,
    PositionAnalyzer,
    StartingPieceRef,
)


def board_with_backrank_pieces(*pieces: tuple[str, chess.Piece]) -> chess.Board:
    board = chess.Board(None)
    board.set_piece_at(chess.E1, chess.Piece(chess.KING, chess.WHITE))
    board.set_piece_at(chess.E8, chess.Piece(chess.KING, chess.BLACK))
    for square, piece in pieces:
        board.set_piece_at(chess.parse_square(square), piece)
    board.turn = chess.WHITE
    return board


def relocate(
    board: chess.Board,
    tracker: OriginalPieceTracker,
    source: str,
    target: str,
    *,
    ply: int,
) -> None:
    source_square = chess.parse_square(source)
    target_square = chess.parse_square(target)
    before = board.copy(stack=False)
    tracker.apply_move(before, chess.Move(source_square, target_square), ply=ply)
    piece = board.remove_piece_at(source_square)
    assert piece is not None
    board.remove_piece_at(target_square)
    board.set_piece_at(target_square, piece)


def test_knight_attack_ignores_blockers_and_identity_survives_movement() -> None:
    board = board_with_backrank_pieces(
        ("b1", chess.Piece(chess.KNIGHT, chess.WHITE)),
        ("c8", chess.Piece(chess.BISHOP, chess.BLACK)),
        ("a2", chess.Piece(chess.PAWN, chess.WHITE)),
        ("b2", chess.Piece(chess.PAWN, chess.WHITE)),
    )
    tracker = OriginalPieceTracker(board)
    relocate(board, tracker, "b1", "c3", ply=1)
    relocate(board, tracker, "c8", "b5", ply=2)
    original = StartingPieceRef.parse("piece:white:knight:queenside").original_piece_id
    facts = PositionAnalyzer().analyze(board, tracker).get(original)
    assert [item.capture.uci() for item in facts.attacks] == ["c3b5"]
    assert facts.piece == original


def test_slider_rays_stop_at_first_occupied_square() -> None:
    board = board_with_backrank_pieces(
        ("c1", chess.Piece(chess.BISHOP, chess.WHITE)),
        ("a1", chess.Piece(chess.ROOK, chess.WHITE)),
        ("d1", chess.Piece(chess.QUEEN, chess.WHITE)),
        ("d2", chess.Piece(chess.PAWN, chess.WHITE)),
        ("a2", chess.Piece(chess.PAWN, chess.WHITE)),
        ("b2", chess.Piece(chess.PAWN, chess.BLACK)),
        ("a3", chess.Piece(chess.ROOK, chess.BLACK)),
    )
    tracker = OriginalPieceTracker(board)
    relations = PositionAnalyzer().analyze(board, tracker)
    bishop = tracker.piece_id_at(chess.C1)
    rook = tracker.piece_id_at(chess.A1)
    queen = tracker.piece_id_at(chess.D1)
    assert bishop and rook and queen
    assert [item.capture.uci() for item in relations.get(bishop).attacks] == ["c1b2"]
    assert not relations.get(rook).attacks
    assert not relations.get(queen).attacks


def test_absolute_pin_excludes_illegal_attack_but_allows_capture_on_pin_line() -> None:
    board = chess.Board("4r1k1/8/8/8/8/8/4R2b/4K3 w - - 0 1")
    tracker = OriginalPieceTracker(board)
    rook = tracker.piece_id_at(chess.E2)
    bishop = tracker.piece_id_at(chess.H2)
    assert rook and bishop
    facts = PositionAnalyzer().analyze(board, tracker).get(rook)
    assert facts.king_pinned
    assert all(item.target != bishop for item in facts.attacks)
    assert [item.capture.uci() for item in facts.attacks] == ["e2e8"]


def test_illegal_king_recapture_and_pinned_defender_do_not_count() -> None:
    board = chess.Board("4k3/8/8/8/8/2br4/3P4/3K4 b - - 0 1")
    tracker = OriginalPieceTracker(board)
    pawn = tracker.piece_id_at(chess.D2)
    assert pawn
    facts = PositionAnalyzer().analyze(board, tracker).get(pawn)
    assert facts.attacker_count == 2
    assert facts.defender_count == 0

    board = chess.Board("4r1k1/8/8/8/8/2br4/3PR3/4K3 b - - 0 1")
    tracker = OriginalPieceTracker(board)
    pawn = tracker.piece_id_at(chess.D2)
    assert pawn
    facts = PositionAnalyzer().analyze(board, tracker).get(pawn)
    assert facts.defender_count == 0


def test_defenders_are_simulated_per_attacker_and_may_differ() -> None:
    history = (
        "h3",
        "g6",
        "a4",
        "Nf6",
        "Na3",
        "h6",
        "b3",
        "g5",
        "Nb1",
        "c6",
        "Bb2",
        "a5",
        "h4",
        "g4",
        "g3",
        "Bg7",
        "Nf3",
        "e6",
        "Rh3",
        "Nh7",
        "d4",
        "Rf8",
        "Ng1",
        "f6",
        "h5",
        "b5",
        "Ba3",
        "Qb6",
        "Qc1",
        "Rh8",
        "Bb4",
        "Qxd4",
        "Qg5",
        "Bf8",
        "Nc3",
        "Bg7",
        "f4",
    )
    board = chess.Board()
    tracker = OriginalPieceTracker(board)
    for ply, san in enumerate(history, start=1):
        before = board.copy(stack=False)
        move = board.parse_san(san)
        board.push(move)
        tracker.apply_move(before, move, ply=ply)
    target = StartingPieceRef.parse("piece:white:pawn:f").original_piece_id
    facts = PositionAnalyzer().analyze(board, tracker).get(target)
    assert len(facts.defenders_by_attacker) == 2
    sets = {
        attacker: {item.defender for item in defenders}
        for attacker, defenders in facts.defenders_by_attacker.items()
    }
    assert len({frozenset(value) for value in sets.values()}) == 2


def test_captured_pieces_have_no_relations_and_live_board_is_not_mutated() -> None:
    board = board_with_backrank_pieces(
        ("b1", chess.Piece(chess.KNIGHT, chess.WHITE)),
        ("c8", chess.Piece(chess.BISHOP, chess.BLACK)),
    )
    tracker = OriginalPieceTracker(board)
    before = board.fen(en_passant="fen")
    relocate(board, tracker, "c8", "b1", ply=1)
    captured = StartingPieceRef.parse("piece:white:knight:queenside").original_piece_id
    analysis_before = board.fen(en_passant="fen")
    facts = PositionAnalyzer().analyze(board, tracker).get(captured)
    assert facts.square is None
    assert not facts.attacks and not facts.attackers
    assert board.fen(en_passant="fen") == analysis_before
    assert before != analysis_before
