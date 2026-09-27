from pydantic import Field

from backend.api.models.base import RequestBase, ResponseBase


class ShowAssetRootPreviewRequest(RequestBase):
    output_template: str = Field(min_length=1, max_length=4096)
    source_id: str | None = Field(default=None, max_length=100)
    local_media_profile_id: int | None = Field(default=None, gt=0)


class ShowAssetRootPreviewResponse(ResponseBase):
    path: str | None
    reason: str | None
    show_title: str | None
    system_enabled: bool
