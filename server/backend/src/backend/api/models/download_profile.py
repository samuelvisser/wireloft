from __future__ import annotations

from datetime import datetime

from backend.api.models.base import ResponseBase, RequestBase
from backend.types.download_profile_types import EpIdType


# ---------- Strict input (create/update) ----------
class DownloadProfileAPIBaseIn(RequestBase):
    enable_profile: bool
    ep_id_type_list: list[EpIdType]


class DownloadProfileAPICreate(DownloadProfileAPIBaseIn):
    """Request body for creating a download profile of any type.
    This model is meant to be extended by download profile implementations."""

    show_id: int
    local_media_profile_id: int


class DownloadProfileAPIUpdate(DownloadProfileAPIBaseIn):
    """Request body for updating a download profile of any type.
    This model is meant to be extended by download profile implementations."""

    local_media_profile_id: int


# ---------- Lenient output (read) ----------
class DownloadProfileAPIBaseOut(ResponseBase):
    id: int
    show_id: int
    local_media_profile_id: int
    type: str
    enable_profile: bool
    ep_id_type_list: list[EpIdType]


class DownloadProfileAPIRead(DownloadProfileAPIBaseOut):
    """Unified response body for a download profile (any type)."""

    created_at: datetime
    updated_at: datetime