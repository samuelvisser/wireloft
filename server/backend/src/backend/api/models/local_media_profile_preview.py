from typing import Literal

from pydantic import Field

from backend.api.models.base import ResponseBase
from backend.api.models.local_media_profile import (
    LocalMediaProfileTemplatePreview,
    LocalMediaProfileTemplatePreviewResult,
)


class LocalMediaProfilePreviewRequest(LocalMediaProfileTemplatePreview):
    """One unsaved profile and editable example shared by every form preview."""

    type: Literal["show", "movie"]
    source_id: str | None = Field(default=None, max_length=100)
    local_media_profile_id: int | None = Field(default=None, gt=0)


class LocalMediaProfileOutputPreview(LocalMediaProfileTemplatePreviewResult):
    output_path: str | None = None
    used_variables: list[str] = Field(default_factory=list)
    error: str | None = None


class LocalMediaProfileShowPreview(ResponseBase):
    path: str | None = None
    reason: str | None = None
    show_title: str | None = None
    system_enabled: bool


class LocalMediaProfilePreviewResult(ResponseBase):
    output: LocalMediaProfileOutputPreview
    show_root: LocalMediaProfileShowPreview | None = None
