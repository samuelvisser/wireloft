from __future__ import annotations

from datetime import datetime

from backend.api.models.base import RequestBase, ResponseBase


# ---------- Strict input (create/update) ----------
class _SettingsAPIBaseIn(RequestBase):
    """Fields for requests: validate here if needed."""
    pass


class SettingsAPICreate(_SettingsAPIBaseIn):
    """Creates the settings record"""
    pass


class SettingsAPIUpdate(_SettingsAPIBaseIn):
    """Updates a setting"""
    pass


# ---------- Lenient output (read) ----------
class _SettingsAPIBaseOut(ResponseBase):
    """Fields for responses: no validators, no constraints."""
    id: int


class SettingsAPIRead(_SettingsAPIBaseOut):
    """Represents the settings record."""
    created_at: datetime
    updated_at: datetime