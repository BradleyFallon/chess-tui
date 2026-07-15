"""Deterministic engine service for tests and dependency injection."""

from __future__ import annotations

import hashlib

import chess

from .errors import EngineConfigurationError, EngineProcessError, EngineResultError
from .models import AnalysedMove, EngineProfile


class FixtureEngineService:
    """Choose one reproducible legal move without starting a process."""

    def __init__(self, *, session_seed: int | str = 0) -> None:
        self.session_seed = str(session_seed)
        self.closed = False

    async def choose_move(
        self,
        board: chess.Board,
        profile: EngineProfile,
    ) -> chess.Move:
        if self.closed:
            raise EngineProcessError("The fixture engine service is closed.")
        legal_moves = tuple(board.legal_moves)
        if not legal_moves:
            raise EngineResultError("The position has no legal engine move.")
        return self._ranked_moves(board, profile.id)[0]

    async def analyse(
        self,
        board: chess.Board,
        *,
        count: int = 4,
    ) -> tuple[AnalysedMove, ...]:
        if self.closed:
            raise EngineProcessError("The fixture engine service is closed.")
        if not 1 <= count <= 4:
            raise EngineConfigurationError("Analysis count must be between 1 and 4.")
        legal_moves = self._ranked_moves(board, "analysis")
        if not legal_moves:
            raise EngineResultError("The position has no legal moves to analyse.")

        analysed: list[AnalysedMove] = []
        for move in legal_moves[:count]:
            after = board.copy(stack=False)
            san = board.san(move)
            after.push(move)
            outcome = after.outcome(claim_draw=False)
            mate_in: int | None = None
            evaluation_cp: int | None
            if (
                outcome is not None
                and outcome.termination is chess.Termination.CHECKMATE
            ):
                mate_in = 1 if outcome.winner is chess.WHITE else -1
                evaluation_cp = None
            else:
                evaluation_cp = _material_evaluation_cp(after)
            analysed.append(
                AnalysedMove(
                    uci=move.uci(),
                    san=san,
                    evaluation_cp=evaluation_cp,
                    principal_variation=(move.uci(),),
                    mate_in=mate_in,
                )
            )
        return tuple(analysed)

    async def close(self) -> None:
        self.closed = True

    def _ranked_moves(self, board: chess.Board, profile_id: str) -> list[chess.Move]:
        material = f"{board.fen(en_passant='fen')}|{profile_id}|{self.session_seed}"
        return sorted(
            board.legal_moves,
            key=lambda move: hashlib.sha256(
                f"{material}|{move.uci()}".encode("utf-8")
            ).digest(),
        )


def _material_evaluation_cp(board: chess.Board) -> int:
    values = {
        chess.PAWN: 100,
        chess.KNIGHT: 320,
        chess.BISHOP: 330,
        chess.ROOK: 500,
        chess.QUEEN: 900,
        chess.KING: 0,
    }
    return sum(
        (
            len(board.pieces(piece_type, chess.WHITE))
            - len(board.pieces(piece_type, chess.BLACK))
        )
        * value
        for piece_type, value in values.items()
    )
