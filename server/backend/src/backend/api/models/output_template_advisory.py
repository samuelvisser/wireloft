from __future__ import annotations

from typing import Annotated

from pydantic import Field

from backend.api.models.base import RequestBase, ResponseBase
from backend.utils.jinja_analysis.custom_index_advisory import CustomIndexAdvisoryKind


class CustomIndexAdvisoryRequest(RequestBase):
    # This is an editor draft, not a saved LMP. Incomplete syntax is accepted and
    # returned as an ordinary advisory result rather than a validation exception.
    output_template: str = Field(max_length=4096)
    indexing_value_keys: list[Annotated[str, Field(min_length=1, max_length=64)]] = Field(
        default_factory=list, max_length=100,
    )


class CustomIndexSuggestionRead(ResponseBase):
    before: str
    after: str
    output_template: str


class CustomIndexAdvisoryRead(ResponseBase):
    key: str
    message: str
    kind: CustomIndexAdvisoryKind
    suggestion: CustomIndexSuggestionRead | None = None


class CustomIndexAdvisoryResultRead(ResponseBase):
    advisories: list[CustomIndexAdvisoryRead] = Field(default_factory=list)
    error: str | None = None
