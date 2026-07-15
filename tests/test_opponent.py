from __future__ import annotations

import asyncio
from pathlib import Path

import chess

from chess_tui import DEFAULT_STARTING_FEN
from chess_tui.flow import FlowStore, WhiteFlow, WhiteFlowAuthor
from chess_tui.opening import (
    FixtureBotMoveSource,
    FixtureOpeningMoveSource,
    OpponentMovePlanner,
    SuggestionKind,
)


async def _play_route(
    path: Path,
    *,
    session_seed: int,
    max_plies: int = 30,
) -> tuple[tuple[str, ...], tuple[str, ...], bool]:
    author = WhiteFlowAuthor(path)
    planner = OpponentMovePlanner(
        FixtureOpeningMoveSource(),
        FixtureBotMoveSource(session_seed=session_seed),
    )
    board = chess.Board(author.flow.start_fen)
    history: list[str] = []
    black_moves: list[str] = []

    try:
        while len(history) < max_plies and not board.is_game_over():
            if board.turn is chess.WHITE:
                move = (
                    board.parse_san("d4")
                    if not history
                    else sorted(board.legal_moves, key=lambda item: item.uci())[0]
                )
            else:
                suggestions = await planner.suggestions_for(board)
                assert suggestions
                assert all(
                    chess.Move.from_uci(suggestion.uci) in board.legal_moves
                    for suggestion in suggestions
                )
                selected = suggestions[0]
                move = chess.Move.from_uci(selected.uci)
                author.record_opponent_reply(
                    board,
                    tuple(history),
                    selected.san,
                )
                black_moves.append(selected.san)

            san = board.san(move)
            board.push(move)
            history.append(san)
    finally:
        await planner.close()

    return tuple(history), tuple(black_moves), board.is_game_over()


def _empty_flow(path: Path) -> None:
    FlowStore().save(
        path,
        WhiteFlow(1, "Deep opponent route", DEFAULT_STARTING_FEN, (), ()),
    )


def test_book_to_bot_route_is_deep_deterministic_and_persisted(
    tmp_path: Path,
) -> None:
    path = tmp_path / "route.toml"
    _empty_flow(path)

    first_history, first_black, game_over = asyncio.run(
        _play_route(path, session_seed=17)
    )
    saved = FlowStore().load(path)

    assert len(first_history) == 30 or game_over
    assert first_black[0] == "d5"
    assert len(saved.opponent_replies) == len(first_black)
    encoded = path.read_text(encoding="utf-8")
    assert "prototype" not in encoded.lower()
    assert "book" not in encoded.lower()
    assert "frequency" not in encoded.lower()

    repeated_history, repeated_black, _ = asyncio.run(
        _play_route(path, session_seed=17)
    )
    assert repeated_history == first_history
    assert repeated_black == first_black
    assert len(FlowStore().load(path).opponent_replies) == len(first_black)

    alternate_path = tmp_path / "alternate.toml"
    _empty_flow(alternate_path)
    alternate_history, alternate_black, _ = asyncio.run(
        _play_route(alternate_path, session_seed=18)
    )
    assert alternate_history != first_history
    assert alternate_black != first_black


def test_deep_route_transitions_from_book_to_bot() -> None:
    async def run_test() -> None:
        planner = OpponentMovePlanner(
            FixtureOpeningMoveSource(),
            FixtureBotMoveSource(session_seed=17),
        )
        book_board = chess.Board()
        book_board.push_san("d4")
        book = await planner.suggestions_for(book_board)
        assert book[0].kind is SuggestionKind.BOOK

        book_board.push_san(book[0].san)
        book_board.push_san("a3")
        bot = await planner.suggestions_for(book_board)
        assert bot
        assert all(suggestion.kind is SuggestionKind.BOT for suggestion in bot)
        await planner.close()

    asyncio.run(run_test())
