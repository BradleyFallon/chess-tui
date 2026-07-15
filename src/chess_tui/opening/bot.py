"""Deterministic all-position bot used before an engine integration exists."""

from __future__ import annotations

import hashlib

import chess

from ..flow import normalized_position_key
from .models import MoveSuggestion, SuggestionKind


class FixtureBotMoveSource:
    """Rank legal moves reproducibly from position, profile, and session seed."""

    def __init__(
        self,
        *,
        profile_id: str = "prototype",
        session_seed: int | str = 0,
        suggestion_count: int = 4,
    ) -> None:
        if not profile_id.strip():
            raise ValueError("profile_id cannot be empty.")
        if not 1 <= suggestion_count <= 4:
            raise ValueError("suggestion_count must be between 1 and 4.")
        self.profile_id = profile_id
        self.session_seed = str(session_seed)
        self.suggestion_count = suggestion_count

    async def moves_for(self, board: chess.Board) -> tuple[MoveSuggestion, ...]:
        material = "|".join(
            (
                normalized_position_key(board),
                self.profile_id,
                self.session_seed,
            )
        )
        legal_moves = sorted(board.legal_moves, key=lambda move: move.uci())
        ranked_moves = sorted(
            legal_moves,
            key=lambda move: hashlib.sha256(
                f"{material}|{move.uci()}".encode("utf-8")
            ).digest(),
        )
        label = f"DETERMINISTIC {self.profile_id.upper()}"
        return tuple(
            MoveSuggestion(
                uci=move.uci(),
                san=board.san(move),
                kind=SuggestionKind.BOT,
                label=label,
                profile_id=self.profile_id,
            )
            for move in ranked_moves[: self.suggestion_count]
        )

    async def close(self) -> None:
        return None
