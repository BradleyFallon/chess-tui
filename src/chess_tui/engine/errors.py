"""Typed failures raised by chess-engine services."""


class EngineError(RuntimeError):
    """Base class for configured engine failures."""


class EngineConfigurationError(EngineError):
    """The requested engine executable cannot be used."""


class EngineStartupError(EngineError):
    """The engine process could not be started or initialized."""


class EngineTimeoutError(EngineError):
    """The engine did not respond within its operational timeout."""


class EngineProcessError(EngineError):
    """The engine process exited or became unavailable."""


class EngineResultError(EngineError):
    """The engine returned no move or an invalid move."""
