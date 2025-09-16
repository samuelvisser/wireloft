from __future__ import annotations

from datetime import datetime

from backend.api.models.base import RequestBase, ResponseBase


class _SettingsAPIBase:
    """Fields common to all settings models."""
    pass


class SettingsAPICreate(_SettingsAPIBase, RequestBase):
    """Creates the settings record"""
    pass


class SettingsAPIRead(_SettingsAPIBase, ResponseBase):
    """Represents the settings record."""

    id: int
    created_at: datetime
    updated_at: datetime


class SettingsAPIUpdate(_SettingsAPIBase, RequestBase):
    """Updates a setting"""
    pass