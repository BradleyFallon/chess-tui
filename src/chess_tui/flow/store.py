"""Strict TOML loading and failure-safe persistence for v2 flows."""

from __future__ import annotations

from dataclasses import replace
import json
import os
from pathlib import Path
import shutil
import tempfile
from collections.abc import Mapping
from typing import Any

import chess

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 compatibility
    import tomli as tomllib  # pyright: ignore[reportMissingImports]

from ..policy import (
    MoveAction,
    OriginalPieceId,
    OriginalPieceTracker,
    condition_to_data,
    parse_condition,
    referenced_pieces,
    referenced_states,
)
from .errors import FlowStorageError, FlowValidationError
from .models import ExactOverride, Flow, NamedState, OpponentReply, PolicyRule
from .position import normalized_position_key, parse_legal_san, replay_san

SUPPORTED_VERSION = 2


class FlowStore:
    def load(self, path: Path) -> Flow:
        try:
            return self.decode(path.read_text(encoding="utf-8"), context=str(path))
        except FileNotFoundError as exc:
            raise FlowStorageError(f"Flow file does not exist: {path}") from exc
        except (OSError, UnicodeError) as exc:
            raise FlowStorageError(f"Could not read flow {path}: {exc}") from exc

    def decode(self, source: str, *, context: str = "flow") -> Flow:
        try:
            data = tomllib.loads(source)
            flow = self._decode(data)
            self.validate(flow)
            return flow
        except tomllib.TOMLDecodeError as exc:
            raise FlowValidationError(f"Invalid TOML in {context}: {exc}") from exc
        except (KeyError, TypeError, ValueError, FlowValidationError) as exc:
            if isinstance(exc, FlowValidationError):
                raise
            raise FlowValidationError(f"Invalid {context}: {exc}") from exc

    def encode(self, flow: Flow) -> str:
        self.validate(flow)
        return _encode(flow)

    def save(self, path: Path, flow: Flow) -> None:
        source = self.encode(flow)
        if self.decode(source, context="serialized flow") != flow:
            raise FlowStorageError("Serialized flow validation changed its data.")
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
                temporary.write(source)
                temporary.flush()
                os.fsync(temporary.fileno())
                temporary_path = Path(temporary.name)
            if path.exists():
                shutil.copy2(path, path.with_suffix(path.suffix + ".bak"))
            os.replace(temporary_path, path)
            temporary_path = None
        except OSError as exc:
            raise FlowStorageError(f"Could not save flow {path}: {exc}") from exc
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    def replace_rule(self, path: Path, replacement: PolicyRule) -> Flow:
        flow = self.load(path)
        if all(rule.id != replacement.id for rule in flow.rules):
            raise FlowValidationError(f"Unknown rule id: {replacement.id!r}.")
        updated = replace(
            flow,
            rules=tuple(
                replacement if rule.id == replacement.id else rule
                for rule in flow.rules
            ),
        )
        self.save(path, updated)
        return updated

    def replace_override(self, path: Path, replacement: ExactOverride) -> Flow:
        flow = self.load(path)
        if all(item.id != replacement.id for item in flow.overrides):
            raise FlowValidationError(f"Unknown override id: {replacement.id!r}.")
        updated = replace(
            flow,
            overrides=tuple(
                replacement if item.id == replacement.id else item
                for item in flow.overrides
            ),
        )
        self.save(path, updated)
        return updated

    def add_opponent_reply(self, path: Path, reply: OpponentReply) -> Flow:
        flow = self.load(path)
        target = replay_san(_expanded_fen(flow.start_fen), reply.after_san)
        target_move = parse_legal_san(target, reply.move_san, context="Opponent reply")
        branch = (normalized_position_key(target), target_move.uci())
        retained: list[OpponentReply] = []
        for existing in flow.opponent_replies:
            board = replay_san(_expanded_fen(flow.start_fen), existing.after_san)
            move = parse_legal_san(board, existing.move_san, context="Opponent reply")
            existing_branch = (normalized_position_key(board), move.uci())
            if existing_branch == branch:
                # Playing an already-authored branch must not rewrite the file or
                # move that branch to the end of its presentation order.
                return flow
            if existing.id != reply.id:
                retained.append(existing)
        retained.append(reply)
        updated = replace(flow, opponent_replies=tuple(retained))
        if updated != flow:
            self.save(path, updated)
        return updated

    def validate(self, flow: Flow) -> None:
        if flow.version != SUPPORTED_VERSION:
            raise FlowValidationError(
                f"Unsupported flow version {flow.version}; expected {SUPPORTED_VERSION}."
            )
        if not flow.name.strip():
            raise FlowValidationError("Flow name cannot be empty.")
        if flow.side not in {"white", "black"}:
            raise FlowValidationError(f"Invalid controlled side: {flow.side!r}.")
        try:
            start = chess.Board(_expanded_fen(flow.start_fen))
        except ValueError as exc:
            raise FlowValidationError(f"Invalid start_fen: {exc}") from exc
        controlled = chess.WHITE if flow.side == "white" else chess.BLACK
        if start.turn != controlled:
            raise FlowValidationError(
                f"start_fen must have the controlled side ({flow.side}) to move."
            )
        tracker = OriginalPieceTracker(start)

        state_ids = _unique_ids((state.id for state in flow.states), "state")
        state_map = {state.id: state.when for state in flow.states}
        for state in flow.states:
            _validate_condition_references(
                state.when, tracker, state_ids, f"State {state.id!r}"
            )
        _validate_state_cycles(state_map)

        _unique_ids((rule.id for rule in flow.rules), "rule")
        priorities: set[int] = set()
        for rule in flow.rules:
            if isinstance(rule.priority, bool) or rule.priority in priorities:
                raise FlowValidationError(
                    f"Rule priorities must be unique; duplicate {rule.priority}."
                )
            priorities.add(rule.priority)
            _validate_note(rule.note, f"Rule {rule.id!r}")
            _validate_action(rule.move, tracker, flow.side, f"Rule {rule.id!r}")
            for label, condition in (
                ("activation", rule.activate_when),
                ("retirement", rule.retire_when),
            ):
                if condition is not None:
                    _validate_condition_references(
                        condition,
                        tracker,
                        state_ids,
                        f"Rule {rule.id!r} {label}",
                    )

        _unique_ids((item.id for item in flow.overrides), "override")
        override_positions: set[str] = set()
        for override in flow.overrides:
            _validate_note(override.note, f"Override {override.id!r}")
            _validate_action(
                override.move, tracker, flow.side, f"Override {override.id!r}"
            )
            board, history_tracker = _replay_with_tracker(
                start, override.after_san, f"Override {override.id!r}"
            )
            if board.turn != controlled:
                raise FlowValidationError(
                    f"Override {override.id!r} must target {flow.side} to move."
                )
            key = normalized_position_key(board)
            if key in override_positions:
                raise FlowValidationError(
                    f"Override {override.id!r} duplicates a normalized position."
                )
            override_positions.add(key)
            _validate_action_legal(
                board, history_tracker, override.move, f"Override {override.id!r}"
            )

        _unique_ids((reply.id for reply in flow.opponent_replies), "opponent reply")
        branches: set[tuple[str, str]] = set()
        for reply in flow.opponent_replies:
            _validate_note(reply.note, f"Opponent reply {reply.id!r}")
            board = replay_san(
                _expanded_fen(flow.start_fen),
                reply.after_san,
                context=f"Opponent reply {reply.id!r}",
            )
            if board.turn == controlled:
                raise FlowValidationError(
                    f"Opponent reply {reply.id!r} must target the opponent to move."
                )
            move = parse_legal_san(
                board, reply.move_san, context=f"Opponent reply {reply.id!r}"
            )
            branch = (normalized_position_key(board), move.uci())
            if branch in branches:
                raise FlowValidationError(
                    f"Opponent reply {reply.id!r} duplicates an explored branch."
                )
            branches.add(branch)

    def _decode(self, data: dict[str, Any]) -> Flow:
        _require_keys(
            data,
            {
                "version",
                "name",
                "start_fen",
                "side",
                "states",
                "rules",
                "overrides",
                "opponent_replies",
            },
        )
        collections = {
            key: data.get(key, [])
            for key in ("states", "rules", "overrides", "opponent_replies")
        }
        if not all(isinstance(value, list) for value in collections.values()):
            raise TypeError(
                "states, rules, overrides, and opponent_replies must be arrays of tables"
            )
        side = _string(data, "side")
        if side not in {"white", "black"}:
            raise ValueError("side must be 'white' or 'black'")
        return Flow(
            version=_integer(data, "version"),
            name=_string(data, "name"),
            start_fen=_string(data, "start_fen"),
            side=side,  # type: ignore[arg-type]
            states=tuple(self._decode_state(item) for item in collections["states"]),
            rules=tuple(self._decode_rule(item) for item in collections["rules"]),
            overrides=tuple(
                self._decode_override(item) for item in collections["overrides"]
            ),
            opponent_replies=tuple(
                self._decode_reply(item) for item in collections["opponent_replies"]
            ),
        )

    def _decode_state(self, value: object) -> NamedState:
        item = _mapping(value, "state")
        _require_keys(item, {"id", "when"})
        return NamedState(
            _string(item, "id"), parse_condition(item.get("when"), context="state.when")
        )

    def _decode_rule(self, value: object) -> PolicyRule:
        item = _mapping(value, "rule")
        _require_keys(
            item,
            {
                "id",
                "priority",
                "enabled",
                "note",
                "move",
                "activate_when",
                "retire_when",
            },
        )
        return PolicyRule(
            id=_string(item, "id"),
            priority=_integer(item, "priority"),
            move=_decode_action(item.get("move"), "rule.move"),
            enabled=_boolean(item, "enabled", True),
            note=_optional_string(item, "note"),
            activate_when=(
                parse_condition(item["activate_when"], context="rule.activate_when")
                if "activate_when" in item
                else None
            ),
            retire_when=(
                parse_condition(item["retire_when"], context="rule.retire_when")
                if "retire_when" in item
                else None
            ),
        )

    def _decode_override(self, value: object) -> ExactOverride:
        item = _mapping(value, "override")
        _require_keys(item, {"id", "after", "enabled", "note", "move"})
        return ExactOverride(
            id=_string(item, "id"),
            after_san=_string_tuple(item.get("after"), "override.after"),
            move=_decode_action(item.get("move"), "override.move"),
            enabled=_boolean(item, "enabled", True),
            note=_optional_string(item, "note"),
        )

    def _decode_reply(self, value: object) -> OpponentReply:
        item = _mapping(value, "opponent reply")
        _require_keys(item, {"id", "after", "move", "note"})
        return OpponentReply(
            _string(item, "id"),
            _string_tuple(item.get("after"), "opponent_reply.after"),
            _string(item, "move"),
            _optional_string(item, "note"),
        )


def _encode(flow: Flow) -> str:
    lines = [
        f"version = {flow.version}",
        f"name = {json.dumps(flow.name)}",
        f"start_fen = {json.dumps(flow.start_fen)}",
        f"side = {json.dumps(flow.side)}",
    ]
    for state in flow.states:
        lines.extend(
            (
                "",
                "[[states]]",
                f"id = {json.dumps(state.id)}",
                f"when = {_toml_value(condition_to_data(state.when))}",
            )
        )
    for rule in flow.rules:
        lines.extend(
            (
                "",
                "[[rules]]",
                f"id = {json.dumps(rule.id)}",
                f"priority = {rule.priority}",
            )
        )
        if not rule.enabled:
            lines.append("enabled = false")
        if rule.note is not None:
            lines.append(f"note = {json.dumps(rule.note)}")
        lines.append(f"move = {_encode_action(rule.move)}")
        if rule.activate_when is not None:
            lines.append(
                f"activate_when = {_toml_value(condition_to_data(rule.activate_when))}"
            )
        if rule.retire_when is not None:
            lines.append(
                f"retire_when = {_toml_value(condition_to_data(rule.retire_when))}"
            )
    for override in flow.overrides:
        lines.extend(
            (
                "",
                "[[overrides]]",
                f"id = {json.dumps(override.id)}",
                f"after = {_toml_value(list(override.after_san))}",
            )
        )
        if not override.enabled:
            lines.append("enabled = false")
        if override.note is not None:
            lines.append(f"note = {json.dumps(override.note)}")
        lines.append(f"move = {_encode_action(override.move)}")
    for reply in flow.opponent_replies:
        lines.extend(
            (
                "",
                "[[opponent_replies]]",
                f"id = {json.dumps(reply.id)}",
                f"after = {_toml_value(list(reply.after_san))}",
                f"move = {json.dumps(reply.move_san)}",
            )
        )
        if reply.note is not None:
            lines.append(f"note = {json.dumps(reply.note)}")
    return "\n".join(lines) + "\n"


def _toml_value(value: object) -> str:
    if isinstance(value, dict):
        return (
            "{ "
            + ", ".join(f"{key} = {_toml_value(item)}" for key, item in value.items())
            + " }"
        )
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(item) for item in value) + "]"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        return json.dumps(value)
    raise TypeError(f"Cannot encode TOML value {value!r}.")


def _encode_action(action: MoveAction) -> str:
    return _toml_value({"piece": str(action.piece), "to": action.to_square})


def _decode_action(value: object, context: str) -> MoveAction:
    item = _mapping(value, context)
    if set(item) != {"piece", "to"}:
        raise ValueError(f"{context} must contain exactly 'piece' and 'to'.")
    piece = _string(item, "piece")
    destination = _string(item, "to")
    if destination not in chess.SQUARE_NAMES:
        raise ValueError(f"{context} has invalid destination {destination!r}.")
    return MoveAction(OriginalPieceId.parse(piece), destination)


def _validate_action(
    action: MoveAction, tracker: OriginalPieceTracker, side: str, context: str
) -> None:
    if not tracker.has(action.piece):
        raise FlowValidationError(
            f"{context}: original piece {action.piece} is absent from start_fen."
        )
    if action.piece.color != side:
        raise FlowValidationError(
            f"{context}: rules may only move the controlled {side} side."
        )
    if action.to_square not in chess.SQUARE_NAMES:
        raise FlowValidationError(
            f"{context}: invalid destination {action.to_square!r}."
        )


def _validate_action_legal(
    board: chess.Board, tracker: OriginalPieceTracker, action: MoveAction, context: str
) -> None:
    square = tracker.get(action.piece).current_square
    if square is None:
        raise FlowValidationError(
            f"{context}: original piece {action.piece} has been captured."
        )
    move = chess.Move(square, chess.parse_square(action.to_square))
    if move not in board.legal_moves:
        raise FlowValidationError(
            f"{context}: action {move.uci()} is not legal after its SAN prefix."
        )


def _validate_condition_references(
    condition, tracker: OriginalPieceTracker, state_ids: set[str], context: str
) -> None:
    missing_states = referenced_states(condition) - state_ids
    if missing_states:
        raise FlowValidationError(
            f"{context}: unknown states {sorted(missing_states)}."
        )
    missing_pieces = [
        str(item) for item in referenced_pieces(condition) if not tracker.has(item)
    ]
    if missing_pieces:
        raise FlowValidationError(
            f"{context}: original pieces absent from start_fen: {sorted(missing_pieces)}."
        )


def _validate_state_cycles(states: Mapping[str, object]) -> None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(state_id: str) -> None:
        if state_id in visiting:
            raise FlowValidationError(f"Named state cycle includes {state_id!r}.")
        if state_id in visited:
            return
        visiting.add(state_id)
        for dependency in referenced_states(states[state_id]):  # type: ignore[arg-type]
            visit(dependency)
        visiting.remove(state_id)
        visited.add(state_id)

    for state_id in states:
        visit(state_id)


def _replay_with_tracker(
    start: chess.Board, history: tuple[str, ...], context: str
) -> tuple[chess.Board, OriginalPieceTracker]:
    board = start.copy(stack=False)
    tracker = OriginalPieceTracker(start)
    for ply, san in enumerate(history, start=1):
        before = board.copy(stack=False)
        try:
            move = board.parse_san(san)
        except ValueError as exc:
            raise FlowValidationError(
                f"{context}: {san!r} is illegal at ply {ply}."
            ) from exc
        tracker.apply_move(before, move)
        board.push(move)
    return board, tracker


def _unique_ids(values, label: str) -> set[str]:
    seen: set[str] = set()
    for value in values:
        if not value.strip() or value in seen:
            raise FlowValidationError(
                f"{label.title()} ids must be non-empty and unique: {value!r}."
            )
        seen.add(value)
    return seen


def _validate_note(note: str | None, context: str) -> None:
    if note is not None and not isinstance(note, str):
        raise FlowValidationError(f"{context} note must be a string.")


def _expanded_fen(value: str) -> str:
    return chess.STARTING_FEN if value == "startpos" else value


def _mapping(value: object, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError(f"{context} must be a table")
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


def _boolean(mapping: dict[str, Any], key: str, default: bool) -> bool:
    value = mapping.get(key, default)
    if not isinstance(value, bool):
        raise TypeError(f"{key} must be a boolean")
    return value


def _string_tuple(value: object, context: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise TypeError(f"{context} must be an array of strings")
    return tuple(value)
