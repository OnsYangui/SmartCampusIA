"""Business rule violations raised by services and mapped to HTTP errors by the API."""


class ConflictError(Exception):
    """The action is impossible in the current state (409)."""


class ForbiddenError(Exception):
    """The principal may not act on this resource (403)."""
