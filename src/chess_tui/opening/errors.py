"""Errors raised by opening-move sources."""


class OpeningSourceError(RuntimeError):
    pass


class OpeningDataError(OpeningSourceError):
    pass
