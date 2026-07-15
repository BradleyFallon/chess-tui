"""Errors raised by opening-move sources."""


class OpeningSourceError(RuntimeError):
    pass


class OpeningDataError(OpeningSourceError):
    pass


class OpponentPlannerError(OpeningSourceError):
    """A move source returned data that is unsafe to present or apply."""
