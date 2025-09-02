from __future__ import annotations

from typing import Optional

from .BaseRecord import BaseRecord


class SettingValueUpdate(BaseRecord):
    value: Optional[str] = None
