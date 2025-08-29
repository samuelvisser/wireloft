from typing import Any
from pydantic import BaseModel, Field, ConfigDict, model_validator, field_validator
from dailywire_api.records.BaseRecord import BaseRecord

class ThumbnailRecord(BaseRecord):
    landscape: str | None = Field(default=None, validation_alias="land")
    portrait: str | None = Field(default=None, validation_alias="port")
    square: str | None = None

    # The API sometimes sends "" for missing images; normalize that to None.
    @field_validator("landscape", "portrait", "square", mode="before")
    @classmethod
    def empty_string_to_none(cls, v: Any):
        return None if isinstance(v, str) and v.strip() == "" else v