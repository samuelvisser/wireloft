"""A request about messages and actions that WireLoft refuses, with the form field it is about."""
from __future__ import annotations


class NotificationError(ValueError):
    def __init__(self, message: str, *, field: str | None = None, status_code: int = 422):
        super().__init__(message)
        self.field = field
        self.status_code = status_code
