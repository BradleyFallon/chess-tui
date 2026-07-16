"""Backend-owned application commands for UI and future tool callers."""

from .models import (
    ActivityEvent,
    AssistantReply,
    ClientEffect,
    CommandArgument,
    CommandAvailability,
    CommandDefinition,
    CommandFailure,
    CommandId,
    CommandInvocation,
    CommandOutcome,
)
from .registry import COMMANDS, CommandRegistry

__all__ = [
    "COMMANDS",
    "ActivityEvent",
    "AssistantReply",
    "ClientEffect",
    "CommandArgument",
    "CommandAvailability",
    "CommandDefinition",
    "CommandFailure",
    "CommandId",
    "CommandInvocation",
    "CommandOutcome",
    "CommandRegistry",
]
