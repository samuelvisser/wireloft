from __future__ import annotations

from datetime import datetime
from typing import Union

from pydantic import Field, computed_field, field_validator

from backend.api.models.base import RequestBase, ResponseBase
from backend.api.models.pagination import OffsetPageRead
from backend.types.local_media_profile_types import (
    LocalMediaProfileStorageMode,
    LocalMediaProfileThumbnailMode,
    LocalMediaProfileType,
    PreferredFormat,
)
from backend.utils.output_template_formatting import normalize_output_template_expression_spacing
from backend.utils.helpers import slugify


class LocalMediaProfileAPIBaseIn(RequestBase):
    """Fields shared by all Local Media Profile request models."""

    name: str = Field(min_length=1)
    preferred_format: PreferredFormat
    download_mode: LocalMediaProfileStorageMode = LocalMediaProfileStorageMode.SYSTEM
    thumbnail_mode: LocalMediaProfileThumbnailMode = LocalMediaProfileThumbnailMode.SYSTEM
    output_template: str = Field(min_length=16, max_length=4096)

    @computed_field(return_type=str)
    @property
    def slug(self) -> str:
        return slugify(self.name)

    @field_validator("output_template", mode="before")
    @classmethod
    def _normalize_output_template(cls, value: object) -> object:
        if isinstance(value, str):
            return normalize_output_template_expression_spacing(value)
        return value


class LocalMediaProfileAPIBaseOut(ResponseBase):
    """Fields shared by all Local Media Profile response models."""

    id: int
    type: Union[LocalMediaProfileType, str]
    slug: str
    name: str
    output_template: str
    preferred_format: Union[PreferredFormat, str]
    download_mode: Union[LocalMediaProfileStorageMode, str] = LocalMediaProfileStorageMode.SYSTEM
    thumbnail_mode: Union[LocalMediaProfileThumbnailMode, str] = LocalMediaProfileThumbnailMode.SYSTEM
    append_media_type_to_filename: bool
    created_at: datetime
    updated_at: datetime


class LocalMediaProfileTemplateVariable(ResponseBase):
    name: str
    description: str


class LocalMediaProfileTemplateSource(ResponseBase):
    id: str
    label: str
    values: dict[str, str]
    fallback: bool = False


class LocalMediaProfileTemplateSourcePage(OffsetPageRead[LocalMediaProfileTemplateSource]):
    pass


class LocalMediaProfileTemplatePreview(RequestBase):
    type: LocalMediaProfileType
    output_template: str = Field(min_length=1, max_length=4096)
    preferred_format: PreferredFormat
    values: dict[str, str] = Field(default_factory=dict)


class LocalMediaProfileTemplatePreviewResult(ResponseBase):
    output_path: str
    used_variables: list[str]
