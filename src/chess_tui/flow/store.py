"""Strict TOML loading and failure-safe persistence for version 3 flows."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import replace
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

from ..policy import (
    ConditionEvaluator,
    MoveAction,
    OriginalPieceTracker,
    StartingPieceRef,
    condition_to_data,
    parse_condition,
    referenced_conditions,
    referenced_pieces,
)
from .errors import FlowStorageError, FlowValidationError
from .models import (
    AuthoredPolicyItem,
    DevelopmentAssignment,
    ExactOverride,
    Flow,
    MoveRule,
    NamedCondition,
    OpeningTag,
    OpponentReply,
    Structure,
)
from .position import normalized_position_key, parse_legal_san, replay_san

SUPPORTED_VERSION = 3


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

    def replace_policy_item(self, path: Path, replacement: AuthoredPolicyItem) -> Flow:
        flow = self.load(path)
        updated = _replace_policy_item(flow, replacement)
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
                f"Unsupported flow version {flow.version}; expected "
                f"{SUPPORTED_VERSION}. Version 2 is not accepted."
            )
        if not flow.name.strip():
            raise FlowValidationError("Flow name cannot be empty.")
        if flow.side not in {"white", "black"}:
            raise FlowValidationError(f"Invalid controlled side: {flow.side!r}.")
        self._validate_opening_tags(flow.opening_tags)
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

        condition_ids = _unique_ids((item.id for item in flow.conditions), "condition")
        condition_map = {item.id: item.when for item in flow.conditions}
        for item in flow.conditions:
            _validate_condition_references(
                item.when,
                tracker,
                condition_ids,
                f"Condition {item.id!r}",
            )
        _validate_condition_cycles(condition_map)

        structure_ids = _unique_ids((item.id for item in flow.structures), "structure")
        evaluator = ConditionEvaluator(start, tracker, condition_map)
        for structure in flow.structures:
            if not structure.name.strip():
                raise FlowValidationError(
                    f"Structure {structure.id!r} name cannot be empty."
                )
            _validate_note(structure.note, f"Structure {structure.id!r}")
            for label, condition in (
                ("availability", structure.available_when),
                ("selection", structure.selected_when),
            ):
                _validate_condition_references(
                    condition,
                    tracker,
                    condition_ids,
                    f"Structure {structure.id!r} {label}",
                )
            if evaluator.evaluate(structure.selected_when).value:
                raise FlowValidationError(
                    f"Structure {structure.id!r} selected_when is true in the "
                    "initial position; initial structure selection is not supported."
                )

        _unique_ids((item.id for item in flow.policy_items), "policy item")
        for section, items in (
            ("response", flow.responses),
            ("development", flow.development),
            ("continuation", flow.continuations),
        ):
            for item in items:
                _validate_note(item.note, f"{section.title()} {item.id!r}")
                _validate_scopes(item.structures, structure_ids, item.id)
                if isinstance(item, DevelopmentAssignment):
                    if item.piece.color != flow.side:
                        raise FlowValidationError(
                            f"Development {item.id!r} may only assign the "
                            f"controlled {flow.side} side."
                        )
                    if item.target not in chess.SQUARE_NAMES:
                        raise FlowValidationError(
                            f"Development {item.id!r}: invalid target "
                            f"{item.target!r}."
                        )
                    conditions = (("readiness", item.ready_when),)
                else:
                    conditions = (
                        ("unlock", item.unlock_when),
                        ("live", item.when),
                        ("expiration", item.expire_when),
                    )
                _validate_action(
                    item.move, tracker, flow.side, f"{section} {item.id!r}"
                )
                for label, condition in conditions:
                    if condition is not None:
                        _validate_condition_references(
                            condition,
                            tracker,
                            condition_ids,
                            f"{section.title()} {item.id!r} {label}",
                        )
        _validate_development_assignments(flow.development)

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

    def warnings(self, flow: Flow) -> tuple[str, ...]:
        """Return non-fatal static authoring diagnostics."""

        warnings: list[str] = []
        scoped = {scope for item in flow.policy_items for scope in item.structures}
        for structure in flow.structures:
            if structure.id not in scoped:
                warnings.append(
                    f"Structure {structure.id!r} is never referenced by a policy item."
                )
        references = set().union(
            *(referenced_conditions(candidate) for candidate in _all_conditions(flow)),
            set(),
        )
        for condition in flow.conditions:
            if condition.id not in references:
                warnings.append(
                    f"Named condition {condition.id!r} is never referenced."
                )
        return tuple(warnings)

    def _validate_opening_tags(self, tags: tuple[OpeningTag, ...]) -> None:
        identities: set[tuple[str, str]] = set()
        for tag in tags:
            if (
                len(tag.eco) != 3
                or tag.eco[0] not in "ABCDE"
                or not tag.eco[1:].isdigit()
            ):
                raise FlowValidationError(
                    f"Opening tag has invalid ECO code {tag.eco!r}."
                )
            if not tag.name.strip():
                raise FlowValidationError("Opening tag name cannot be empty.")
            identity = (tag.eco, tag.name)
            if identity in identities:
                raise FlowValidationError(
                    f"Opening tags must be unique; duplicate {tag.name!r} ({tag.eco})."
                )
            identities.add(identity)

    def _decode(self, data: dict[str, Any]) -> Flow:
        _require_keys(
            data,
            {
                "version",
                "name",
                "start_fen",
                "side",
                "opening_tags",
                "conditions",
                "structures",
                "responses",
                "development",
                "continuations",
                "overrides",
                "opponent_replies",
            },
        )
        collection_names = (
            "opening_tags",
            "conditions",
            "structures",
            "responses",
            "development",
            "continuations",
            "overrides",
            "opponent_replies",
        )
        collections = {key: data.get(key, []) for key in collection_names}
        if not all(isinstance(value, list) for value in collections.values()):
            raise TypeError(f"{', '.join(collection_names)} must be arrays of tables")
        side = _string(data, "side")
        if side not in {"white", "black"}:
            raise ValueError("side must be 'white' or 'black'")
        return Flow(
            version=_integer(data, "version"),
            name=_string(data, "name"),
            start_fen=_string(data, "start_fen"),
            side=side,  # type: ignore[arg-type]
            opening_tags=tuple(
                self._decode_opening_tag(item) for item in collections["opening_tags"]
            ),
            conditions=tuple(
                self._decode_condition(item) for item in collections["conditions"]
            ),
            structures=tuple(
                self._decode_structure(item) for item in collections["structures"]
            ),
            responses=tuple(
                self._decode_move_rule(item, "response")
                for item in collections["responses"]
            ),
            development=tuple(
                self._decode_development(item) for item in collections["development"]
            ),
            continuations=tuple(
                self._decode_move_rule(item, "continuation")
                for item in collections["continuations"]
            ),
            overrides=tuple(
                self._decode_override(item) for item in collections["overrides"]
            ),
            opponent_replies=tuple(
                self._decode_reply(item) for item in collections["opponent_replies"]
            ),
        )

    def _decode_opening_tag(self, value: object) -> OpeningTag:
        item = _mapping(value, "opening tag")
        _require_keys(item, {"eco", "name"})
        return OpeningTag(eco=_string(item, "eco"), name=_string(item, "name"))

    def _decode_condition(self, value: object) -> NamedCondition:
        item = _mapping(value, "condition")
        _require_keys(item, {"id", "when"})
        return NamedCondition(
            _string(item, "id"),
            parse_condition(item.get("when"), context="condition.when"),
        )

    def _decode_structure(self, value: object) -> Structure:
        item = _mapping(value, "structure")
        _require_keys(
            item,
            {"id", "name", "available_when", "selected_when", "note"},
        )
        return Structure(
            id=_string(item, "id"),
            name=_string(item, "name"),
            available_when=parse_condition(
                item.get("available_when"), context="structure.available_when"
            ),
            selected_when=parse_condition(
                item.get("selected_when"), context="structure.selected_when"
            ),
            note=_optional_string(item, "note"),
        )

    def _decode_move_rule(self, value: object, context: str) -> MoveRule:
        item = _mapping(value, context)
        _require_keys(
            item,
            {
                "id",
                "move",
                "structures",
                "unlock_when",
                "when",
                "expire_when",
                "note",
            },
        )
        return MoveRule(
            id=_string(item, "id"),
            move=_decode_action(item.get("move"), f"{context}.move"),
            structures=_optional_string_tuple(
                item, "structures", f"{context}.structures"
            ),
            unlock_when=_optional_condition(item, "unlock_when", context),
            when=_optional_condition(item, "when", context),
            expire_when=_optional_condition(item, "expire_when", context),
            note=_optional_string(item, "note"),
        )

    def _decode_development(self, value: object) -> DevelopmentAssignment:
        item = _mapping(value, "development")
        _require_keys(
            item,
            {"id", "piece", "target", "structures", "ready_when", "note"},
        )
        target = _string(item, "target")
        if target not in chess.SQUARE_NAMES:
            raise ValueError(f"development.target has invalid square {target!r}.")
        return DevelopmentAssignment(
            id=_string(item, "id"),
            piece=StartingPieceRef.parse(_string(item, "piece")),
            target=target,
            structures=_optional_string_tuple(
                item, "structures", "development.structures"
            ),
            ready_when=_optional_condition(item, "ready_when", "development"),
            note=_optional_string(item, "note"),
        )

    def _decode_override(self, value: object) -> ExactOverride:
        item = _mapping(value, "override")
        _require_keys(item, {"id", "after", "note", "move"})
        return ExactOverride(
            id=_string(item, "id"),
            after_san=_string_tuple(item.get("after"), "override.after"),
            move=_decode_action(item.get("move"), "override.move"),
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
    for tag in flow.opening_tags:
        lines.extend(
            (
                "",
                "[[opening_tags]]",
                f"eco = {json.dumps(tag.eco)}",
                f"name = {json.dumps(tag.name)}",
            )
        )
    for item in flow.conditions:
        lines.extend(
            (
                "",
                "[[conditions]]",
                f"id = {json.dumps(item.id)}",
                f"when = {_toml_value(condition_to_data(item.when))}",
            )
        )
    for structure in flow.structures:
        lines.extend(
            (
                "",
                "[[structures]]",
                f"id = {json.dumps(structure.id)}",
                f"name = {json.dumps(structure.name)}",
                "available_when = "
                f"{_toml_value(condition_to_data(structure.available_when))}",
                "selected_when = "
                f"{_toml_value(condition_to_data(structure.selected_when))}",
            )
        )
        if structure.note is not None:
            lines.append(f"note = {json.dumps(structure.note)}")
    _encode_move_rules(lines, "responses", flow.responses)
    for item in flow.development:
        lines.extend(
            (
                "",
                "[[development]]",
                f"id = {json.dumps(item.id)}",
                f"piece = {json.dumps(str(item.piece))}",
                f"target = {json.dumps(item.target)}",
            )
        )
        if item.structures:
            lines.append(f"structures = {_toml_value(list(item.structures))}")
        if item.ready_when is not None:
            lines.append(
                f"ready_when = {_toml_value(condition_to_data(item.ready_when))}"
            )
        if item.note is not None:
            lines.append(f"note = {json.dumps(item.note)}")
    _encode_move_rules(lines, "continuations", flow.continuations)
    for override in flow.overrides:
        lines.extend(
            (
                "",
                "[[overrides]]",
                f"id = {json.dumps(override.id)}",
                f"after = {_toml_value(list(override.after_san))}",
                f"move = {_encode_action(override.move)}",
            )
        )
        if override.note is not None:
            lines.append(f"note = {json.dumps(override.note)}")
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


def _encode_move_rules(
    lines: list[str], section: str, rules: tuple[MoveRule, ...]
) -> None:
    for rule in rules:
        lines.extend(
            (
                "",
                f"[[{section}]]",
                f"id = {json.dumps(rule.id)}",
                f"move = {_encode_action(rule.move)}",
            )
        )
        if rule.structures:
            lines.append(f"structures = {_toml_value(list(rule.structures))}")
        for key, condition in (
            ("unlock_when", rule.unlock_when),
            ("when", rule.when),
            ("expire_when", rule.expire_when),
        ):
            if condition is not None:
                lines.append(f"{key} = {_toml_value(condition_to_data(condition))}")
        if rule.note is not None:
            lines.append(f"note = {json.dumps(rule.note)}")


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
    return _toml_value(
        {
            "piece": str(StartingPieceRef.from_original(action.piece)),
            "to": action.to_square,
        }
    )


def _decode_action(value: object, context: str) -> MoveAction:
    item = _mapping(value, context)
    if set(item) != {"piece", "to"}:
        raise ValueError(f"{context} must contain exactly 'piece' and 'to'.")
    destination = _string(item, "to")
    if destination not in chess.SQUARE_NAMES:
        raise ValueError(f"{context} has invalid destination {destination!r}.")
    return MoveAction(
        StartingPieceRef.parse(_string(item, "piece")).original_piece_id,
        destination,
    )


def _validate_action(
    action: MoveAction, tracker: OriginalPieceTracker, side: str, context: str
) -> None:
    if not tracker.has(action.piece):
        raise FlowValidationError(
            f"{context}: original piece {action.piece} is absent from start_fen."
        )
    if action.piece.color != side:
        raise FlowValidationError(
            f"{context}: policy items may only move the controlled {side} side."
        )
    reference = StartingPieceRef.from_original(action.piece)
    if tracker.get(action.piece).piece_type != _expected_piece_type(reference):
        raise FlowValidationError(
            f"{context}: {reference} does not identify the expected "
            f"{reference.piece_type} in start_fen."
        )
    if action.to_square not in chess.SQUARE_NAMES:
        raise FlowValidationError(
            f"{context}: invalid destination {action.to_square!r}."
        )


def _expected_piece_type(reference: StartingPieceRef) -> chess.PieceType:
    return {
        "pawn": chess.PAWN,
        "knight": chess.KNIGHT,
        "bishop": chess.BISHOP,
        "rook": chess.ROOK,
        "queen": chess.QUEEN,
        "king": chess.KING,
    }[reference.piece_type]


def _validate_action_legal(
    board: chess.Board,
    tracker: OriginalPieceTracker,
    action: MoveAction,
    context: str,
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
    condition,
    tracker: OriginalPieceTracker,
    condition_ids: set[str],
    context: str,
) -> None:
    missing_conditions = referenced_conditions(condition) - condition_ids
    if missing_conditions:
        raise FlowValidationError(
            f"{context}: unknown conditions {sorted(missing_conditions)}."
        )
    missing_pieces = [
        str(item) for item in referenced_pieces(condition) if not tracker.has(item)
    ]
    if missing_pieces:
        raise FlowValidationError(
            f"{context}: original pieces absent from start_fen: "
            f"{sorted(missing_pieces)}."
        )
    for piece_id in referenced_pieces(condition):
        reference = StartingPieceRef.from_original(piece_id)
        if tracker.get(piece_id).piece_type != _expected_piece_type(reference):
            raise FlowValidationError(
                f"{context}: {reference} does not identify the expected "
                f"{reference.piece_type} in start_fen."
            )


def _validate_condition_cycles(conditions: Mapping[str, object]) -> None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(condition_id: str) -> None:
        if condition_id in visiting:
            raise FlowValidationError(
                f"Named condition cycle includes {condition_id!r}."
            )
        if condition_id in visited:
            return
        visiting.add(condition_id)
        for dependency in referenced_conditions(conditions[condition_id]):  # type: ignore[arg-type]
            visit(dependency)
        visiting.remove(condition_id)
        visited.add(condition_id)

    for condition_id in conditions:
        visit(condition_id)


def _validate_scopes(
    scopes: tuple[str, ...], structure_ids: set[str], item_id: str
) -> None:
    if len(scopes) != len(set(scopes)):
        raise FlowValidationError(
            f"Policy item {item_id!r} contains duplicate structure scopes."
        )
    missing = set(scopes) - structure_ids
    if missing:
        raise FlowValidationError(
            f"Policy item {item_id!r} references unknown structures "
            f"{sorted(missing)}."
        )


def _validate_development_assignments(
    assignments: tuple[DevelopmentAssignment, ...],
) -> None:
    by_piece: dict[StartingPieceRef, list[DevelopmentAssignment]] = {}
    for item in assignments:
        by_piece.setdefault(item.piece, []).append(item)
    for piece, items in by_piece.items():
        globals_for_piece = [item for item in items if not item.structures]
        if len(globals_for_piece) > 1:
            raise FlowValidationError(
                f"{piece} has more than one global development assignment."
            )
        scopes_seen: set[str] = set()
        for item in items:
            overlap = scopes_seen.intersection(item.structures)
            if overlap:
                raise FlowValidationError(
                    f"{piece} has overlapping development assignments for "
                    f"structures {sorted(overlap)}."
                )
            scopes_seen.update(item.structures)


def _all_conditions(flow: Flow) -> Iterable:
    for item in flow.conditions:
        yield item.when
    for item in flow.structures:
        yield item.available_when
        yield item.selected_when
    for item in (*flow.responses, *flow.continuations):
        for condition in (item.unlock_when, item.when, item.expire_when):
            if condition is not None:
                yield condition
    for item in flow.development:
        if item.ready_when is not None:
            yield item.ready_when


def _replace_policy_item(flow: Flow, replacement: AuthoredPolicyItem) -> Flow:
    if isinstance(replacement, DevelopmentAssignment):
        if all(item.id != replacement.id for item in flow.development):
            raise FlowValidationError(f"Unknown development id: {replacement.id!r}.")
        return replace(
            flow,
            development=tuple(
                replacement if item.id == replacement.id else item
                for item in flow.development
            ),
        )
    if any(item.id == replacement.id for item in flow.responses):
        return replace(
            flow,
            responses=tuple(
                replacement if item.id == replacement.id else item
                for item in flow.responses
            ),
        )
    if any(item.id == replacement.id for item in flow.continuations):
        return replace(
            flow,
            continuations=tuple(
                replacement if item.id == replacement.id else item
                for item in flow.continuations
            ),
        )
    raise FlowValidationError(f"Unknown move-rule id: {replacement.id!r}.")


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
        tracker.apply_move(before, move, ply=ply)
        board.push(move)
    return board, tracker


def _unique_ids(values: Iterable[str], label: str) -> set[str]:
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


def _string_tuple(value: object, context: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise TypeError(f"{context} must be an array of strings")
    return tuple(value)


def _optional_string_tuple(
    mapping: dict[str, Any], key: str, context: str
) -> tuple[str, ...]:
    if key not in mapping:
        return ()
    return _string_tuple(mapping[key], context)


def _optional_condition(mapping: dict[str, Any], key: str, context: str):
    if key not in mapping:
        return None
    return parse_condition(mapping[key], context=f"{context}.{key}")
