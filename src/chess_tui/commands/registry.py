"""Deterministic command discovery, availability, and slash parsing."""

from __future__ import annotations

import shlex

from .models import (
    CommandArgument,
    CommandAvailability,
    CommandDefinition,
    CommandFailure,
    CommandId,
    CommandInvocation,
)

COMMANDS: tuple[CommandDefinition, ...] = (
    CommandDefinition(
        CommandId.ANALYSE_POSITION,
        "/analyse",
        "/analyse",
        "Show local book moves and Stockfish's best candidates.",
    ),
    CommandDefinition(
        CommandId.EXPLAIN_DECISION,
        "/why",
        "/why",
        "Explain why the current policy decision was selected.",
    ),
    CommandDefinition(
        CommandId.INSPECT_RULE,
        "/rule",
        "/rule <rule-id>",
        "Inspect one policy rule or exact override.",
        (CommandArgument("rule_id", "Rule or override identifier."),),
    ),
    CommandDefinition(
        CommandId.LIST_RULES,
        "/rules",
        "/rules",
        "List rules grouped by their current effective status.",
    ),
    CommandDefinition(
        CommandId.TRACE_DECISION,
        "/trace",
        "/trace",
        "Show the deterministic trace for the current decision.",
    ),
    CommandDefinition(
        CommandId.INSPECT_POSITION,
        "/position",
        "/position",
        "Show the current position, history, and legal moves.",
    ),
    CommandDefinition(
        CommandId.PLAY_MOVE,
        "/play",
        "/play <SAN>",
        "Play a legal move using SAN notation.",
        (CommandArgument("move", "Move in SAN notation."),),
    ),
    CommandDefinition(
        CommandId.NEXT_OPPONENT,
        "/next",
        "/next",
        "Ask Stockfish to play the opponent's next move.",
    ),
    CommandDefinition(
        CommandId.RETRY_POLICY,
        "/retry",
        "/retry",
        "Discard the attempted move and retry the policy turn.",
    ),
    CommandDefinition(
        CommandId.CONTINUE_POLICY,
        "/continue",
        "/continue",
        "Discard the mismatch and play the selected policy move.",
    ),
    CommandDefinition(
        CommandId.ADD_RULE_FOR_MISMATCH,
        "/add-rule",
        "/add-rule",
        "Accept the attempted move as an exact-position policy rule.",
    ),
    CommandDefinition(
        CommandId.GO_BACK,
        "/back",
        "/back",
        "Return to the previous policy decision.",
    ),
    CommandDefinition(
        CommandId.RESTART,
        "/restart",
        "/restart",
        "Restart this line from its initial position.",
    ),
    CommandDefinition(
        CommandId.HINT_POLICY_MOVE,
        "/hint",
        "/hint",
        "Highlight the piece selected by the current policy.",
    ),
    CommandDefinition(
        CommandId.LIST_COMMANDS,
        "/help",
        "/help",
        "Show the commands available in the current position.",
    ),
)


class CommandRegistry:
    def __init__(self) -> None:
        self._by_id = {item.id: item for item in COMMANDS}
        self._by_slash = {item.slash: item for item in COMMANDS}

    def definition(self, command: CommandId) -> CommandDefinition:
        return self._by_id[command]

    def available(self, context: CommandAvailability) -> tuple[CommandDefinition, ...]:
        return tuple(item for item in COMMANDS if self.is_available(item.id, context))

    def is_available(self, command: CommandId, context: CommandAvailability) -> bool:
        if command in {
            CommandId.INSPECT_POSITION,
            CommandId.LIST_RULES,
            CommandId.LIST_COMMANDS,
        }:
            return True
        if command is CommandId.INSPECT_RULE:
            return context.has_rules
        if command in {CommandId.EXPLAIN_DECISION, CommandId.TRACE_DECISION}:
            return context.has_decision
        if command is CommandId.ANALYSE_POSITION:
            return context.engine_available and context.phase != "game-over"
        if command is CommandId.PLAY_MOVE:
            return context.phase in {"policy-ready", "opponent-ready"}
        if command is CommandId.NEXT_OPPONENT:
            return context.engine_available and context.phase == "opponent-ready"
        if command is CommandId.RETRY_POLICY:
            return context.phase == "policy-result"
        if command in {
            CommandId.CONTINUE_POLICY,
            CommandId.ADD_RULE_FOR_MISMATCH,
        }:
            return context.mismatch
        if command is CommandId.GO_BACK:
            return context.can_back
        if command is CommandId.RESTART:
            return context.can_restart
        if command is CommandId.HINT_POLICY_MOVE:
            return context.phase == "policy-ready" and context.has_decision_move
        return False

    def parse_chat(self, text: str) -> CommandInvocation:
        value = text.strip()
        if not value:
            raise CommandFailure("EMPTY_MESSAGE", "Enter a move or command.")
        if not value.startswith("/"):
            return CommandInvocation(
                CommandId.PLAY_MOVE, "chat", notation="san", move=value
            )
        try:
            parts = shlex.split(value)
        except ValueError as error:
            raise CommandFailure("INVALID_COMMAND", str(error)) from error
        if not parts:
            raise CommandFailure("INVALID_COMMAND", "Enter a slash command.")
        definition = self._by_slash.get(parts[0].lower())
        if definition is None:
            raise CommandFailure(
                "UNKNOWN_COMMAND", f"Unknown command {parts[0]!r}. Type / for help."
            )
        arguments = parts[1:]
        if definition.id is CommandId.INSPECT_RULE:
            if len(arguments) != 1:
                raise CommandFailure("INVALID_COMMAND", f"Usage: {definition.usage}.")
            return CommandInvocation(definition.id, "chat", rule_id=arguments[0])
        if definition.id is CommandId.PLAY_MOVE:
            if len(arguments) != 1:
                raise CommandFailure("INVALID_COMMAND", f"Usage: {definition.usage}.")
            return CommandInvocation(
                definition.id, "chat", notation="san", move=arguments[0]
            )
        if arguments:
            raise CommandFailure("INVALID_COMMAND", f"Usage: {definition.usage}.")
        return CommandInvocation(definition.id, "chat")
