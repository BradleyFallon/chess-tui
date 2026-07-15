"""Structured, White-normalized move grading."""

from __future__ import annotations

import chess

from .errors import EngineResultError
from .models import (
    DEFAULT_QUALITY_THRESHOLDS,
    AnalysedMove,
    MoveAssessment,
    MoveQuality,
    QualityThresholds,
)
from .service import ChessEngineService


async def assess_white_move(
    engine: ChessEngineService,
    board: chess.Board,
    played_move: chess.Move,
    *,
    thresholds: QualityThresholds = DEFAULT_QUALITY_THRESHOLDS,
) -> MoveAssessment:
    """Grade one legal White move against best play from the same position."""

    if board.turn is not chess.WHITE:
        raise EngineResultError("White move assessment requires White to move.")
    if played_move not in board.legal_moves:
        raise EngineResultError(
            f"Cannot assess illegal White move {played_move.uci()!r}."
        )

    before = _require_line(await engine.analyse(board, count=1), "before")
    after_board = board.copy(stack=False)
    after_board.push(played_move)
    after = await _analyse_after(engine, after_board)

    loss_cp: int | None = None
    if before.evaluation_cp is not None and after.evaluation_cp is not None:
        loss_cp = max(0, before.evaluation_cp - after.evaluation_cp)
        quality = quality_for_loss(loss_cp, thresholds)
    else:
        quality = _mate_quality(before, after)

    return MoveAssessment(
        played_uci=played_move.uci(),
        best_uci=before.uci,
        evaluation_before_cp=before.evaluation_cp,
        evaluation_after_cp=after.evaluation_cp,
        loss_cp=loss_cp,
        quality=quality,
        mate_before=before.mate_in,
        mate_after=after.mate_in,
    )


def quality_for_loss(
    loss_cp: int,
    thresholds: QualityThresholds = DEFAULT_QUALITY_THRESHOLDS,
) -> MoveQuality:
    if loss_cp < 0:
        raise ValueError("Centipawn loss cannot be negative.")
    if loss_cp <= thresholds.best_max_cp:
        return MoveQuality.BEST
    if loss_cp <= thresholds.good_max_cp:
        return MoveQuality.GOOD
    if loss_cp <= thresholds.inaccuracy_max_cp:
        return MoveQuality.INACCURACY
    if loss_cp <= thresholds.mistake_max_cp:
        return MoveQuality.MISTAKE
    return MoveQuality.BLUNDER


async def _analyse_after(
    engine: ChessEngineService,
    board: chess.Board,
) -> AnalysedMove:
    outcome = board.outcome(claim_draw=False)
    if outcome is None:
        return _require_line(await engine.analyse(board, count=1), "after")
    if outcome.termination is chess.Termination.CHECKMATE:
        mate = 0 if outcome.winner is chess.WHITE else -1
        return AnalysedMove("", "", None, (), mate_in=mate)
    return AnalysedMove("", "", 0, ())


def _require_line(
    lines: tuple[AnalysedMove, ...],
    context: str,
) -> AnalysedMove:
    if not lines:
        raise EngineResultError(f"Engine returned no {context}-move analysis.")
    return lines[0]


def _mate_quality(before: AnalysedMove, after: AnalysedMove) -> MoveQuality:
    before_mate = before.mate_in
    after_mate = after.mate_in
    if after_mate is not None and after_mate < 0:
        return MoveQuality.BLUNDER
    if before_mate is not None and before_mate > 0:
        if after_mate is None or after_mate <= 0:
            return MoveQuality.BLUNDER
        return MoveQuality.BEST if after_mate <= before_mate else MoveQuality.GOOD
    if after_mate is not None and after_mate >= 0:
        return MoveQuality.BEST
    return MoveQuality.GOOD
