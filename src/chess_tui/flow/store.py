"""Strict TOML loading and failure-safe persistence for White flows."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any

import chess

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 compatibility
    import tomli as tomllib  # pyright: ignore[reportMissingImports]

from .errors import FlowStorageError, FlowValidationError
from .models import DefaultRule, ExceptionRule, OpponentReply, WhiteFlow
from .position import normalized_position_key, parse_legal_san, replay_san

SUPPORTED_VERSION = 1


class FlowStore:
    def load(self, path: Path) -> WhiteFlow:
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise FlowStorageError(f"Flow file does not exist: {path}") from exc
        except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
            raise FlowStorageError(f"Could not read flow {path}: {exc}") from exc
        try:
            flow = self._decode(data)
            self.validate(flow)
        except (KeyError, TypeError, ValueError, FlowValidationError) as exc:
            if isinstance(exc, FlowValidationError):
                raise
            raise FlowValidationError(f"Invalid flow {path}: {exc}") from exc
        return flow

    def save(self, path: Path, flow: WhiteFlow) -> None:
        self.validate(flow)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                temporary.write(_encode(flow))
                temporary.flush()
                os.fsync(temporary.fileno())
                temporary_path = Path(temporary.name)

            validated = self.load(temporary_path)
            if validated != flow:
                raise FlowStorageError("Temporary flow validation changed its data.")
            if path.exists():
                shutil.copy2(path, path.with_suffix(path.suffix + ".bak"))
            os.replace(temporary_path, path)
            temporary_path = None
        except (OSError, FlowValidationError) as exc:
            raise FlowStorageError(f"Could not save flow {path}: {exc}") from exc
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    def replace_default(
        self,
        path: Path,
        step: int,
        move_san: str,
        note: str | None,
    ) -> WhiteFlow:
        flow = self.load(path)
        replacement = DefaultRule(step, move_san, note)
        defaults = [rule for rule in flow.defaults if rule.step != step]
        defaults.append(replacement)
        updated = WhiteFlow(
            flow.version,
            flow.name,
            flow.start_fen,
            tuple(sorted(defaults, key=lambda rule: rule.step)),
            flow.exceptions,
            flow.opponent_replies,
        )
        self.save(path, updated)
        return updated

    def add_exception(self, path: Path, exception: ExceptionRule) -> WhiteFlow:
        flow = self.load(path)
        target_board = replay_san(flow.start_fen, exception.after_san)
        target_key = normalized_position_key(target_board)
        exceptions = []
        for existing in flow.exceptions:
            existing_board = replay_san(flow.start_fen, existing.after_san)
            if existing.id == exception.id:
                continue
            if normalized_position_key(existing_board) == target_key:
                continue
            exceptions.append(existing)
        exceptions.append(exception)
        updated = WhiteFlow(
            flow.version,
            flow.name,
            flow.start_fen,
            flow.defaults,
            tuple(exceptions),
            flow.opponent_replies,
        )
        self.save(path, updated)
        return updated

    def remove_exception(self, path: Path, exception_id: str) -> WhiteFlow:
        flow = self.load(path)
        exceptions = tuple(
            exception for exception in flow.exceptions if exception.id != exception_id
        )
        if len(exceptions) == len(flow.exceptions):
            raise FlowValidationError(f"Unknown exception id: {exception_id!r}.")
        updated = WhiteFlow(
            flow.version,
            flow.name,
            flow.start_fen,
            flow.defaults,
            exceptions,
            flow.opponent_replies,
        )
        self.save(path, updated)
        return updated

    def add_opponent_reply(self, path: Path, reply: OpponentReply) -> WhiteFlow:
        flow = self.load(path)
        target_board = replay_san(flow.start_fen, reply.after_san)
        target_key = normalized_position_key(target_board)
        target_move = parse_legal_san(
            target_board,
            reply.move_san,
            context=f"Opponent reply {reply.id!r}",
        )
        replies: list[OpponentReply] = []
        for existing in flow.opponent_replies:
            existing_board = replay_san(flow.start_fen, existing.after_san)
            existing_move = parse_legal_san(
                existing_board,
                existing.move_san,
                context=f"Opponent reply {existing.id!r}",
            )
            same_branch = (
                normalized_position_key(existing_board) == target_key
                and existing_move == target_move
            )
            if existing.id == reply.id or same_branch:
                continue
            replies.append(existing)
        replies.append(reply)
        updated = WhiteFlow(
            flow.version,
            flow.name,
            flow.start_fen,
            flow.defaults,
            flow.exceptions,
            tuple(replies),
        )
        if updated == flow:
            return flow
        self.save(path, updated)
        return updated

    def validate(self, flow: WhiteFlow) -> None:
        if flow.version != SUPPORTED_VERSION:
            raise FlowValidationError(
                f"Unsupported flow version {flow.version}; expected {SUPPORTED_VERSION}."
            )
        if not flow.name.strip():
            raise FlowValidationError("Flow name cannot be empty.")
        try:
            start = chess.Board(flow.start_fen)
        except ValueError as exc:
            raise FlowValidationError(f"Invalid start_fen: {exc}") from exc
        if start.turn is not chess.WHITE:
            raise FlowValidationError("A White flow must start with White to move.")

        expected_steps = tuple(range(1, len(flow.defaults) + 1))
        actual_steps = tuple(rule.step for rule in flow.defaults)
        if actual_steps != expected_steps:
            raise FlowValidationError(
                "Default steps must start at 1 and be consecutive."
            )
        for rule in flow.defaults:
            _validate_rule_text(rule.move_san, rule.note, f"Default step {rule.step}")
        if flow.defaults and not _has_legal_default_line(start, flow.defaults):
            raise FlowValidationError(
                "The numbered defaults do not have a legal realization through "
                "possible Black replies."
            )

        ids: set[str] = set()
        positions: set[str] = set()
        for exception in flow.exceptions:
            if not exception.id.strip() or exception.id in ids:
                raise FlowValidationError(
                    f"Exception ids must be non-empty and unique: {exception.id!r}."
                )
            ids.add(exception.id)
            _validate_rule_text(
                exception.move_san,
                exception.note,
                f"Exception {exception.id!r}",
            )
            board = replay_san(
                flow.start_fen,
                exception.after_san,
                context=f"Exception {exception.id!r}",
            )
            expected_step = (len(exception.after_san) // 2) + 1
            if board.turn is not chess.WHITE or exception.step != expected_step:
                raise FlowValidationError(
                    f"Exception {exception.id!r} must target White step {expected_step}."
                )
            parse_legal_san(
                board,
                exception.move_san,
                context=f"Exception {exception.id!r}",
            )
            key = normalized_position_key(board)
            if key in positions:
                raise FlowValidationError(
                    f"Exception {exception.id!r} duplicates a normalized position."
                )
            positions.add(key)

        reply_ids: set[str] = set()
        explored_branches: set[tuple[str, str]] = set()
        for reply in flow.opponent_replies:
            if not reply.id.strip() or reply.id in reply_ids:
                raise FlowValidationError(
                    f"Opponent reply ids must be non-empty and unique: {reply.id!r}."
                )
            reply_ids.add(reply.id)
            _validate_rule_text(
                reply.move_san,
                reply.note,
                f"Opponent reply {reply.id!r}",
            )
            board = replay_san(
                flow.start_fen,
                reply.after_san,
                context=f"Opponent reply {reply.id!r}",
            )
            if board.turn is not chess.BLACK:
                raise FlowValidationError(
                    f"Opponent reply {reply.id!r} must target Black to move."
                )
            move = parse_legal_san(
                board,
                reply.move_san,
                context=f"Opponent reply {reply.id!r}",
            )
            branch = (normalized_position_key(board), move.uci())
            if branch in explored_branches:
                raise FlowValidationError(
                    f"Opponent reply {reply.id!r} duplicates an explored branch."
                )
            explored_branches.add(branch)

    def _decode(self, data: dict[str, Any]) -> WhiteFlow:
        _require_keys(
            data,
            {
                "version",
                "name",
                "start_fen",
                "defaults",
                "exceptions",
                "opponent_replies",
            },
        )
        defaults_data = data.get("defaults", [])
        exceptions_data = data.get("exceptions", [])
        replies_data = data.get("opponent_replies", [])
        if not all(
            isinstance(items, list)
            for items in (defaults_data, exceptions_data, replies_data)
        ):
            raise TypeError(
                "defaults, exceptions, and opponent_replies must be arrays of tables"
            )
        defaults = tuple(self._decode_default(item) for item in defaults_data)
        exceptions = tuple(self._decode_exception(item) for item in exceptions_data)
        replies = tuple(self._decode_opponent_reply(item) for item in replies_data)
        return WhiteFlow(
            version=_integer(data, "version"),
            name=_string(data, "name"),
            start_fen=_string(data, "start_fen"),
            defaults=defaults,
            exceptions=exceptions,
            opponent_replies=replies,
        )

    def _decode_default(self, data: object) -> DefaultRule:
        mapping = _mapping(data, "default")
        _require_keys(mapping, {"step", "move", "note"})
        return DefaultRule(
            _integer(mapping, "step"),
            _string(mapping, "move"),
            _optional_string(mapping, "note"),
        )

    def _decode_exception(self, data: object) -> ExceptionRule:
        mapping = _mapping(data, "exception")
        _require_keys(mapping, {"id", "step", "after", "move", "note"})
        after = mapping.get("after")
        if not isinstance(after, list) or not all(
            isinstance(item, str) for item in after
        ):
            raise TypeError("exception after must be an array of strings")
        return ExceptionRule(
            _string(mapping, "id"),
            _integer(mapping, "step"),
            tuple(after),
            _string(mapping, "move"),
            _optional_string(mapping, "note"),
        )

    def _decode_opponent_reply(self, data: object) -> OpponentReply:
        mapping = _mapping(data, "opponent reply")
        _require_keys(mapping, {"id", "after", "move", "note"})
        after = mapping.get("after")
        if not isinstance(after, list) or not all(
            isinstance(item, str) for item in after
        ):
            raise TypeError("opponent reply after must be an array of strings")
        return OpponentReply(
            _string(mapping, "id"),
            tuple(after),
            _string(mapping, "move"),
            _optional_string(mapping, "note"),
        )


def _encode(flow: WhiteFlow) -> str:
    lines = [
        f"version = {flow.version}",
        f"name = {json.dumps(flow.name)}",
        f"start_fen = {json.dumps(flow.start_fen)}",
    ]
    for rule in flow.defaults:
        lines.extend(
            (
                "",
                "[[defaults]]",
                f"step = {rule.step}",
                f"move = {json.dumps(rule.move_san)}",
            )
        )
        if rule.note is not None:
            lines.append(f"note = {json.dumps(rule.note)}")
    for rule in flow.exceptions:
        lines.extend(
            (
                "",
                "[[exceptions]]",
                f"id = {json.dumps(rule.id)}",
                f"step = {rule.step}",
                f"after = {json.dumps(list(rule.after_san))}",
                f"move = {json.dumps(rule.move_san)}",
            )
        )
        if rule.note is not None:
            lines.append(f"note = {json.dumps(rule.note)}")
    for reply in flow.opponent_replies:
        lines.extend(
            (
                "",
                "[[opponent_replies]]",
                f"id = {json.dumps(reply.id)}",
                f"after = {json.dumps(list(reply.after_san))}",
                f"move = {json.dumps(reply.move_san)}",
            )
        )
        if reply.note is not None:
            lines.append(f"note = {json.dumps(reply.note)}")
    return "\n".join(lines) + "\n"


def _validate_rule_text(move_san: str, note: str | None, context: str) -> None:
    if not move_san.strip():
        raise FlowValidationError(f"{context} move cannot be empty.")
    if note is not None and not isinstance(note, str):
        raise FlowValidationError(f"{context} note must be a string.")


def _mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError(f"{label} must be a table")
    return value


def _require_keys(mapping: dict[str, Any], allowed: set[str]) -> None:
    unknown = set(mapping) - allowed
    if unknown:
        raise ValueError(f"Unknown fields: {sorted(unknown)}")


def _string(mapping: dict[str, Any], key: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str):
        raise TypeError(f"{key} must be a string")
    return value


def _optional_string(mapping: dict[str, Any], key: str) -> str | None:
    value = mapping.get(key)
    if value is not None and not isinstance(value, str):
        raise TypeError(f"{key} must be a string when present")
    return value


def _integer(mapping: dict[str, Any], key: str) -> int:
    value = mapping.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{key} must be an integer")
    return value


def _has_legal_default_line(
    board: chess.Board,
    defaults: tuple[DefaultRule, ...],
    index: int = 0,
) -> bool:
    if index >= len(defaults):
        return True
    try:
        white_move = board.parse_san(defaults[index].move_san)
    except ValueError:
        return False
    after_white = board.copy(stack=False)
    after_white.push(white_move)
    if index == len(defaults) - 1:
        return True
    for black_move in after_white.legal_moves:
        after_black = after_white.copy(stack=False)
        after_black.push(black_move)
        if _has_legal_default_line(after_black, defaults, index + 1):
            return True
    return False
