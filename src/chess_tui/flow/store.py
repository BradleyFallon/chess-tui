"""Strict TOML loading and failure-safe persistence for Rulebook version 4."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import replace
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any

import chess

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # pyright: ignore[reportMissingImports]

from ..policy.conditions import condition_to_data, parse_condition, referenced_pieces
from ..policy.models import StartingPieceRef
from ..policy.models import ActionAttempt, CaptureAttempt, MoveAttempt
from ..policy.tracker import OriginalPieceTracker
from .errors import FlowStorageError, FlowValidationError
from .models import (
    DevelopmentInstruction,
    InterruptRule,
    OpeningTag,
    OpponentReply,
    PieceScript,
    Rulebook,
)
from .position import normalized_position_key, parse_legal_san, replay_san

SUPPORTED_VERSION = 4
_ALIAS_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")


class FlowStore:
    """The historical class name remains the storage service, not a schema alias."""

    def load(self, path: Path) -> Rulebook:
        try:
            return self.decode(path.read_text(encoding="utf-8"), context=str(path))
        except FileNotFoundError as exc:
            raise FlowStorageError(f"Rulebook file does not exist: {path}") from exc
        except (OSError, UnicodeError) as exc:
            raise FlowStorageError(f"Could not read Rulebook {path}: {exc}") from exc

    def decode(self, source: str, *, context: str = "Rulebook") -> Rulebook:
        try:
            data = tomllib.loads(source)
            rulebook = self._decode(data)
            self.validate(rulebook)
            return rulebook
        except tomllib.TOMLDecodeError as exc:
            raise FlowValidationError(f"Invalid TOML in {context}: {exc}") from exc
        except (KeyError, TypeError, ValueError, FlowValidationError) as exc:
            if isinstance(exc, FlowValidationError):
                raise
            raise FlowValidationError(f"Invalid {context}: {exc}") from exc

    def encode(self, rulebook: Rulebook) -> str:
        self.validate(rulebook)
        return _encode(rulebook)

    def save(self, path: Path, rulebook: Rulebook) -> None:
        source = self.encode(rulebook)
        if self.decode(source, context="serialized Rulebook") != rulebook:
            raise FlowStorageError("Serialized Rulebook validation changed its data.")
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
            raise FlowStorageError(f"Could not save Rulebook {path}: {exc}") from exc
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    def add_opponent_reply(self, path: Path, reply: OpponentReply) -> Rulebook:
        rulebook = self.load(path)
        target = replay_san(_expanded_fen(rulebook.start_fen), reply.after_san)
        move = parse_legal_san(target, reply.move_san, context="Opponent reply")
        branch = (normalized_position_key(target), move.uci())
        retained: list[OpponentReply] = []
        for existing in rulebook.opponent_replies:
            board = replay_san(_expanded_fen(rulebook.start_fen), existing.after_san)
            existing_move = parse_legal_san(
                board, existing.move_san, context="Opponent reply"
            )
            if (normalized_position_key(board), existing_move.uci()) == branch:
                return rulebook
            if existing.id != reply.id:
                retained.append(existing)
        updated = replace(rulebook, opponent_replies=(*retained, reply))
        self.save(path, updated)
        return updated

    def validate(self, rulebook: Rulebook) -> None:
        if rulebook.version != SUPPORTED_VERSION:
            raise FlowValidationError(
                f"Unsupported Rulebook version {rulebook.version}; expected 4. "
                "Version 3 is not accepted and no compatibility loader exists."
            )
        if not rulebook.name.strip():
            raise FlowValidationError("Rulebook name cannot be empty.")
        if rulebook.side not in {"white", "black"}:
            raise FlowValidationError(f"Invalid controlled side: {rulebook.side!r}.")
        try:
            start = chess.Board(_expanded_fen(rulebook.start_fen))
        except ValueError as exc:
            raise FlowValidationError(f"Invalid start_fen: {exc}") from exc
        controlled = chess.WHITE if rulebook.side == "white" else chess.BLACK
        if start.turn != controlled:
            raise FlowValidationError(
                f"start_fen must have controlled side {rulebook.side} to move."
            )
        tracker = OriginalPieceTracker(start)

        aliases = [piece.id for piece in rulebook.pieces]
        _unique(aliases, "piece alias")
        refs = [piece.ref for piece in rulebook.pieces]
        if len(refs) != len(set(refs)):
            raise FlowValidationError("Piece aliases must map to unique canonical refs.")
        alias_by_ref = rulebook.alias_by_ref
        for piece in rulebook.pieces:
            if not _ALIAS_PATTERN.fullmatch(piece.id):
                raise FlowValidationError(f"Invalid piece alias {piece.id!r}.")
            _validate_starting_piece(piece.ref, tracker, f"Piece {piece.id!r}")
            if piece.ref.color != rulebook.side and (
                piece.development is not None or piece.rules
            ):
                raise FlowValidationError(
                    f"Opponent piece {piece.id!r} is read-only and cannot author moves."
                )
            if piece.development is not None:
                development = piece.development
                if development.piece != piece.ref:
                    raise FlowValidationError(
                        f"Development owner mismatch for {piece.id!r}."
                    )
                _validate_square(development.to_square, f"{piece.id}.develop.to")
                _validate_why(development.why, f"{piece.id}.develop")
                if development.when is not None:
                    _validate_condition(
                        development.when,
                        tracker,
                        alias_by_ref,
                        f"{piece.id}.develop.when",
                    )
            rule_ids = [rule.id for rule in piece.rules]
            _unique(rule_ids, f"rule id in piece {piece.id!r}")
            for rule in piece.rules:
                if rule.piece != piece.ref:
                    raise FlowValidationError(f"Interrupt owner mismatch for {piece.id}.")
                _validate_why(rule.why, f"{piece.id}.{rule.id}")
                if not rule.attempts:
                    raise FlowValidationError(
                        f"Interrupt {piece.id}.{rule.id} requires a non-empty try list."
                    )
                if rule.when is not None:
                    _validate_condition(
                        rule.when,
                        tracker,
                        alias_by_ref,
                        f"{piece.id}.{rule.id}.when",
                    )
                for attempt in rule.attempts:
                    _validate_attempt(
                        attempt, piece.ref, tracker, alias_by_ref, piece.id, rule.id
                    )

        development_refs = tuple(
            piece.id for piece in rulebook.pieces if piece.development is not None
        )
        _validate_exact_order(
            rulebook.development_order, development_refs, "development_order"
        )
        interrupt_refs = tuple(
            f"{piece.id}.{rule.id}"
            for piece in rulebook.pieces
            for rule in piece.rules
        )
        _validate_exact_order(
            rulebook.interrupt_order, interrupt_refs, "interrupt_order"
        )

        instruction_refs = {
            *(f"{piece.id}.develop" for piece in rulebook.pieces if piece.development),
            *interrupt_refs,
        }
        dependencies: dict[str, tuple[str, ...]] = {}
        for piece in rulebook.pieces:
            if piece.development is not None:
                reference = f"{piece.id}.develop"
                dependencies[reference] = piece.development.requires
            for rule in piece.rules:
                reference = f"{piece.id}.{rule.id}"
                dependencies[reference] = rule.requires
        for reference, requirements in dependencies.items():
            if len(requirements) != len(set(requirements)):
                raise FlowValidationError(
                    f"Instruction {reference!r} has duplicate prerequisites."
                )
            missing = set(requirements) - instruction_refs
            if missing:
                raise FlowValidationError(
                    f"Instruction {reference!r} has unknown prerequisites "
                    f"{sorted(missing)}."
                )
        _validate_dependency_cycles(dependencies)

        exact_positions: dict[str, str] = {}
        for reference in rulebook.interrupt_order:
            rule = rulebook.interrupt_by_ref[reference]
            if rule.after_san is None:
                continue
            board = replay_san(
                _expanded_fen(rulebook.start_fen),
                rule.after_san,
                context=f"Interrupt {reference!r}",
            )
            if board.turn != controlled:
                raise FlowValidationError(
                    f"Exact interrupt {reference!r} must target "
                    f"{rulebook.side} to move."
                )
            key = normalized_position_key(board)
            if key in exact_positions:
                raise FlowValidationError(
                    f"Exact interrupts {exact_positions[key]!r} and {reference!r} "
                    "duplicate a normalized position."
                )
            exact_positions[key] = reference

        self._validate_opening_tags(rulebook.opening_tags)
        _unique((reply.id for reply in rulebook.opponent_replies), "opponent reply")
        branches: set[tuple[str, str]] = set()
        for reply in rulebook.opponent_replies:
            _validate_optional_note(reply.note, f"Opponent reply {reply.id!r}")
            board = replay_san(
                _expanded_fen(rulebook.start_fen),
                reply.after_san,
                context=f"Opponent reply {reply.id!r}",
            )
            if board.turn == controlled:
                raise FlowValidationError(
                    f"Opponent reply {reply.id!r} targets the controlled side."
                )
            move = parse_legal_san(
                board, reply.move_san, context=f"Opponent reply {reply.id!r}"
            )
            branch = (normalized_position_key(board), move.uci())
            if branch in branches:
                raise FlowValidationError(
                    f"Opponent reply {reply.id!r} duplicates an existing branch."
                )
            branches.add(branch)

    def warnings(self, rulebook: Rulebook) -> tuple[str, ...]:
        warnings: list[str] = []
        for piece in rulebook.pieces:
            if piece.development is not None and piece.id not in rulebook.development_order:
                warnings.append(
                    f"Controlled piece {piece.id!r} has development but is not ordered."
                )
            for rule in piece.rules:
                reference = f"{piece.id}.{rule.id}"
                if reference not in rulebook.interrupt_order:
                    warnings.append(f"Interrupt {reference!r} is not ordered.")
        return tuple(warnings)

    def _decode(self, data: dict[str, Any]) -> Rulebook:
        required = {
            "version",
            "name",
            "start_fen",
            "side",
            "development_order",
            "interrupt_order",
            "pieces",
        }
        _require_keys(data, required | {"opening_tags", "opponent_replies"})
        missing = required - set(data)
        if missing:
            raise ValueError(f"Missing required top-level fields {sorted(missing)}.")
        pieces_data = _mapping(data["pieces"], "pieces")
        preliminary: list[tuple[str, dict[str, Any], StartingPieceRef]] = []
        for alias, raw in pieces_data.items():
            item = _mapping(raw, f"pieces.{alias}")
            _require_keys(item, {"ref", "develop", "rules"})
            preliminary.append(
                (alias, item, StartingPieceRef.parse(_string(item, "ref")))
            )
        aliases = {alias: ref for alias, _, ref in preliminary}
        if len(aliases) != len(preliminary):
            raise ValueError("Duplicate piece aliases are not allowed.")

        pieces: list[PieceScript] = []
        for alias, item, ref in preliminary:
            development = (
                self._decode_development(item["develop"], alias, ref, aliases)
                if "develop" in item
                else None
            )
            raw_rules = item.get("rules", [])
            if not isinstance(raw_rules, list):
                raise TypeError(f"pieces.{alias}.rules must be an array of tables.")
            rules = tuple(
                self._decode_rule(raw, alias, ref, aliases)
                for raw in raw_rules
            )
            pieces.append(PieceScript(alias, ref, development, rules))

        opening_tags = data.get("opening_tags", [])
        opponent_replies = data.get("opponent_replies", [])
        if not isinstance(opening_tags, list) or not isinstance(opponent_replies, list):
            raise TypeError("opening_tags and opponent_replies must be arrays.")
        side = _string(data, "side")
        if side not in {"white", "black"}:
            raise ValueError("side must be 'white' or 'black'.")
        return Rulebook(
            version=_integer(data, "version"),
            name=_string(data, "name"),
            start_fen=_string(data, "start_fen"),
            side=side,  # type: ignore[arg-type]
            development_order=_string_tuple(
                data["development_order"], "development_order"
            ),
            interrupt_order=_string_tuple(
                data["interrupt_order"], "interrupt_order"
            ),
            pieces=tuple(pieces),
            opening_tags=tuple(
                self._decode_opening_tag(item) for item in opening_tags
            ),
            opponent_replies=tuple(
                self._decode_reply(item) for item in opponent_replies
            ),
        )

    def _decode_development(
        self,
        raw: object,
        alias: str,
        ref: StartingPieceRef,
        aliases: Mapping[str, StartingPieceRef],
    ) -> DevelopmentInstruction:
        item = _mapping(raw, f"pieces.{alias}.develop")
        _require_keys(item, {"to", "requires", "when", "why"})
        return DevelopmentInstruction(
            piece=ref,
            to_square=_string(item, "to"),
            requires=_requirements(item.get("requires", []), alias),
            when=(
                parse_condition(
                    item["when"],
                    context=f"pieces.{alias}.develop.when",
                    aliases=aliases,
                )
                if "when" in item
                else None
            ),
            why=_string(item, "why"),
        )

    def _decode_rule(
        self,
        raw: object,
        alias: str,
        ref: StartingPieceRef,
        aliases: Mapping[str, StartingPieceRef],
    ) -> InterruptRule:
        item = _mapping(raw, f"pieces.{alias}.rules")
        _require_keys(
            item, {"id", "requires", "after", "when", "required", "try", "why"}
        )
        rule_id = _string(item, "id")
        attempts_data = item.get("try")
        if not isinstance(attempts_data, list):
            raise TypeError(f"pieces.{alias}.{rule_id}.try must be an array.")
        return InterruptRule(
            piece=ref,
            id=rule_id,
            requires=_requirements(item.get("requires", []), alias),
            after_san=(
                _string_tuple(item["after"], f"pieces.{alias}.{rule_id}.after")
                if "after" in item
                else None
            ),
            when=(
                parse_condition(
                    item["when"],
                    context=f"pieces.{alias}.{rule_id}.when",
                    aliases=aliases,
                )
                if "when" in item
                else None
            ),
            required=_optional_bool(item, "required", False),
            attempts=tuple(
                _decode_attempt(attempt, aliases, f"{alias}.{rule_id}.try[{index}]")
                for index, attempt in enumerate(attempts_data)
            ),
            why=_string(item, "why"),
        )

    def _decode_opening_tag(self, raw: object) -> OpeningTag:
        item = _mapping(raw, "opening tag")
        _require_keys(item, {"eco", "name"})
        return OpeningTag(_string(item, "eco"), _string(item, "name"))

    def _decode_reply(self, raw: object) -> OpponentReply:
        item = _mapping(raw, "opponent reply")
        _require_keys(item, {"id", "after", "move", "note"})
        return OpponentReply(
            _string(item, "id"),
            _string_tuple(item.get("after"), "opponent_reply.after"),
            _string(item, "move"),
            _optional_string(item, "note"),
        )

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
                raise FlowValidationError(f"Duplicate opening tag {identity!r}.")
            identities.add(identity)


def _encode(rulebook: Rulebook) -> str:
    lines = [
        f"version = {rulebook.version}",
        f"name = {json.dumps(rulebook.name)}",
        f"start_fen = {json.dumps(rulebook.start_fen)}",
        f"side = {json.dumps(rulebook.side)}",
        f"development_order = {_toml_value(list(rulebook.development_order))}",
        f"interrupt_order = {_toml_value(list(rulebook.interrupt_order))}",
    ]
    for tag in rulebook.opening_tags:
        lines.extend(
            (
                "",
                "[[opening_tags]]",
                f"eco = {json.dumps(tag.eco)}",
                f"name = {json.dumps(tag.name)}",
            )
        )
    aliases = rulebook.alias_by_ref
    for piece in rulebook.pieces:
        key = _toml_key(piece.id)
        lines.extend(("", f"[pieces.{key}]", f"ref = {json.dumps(str(piece.ref))}"))
        if piece.development is not None:
            development = piece.development
            lines.extend(
                (
                    "",
                    f"[pieces.{key}.develop]",
                    f"to = {json.dumps(development.to_square)}",
                )
            )
            if development.requires:
                lines.append(
                    f"requires = {_toml_value(list(development.requires))}"
                )
            if development.when is not None:
                lines.append(
                    "when = "
                    f"{_toml_value(condition_to_data(development.when, aliases=aliases))}"
                )
            lines.append(f"why = {json.dumps(development.why)}")
        for rule in piece.rules:
            lines.extend(("", f"[[pieces.{key}.rules]]", f"id = {json.dumps(rule.id)}"))
            if rule.requires:
                lines.append(f"requires = {_toml_value(list(rule.requires))}")
            if rule.after_san is not None:
                lines.append(f"after = {_toml_value(list(rule.after_san))}")
            if rule.when is not None:
                lines.append(
                    f"when = {_toml_value(condition_to_data(rule.when, aliases=aliases))}"
                )
            if rule.required:
                lines.append("required = true")
            lines.append(
                f"try = {_toml_value([_attempt_to_data(item, aliases) for item in rule.attempts])}"
            )
            lines.append(f"why = {json.dumps(rule.why)}")
    for reply in rulebook.opponent_replies:
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


def _attempt_to_data(
    attempt: ActionAttempt, aliases: Mapping[StartingPieceRef, str]
) -> dict[str, object]:
    if isinstance(attempt, MoveAttempt):
        return {"move": attempt.to_square}
    if attempt.triggering_attacker:
        return {"capture": "attacker"}
    if attempt.target_piece is not None:
        return {"capture": aliases.get(attempt.target_piece, str(attempt.target_piece))}
    assert attempt.target_type is not None
    return {"capture_type": attempt.target_type}


def _decode_attempt(
    raw: object,
    aliases: Mapping[str, StartingPieceRef],
    context: str,
) -> ActionAttempt:
    item = _mapping(raw, context)
    if len(item) != 1:
        raise ValueError(f"{context} must contain exactly one action field.")
    kind, value = next(iter(item.items()))
    if kind == "move":
        return MoveAttempt(_string_value(value, context))
    if kind == "capture_type":
        piece_type = _string_value(value, context)
        if piece_type not in {"pawn", "knight", "bishop", "rook", "queen", "king"}:
            raise ValueError(f"{context} has invalid capture_type {piece_type!r}.")
        return CaptureAttempt(target_type=piece_type)  # type: ignore[arg-type]
    if kind == "capture":
        target = _string_value(value, context)
        if target == "attacker":
            return CaptureAttempt(triggering_attacker=True)
        try:
            reference = aliases.get(target) or StartingPieceRef.parse(target)
        except ValueError as exc:
            if target in {"pawn", "knight", "bishop", "rook", "queen", "king"}:
                return CaptureAttempt(target_type=target)  # type: ignore[arg-type]
            raise ValueError(f"{context} references unknown piece {target!r}.") from exc
        return CaptureAttempt(target_piece=reference)
    raise ValueError(f"{context} uses unsupported action {kind!r}.")


def _validate_attempt(
    attempt: ActionAttempt,
    owner: StartingPieceRef,
    tracker: OriginalPieceTracker,
    alias_by_ref: Mapping[StartingPieceRef, str],
    alias: str,
    rule_id: str,
) -> None:
    context = f"Interrupt {alias}.{rule_id}"
    if isinstance(attempt, MoveAttempt):
        _validate_square(attempt.to_square, context)
        return
    choices = sum(
        (
            attempt.target_piece is not None,
            attempt.target_type is not None,
            attempt.triggering_attacker,
        )
    )
    if choices != 1:
        raise FlowValidationError(f"{context} capture attempt is not discriminated.")
    if attempt.target_piece is not None:
        _validate_starting_piece(attempt.target_piece, tracker, context)
        if attempt.target_piece not in alias_by_ref:
            raise FlowValidationError(
                f"{context} target {attempt.target_piece} requires a declared alias."
            )
        if attempt.target_piece.color == owner.color:
            raise FlowValidationError(f"{context} cannot capture a friendly piece.")


def _validate_condition(
    condition,
    tracker: OriginalPieceTracker,
    alias_by_ref: Mapping[StartingPieceRef, str],
    context: str,
) -> None:
    for reference in referenced_pieces(condition):
        _validate_starting_piece(reference, tracker, context)
        if reference not in alias_by_ref:
            raise FlowValidationError(
                f"{context}: referenced piece {reference} requires a declared alias."
            )


def _validate_starting_piece(
    reference: StartingPieceRef, tracker: OriginalPieceTracker, context: str
) -> None:
    piece_id = reference.original_piece_id
    if not tracker.has(piece_id):
        raise FlowValidationError(
            f"{context}: {reference} is absent from start_fen."
        )
    expected = {
        "pawn": chess.PAWN,
        "knight": chess.KNIGHT,
        "bishop": chess.BISHOP,
        "rook": chess.ROOK,
        "queen": chess.QUEEN,
        "king": chess.KING,
    }[reference.piece_type]
    if tracker.get(piece_id).piece_type != expected:
        raise FlowValidationError(
            f"{context}: {reference} does not identify the expected piece type."
        )


def _validate_exact_order(
    actual: tuple[str, ...], expected: tuple[str, ...], name: str
) -> None:
    if len(actual) != len(set(actual)):
        raise FlowValidationError(f"{name} contains duplicate entries.")
    missing = set(expected) - set(actual)
    extra = set(actual) - set(expected)
    if missing or extra:
        raise FlowValidationError(
            f"{name} must contain every authored item exactly once; "
            f"missing={sorted(missing)}, extra={sorted(extra)}."
        )


def _validate_dependency_cycles(
    dependencies: Mapping[str, tuple[str, ...]]
) -> None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(reference: str) -> None:
        if reference in visiting:
            raise FlowValidationError(
                f"Instruction dependency cycle includes {reference!r}."
            )
        if reference in visited:
            return
        visiting.add(reference)
        for dependency in dependencies[reference]:
            visit(dependency)
        visiting.remove(reference)
        visited.add(reference)

    for reference in dependencies:
        visit(reference)


def _requirements(raw: object, owner: str) -> tuple[str, ...]:
    values = _string_tuple(raw, "requires")
    return tuple(
        (
            f"{owner}.develop"
            if value == "develop"
            else f"{owner}.{value}"
            if "." not in value
            else value
        )
        for value in values
    )


def _unique(values: Iterable[str], label: str) -> set[str]:
    seen: set[str] = set()
    for value in values:
        if value in seen:
            raise FlowValidationError(f"Duplicate {label}: {value!r}.")
        seen.add(value)
    return seen


def _validate_square(value: str, context: str) -> None:
    if value not in chess.SQUARE_NAMES:
        raise FlowValidationError(f"{context}: invalid square {value!r}.")


def _validate_why(value: str, context: str) -> None:
    if not value.strip():
        raise FlowValidationError(f"{context} requires a non-empty why.")


def _validate_optional_note(value: str | None, context: str) -> None:
    if value is not None and not value.strip():
        raise FlowValidationError(f"{context} note cannot be empty.")


def _require_keys(item: Mapping[str, object], allowed: set[str]) -> None:
    unknown = set(item) - allowed
    if unknown:
        raise ValueError(f"Unknown fields {sorted(unknown)}.")


def _mapping(value: object, context: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise TypeError(f"{context} must be a table/object.")
    return value


def _string(item: Mapping[str, object], key: str) -> str:
    if key not in item:
        raise KeyError(f"Missing required field {key!r}.")
    return _string_value(item[key], key)


def _string_value(value: object, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"{context} must be a non-empty string.")
    return value


def _integer(item: Mapping[str, object], key: str) -> int:
    value = item.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{key} must be an integer.")
    return value


def _optional_bool(
    item: Mapping[str, object], key: str, default: bool
) -> bool:
    value = item.get(key, default)
    if not isinstance(value, bool):
        raise TypeError(f"{key} must be a boolean.")
    return value


def _string_tuple(value: object, context: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise TypeError(f"{context} must be an array of strings.")
    return tuple(value)


def _optional_string(item: Mapping[str, object], key: str) -> str | None:
    value = item.get(key)
    if value is None:
        return None
    return _string_value(value, key)


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


def _toml_key(value: str) -> str:
    return value if _ALIAS_PATTERN.fullmatch(value) else json.dumps(value)


def _expanded_fen(value: str) -> str:
    return chess.STARTING_FEN if value == "startpos" else value
