from __future__ import annotations

from typing import Optional
from datetime import datetime

from backend.api.models.base import RequestBase, ResponseBase


class SettingsAPIBase:
    """Fields common to all settings models."""
    pass


class SettingsAPICreate(SettingsAPIBase, RequestBase):
    """Creates the settings record"""
    pass


class SettingsAPIRead(SettingsAPIBase, ResponseBase):
    """Represents the settings record."""

    id: int
    created_at: datetime
    updated_at: datetime


class SettingsAPIUpdate(SettingsAPIBase, RequestBase):
    """Updates a setting"""
    pass