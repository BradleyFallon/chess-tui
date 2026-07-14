"""Quiz provider failures surfaced to the presentation layer."""


class SessionError(RuntimeError):
    pass


class SessionProtocolError(SessionError):
    pass


class SessionUnavailableError(SessionError):
    pass
