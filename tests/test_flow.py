from dataclasses import replace
from pathlib import Path

import chess
import pytest

from chess_tui.flow import (
    DevelopmentInstruction,
    FlowStore,
    FlowValidationError,
    InterruptRule,
    MoveAttempt,
    PieceScript,
    Rulebook,
)
from chess_tui.policy import (
    AttackedCondition,
    StartingPieceRef,
)
from chess_tui.policy.runtime import (
    DecisionSource,
    FrontierReason,
    PolicyRuntime,
)


def ref(value: str) -> StartingPieceRef:
    return StartingPieceRef.parse(value)


def development(piece: StartingPieceRef, target: str, *, requires=()):
    return DevelopmentInstruction(
        piece, target, tuple(requires), None, f"Move to {target}."
    )


def rulebook(
    pieces: tuple[PieceScript, ...],
    *,
    development_order: tuple[str, ...] = (),
    interrupt_order: tuple[str, ...] = (),
    start_fen: str = "startpos",
) -> Rulebook:
    return Rulebook(
        version=4,
        name="Test",
        start_fen=start_fen,
        side="white",
        development_order=development_order,
        interrupt_order=interrupt_order,
        pieces=pieces,
    )


def test_london_rulebook_is_v4_and_round_trips() -> None:
    store = FlowStore()
    loaded = store.load(Path("flows/london.toml"))
    assert loaded.version == 4
    assert loaded.development_order[:3] == ("d-pawn", "london-bishop", "e-pawn")
    assert store.decode(store.encode(loaded)) == loaded
    assert "structures" not in store.encode(loaded)
    assert "[[overrides]]" not in store.encode(loaded)


def test_atomic_save_preserves_previous_source_as_backup(tmp_path: Path) -> None:
    store = FlowStore()
    rulebook = store.load(Path("flows/london.toml"))
    path = tmp_path / "rulebook.toml"
    path.write_text("previous source\n", encoding="utf-8")

    store.save(path, rulebook)

    assert path.with_suffix(".toml.bak").read_text(encoding="utf-8") == (
        "previous source\n"
    )
    assert store.load(path) == rulebook
    assert not list(tmp_path.glob(".rulebook.toml.*.tmp"))


def test_version_3_is_rejected_without_compatibility() -> None:
    with pytest.raises(FlowValidationError, match="Version 3 is not accepted"):
        FlowStore().decode(
            'version = 3\nname = "Old"\nstart_fen = "startpos"\n'
            'side = "white"\ndevelopment_order = []\ninterrupt_order = []\n'
            "[pieces]\n"
        )


@pytest.mark.parametrize(
    "source, message",
    [
        (
            'version = 4\nname = "Bad"\nstart_fen = "startpos"\nside = "white"\n'
            "development_order = []\ninterrupt_order = []\nunknown = true\n[pieces]\n",
            "Unknown fields",
        ),
        (
            'version = 4\nname = "Bad"\nstart_fen = "startpos"\nside = "white"\n'
            "development_order = []\ninterrupt_order = []\n"
            '[pieces.p]\nref = "piece:white:pawn:d"\n'
            '[[pieces.p.rules]]\nid = "x"\ntry = []\nwhy = "No."\n',
            "non-empty try",
        ),
    ],
)
def test_strict_schema_rejections(source: str, message: str) -> None:
    with pytest.raises(FlowValidationError, match=message):
        FlowStore().decode(source)


def test_exact_interrupt_precedes_other_interrupts() -> None:
    pawn = ref("piece:white:pawn:d")
    exact = InterruptRule(
        pawn, "exact", (), ("d4", "e5"), None, True, (MoveAttempt("e5"),), "Exact."
    )
    broad = InterruptRule(
        pawn, "broad", (), None, None, False, (MoveAttempt("d5"),), "Broad."
    )
    book = rulebook(
        (PieceScript("d-pawn", pawn, development(pawn, "d4"), (broad, exact)),),
        development_order=("d-pawn",),
        interrupt_order=("d-pawn.broad", "d-pawn.exact"),
    )
    runtime, board = PolicyRuntime.replay(book, ("d4", "e5"))
    decision = runtime.resolve(board)
    assert decision.source is DecisionSource.INTERRUPT
    assert decision.source_id == "d-pawn.exact"
    assert decision.move_san == "dxe5"


def test_interrupt_precedes_development_and_attempts_use_authored_order() -> None:
    knight = ref("piece:white:knight:kingside")
    interrupt = InterruptRule(
        knight,
        "opportunity",
        (),
        None,
        None,
        False,
        (MoveAttempt("h3"), MoveAttempt("f3")),
        "Use first legal attempt.",
    )
    book = rulebook(
        (PieceScript("knight", knight, development(knight, "e2"), (interrupt,)),),
        development_order=("knight",),
        interrupt_order=("knight.opportunity",),
    )
    decision = PolicyRuntime(book).resolve(chess.Board())
    assert decision.source is DecisionSource.INTERRUPT
    assert decision.move_san == "Nh3"
    assert len(decision.interrupt_resolutions[0].attempts) == 1


def test_optional_interrupt_without_action_is_skipped() -> None:
    pawn = ref("piece:white:pawn:d")
    interrupt = InterruptRule(
        pawn, "skip", (), None, None, False, (MoveAttempt("d5"),), "Not legal yet."
    )
    book = rulebook(
        (PieceScript("pawn", pawn, development(pawn, "d4"), (interrupt,)),),
        development_order=("pawn",),
        interrupt_order=("pawn.skip",),
    )
    assert PolicyRuntime(book).resolve(chess.Board()).move_san == "d4"


def test_required_trigger_without_action_returns_typed_frontier() -> None:
    bishop = ref("piece:white:bishop:queenside")
    interrupt = InterruptRule(
        bishop,
        "required",
        (),
        None,
        AttackedCondition("self"),
        True,
        (MoveAttempt("c3"),),
        "Respond.",
    )
    start = "4k3/8/8/8/8/8/2r5/2B1K3 w - - 0 1"
    book = rulebook(
        (PieceScript("bishop", bishop, None, (interrupt,)),),
        interrupt_order=("bishop.required",),
        start_fen=start,
    )
    decision = PolicyRuntime(book).resolve(chess.Board(start))
    assert decision.frontier_reason is FrontierReason.UNHANDLED_REQUIRED_RULE


def test_illegal_earlier_development_allows_later_legal_instruction() -> None:
    bishop = ref("piece:white:bishop:queenside")
    pawn = ref("piece:white:pawn:d")
    book = rulebook(
        (
            PieceScript("bishop", bishop, development(bishop, "f4"), ()),
            PieceScript("pawn", pawn, development(pawn, "d4"), ()),
        ),
        development_order=("bishop", "pawn"),
    )
    decision = PolicyRuntime(book).resolve(chess.Board())
    assert decision.source_id == "pawn.develop"
    assert decision.development_resolutions[0].status.value == "waiting-for-legality"


def test_prerequisites_and_captured_undeveloped_do_not_complete_development() -> None:
    bishop = ref("piece:white:bishop:queenside")
    pawn = ref("piece:white:pawn:d")
    start = "4k3/8/8/8/8/8/3P4/2B1K3 w - - 0 1"
    book = rulebook(
        (
            PieceScript("pawn", pawn, development(pawn, "d4"), ()),
            PieceScript(
                "bishop",
                bishop,
                development(bishop, "f4", requires=("pawn.develop",)),
                (),
            ),
        ),
        development_order=("pawn", "bishop"),
        start_fen=start,
    )
    runtime, board = PolicyRuntime.replay(book, ("d4", "Kf7"))
    assert runtime.resolve(board).source_id == "bishop.develop"


def test_interrupt_move_completes_development_and_is_one_shot() -> None:
    knight = ref("piece:white:knight:kingside")
    interrupt = InterruptRule(
        knight, "first", (), None, None, False, (MoveAttempt("h3"),), "Move."
    )
    book = rulebook(
        (PieceScript("knight", knight, development(knight, "f3"), (interrupt,)),),
        development_order=("knight",),
        interrupt_order=("knight.first",),
    )
    runtime, board = PolicyRuntime.replay(book, ("Nh3", "a6"))
    assert "knight.first" in runtime.completed_interrupts
    assert runtime.resolve(board).frontier_reason is FrontierReason.DEVELOPMENT_COMPLETE


def test_no_authored_legal_move_frontier() -> None:
    bishop = ref("piece:white:bishop:queenside")
    book = rulebook(
        (PieceScript("bishop", bishop, development(bishop, "f4"), ()),),
        development_order=("bishop",),
    )
    decision = PolicyRuntime(book).resolve(chess.Board())
    assert decision.frontier_reason is FrontierReason.NO_AUTHORED_LEGAL_MOVE


def test_dependency_cycles_and_incomplete_orders_are_rejected() -> None:
    pawn = ref("piece:white:pawn:d")
    book = rulebook(
        (
            PieceScript(
                "pawn",
                pawn,
                DevelopmentInstruction(pawn, "d4", ("pawn.rule",), None, "Develop."),
                (
                    InterruptRule(
                        pawn,
                        "rule",
                        ("pawn.develop",),
                        None,
                        None,
                        False,
                        (MoveAttempt("d4"),),
                        "Rule.",
                    ),
                ),
            ),
        ),
        development_order=("pawn",),
        interrupt_order=("pawn.rule",),
    )
    with pytest.raises(FlowValidationError, match="cycle"):
        FlowStore().validate(book)
    with pytest.raises(FlowValidationError, match="interrupt_order"):
        FlowStore().validate(replace(book, interrupt_order=()))
