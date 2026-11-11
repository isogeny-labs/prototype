"""The three ways a request can be turned down. The web API maps them to 404, 422 and 409."""
from __future__ import annotations


class NotFound(Exception):
    pass


class BadRequest(Exception):
    def __init__(self, message: str, field: str | None = None):
        super().__init__(message)
        self.message, self.field = message, field


class Conflict(Exception):
    """Not possible right now (for example: tests are still running)."""
