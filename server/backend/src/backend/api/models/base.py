from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, AliasGenerator
from pydantic import ConfigDict
from pydantic.alias_generators import to_camel, to_snake

from backend.api.datetime import api_datetime


class ResponseBase(BaseModel):
    """Base class for API response models with camelCase JSON output via aliases."""

    model_config = ConfigDict(
        alias_generator=AliasGenerator(
            serialization_alias=to_camel,
            validation_alias=to_snake,
        ),
        populate_by_name=True,
        from_attributes=True,
        extra='ignore',
        use_enum_values=True,
        json_encoders={datetime: api_datetime},
    )


class RequestBase(BaseModel):
    """Base class for API request models with camelCase input and snake_case serialization."""

    model_config = ConfigDict(
        alias_generator=AliasGenerator(
            serialization_alias=to_snake,
            validation_alias=to_camel,
        ),
        populate_by_name=True,
        from_attributes=True,
        extra='ignore',
        use_enum_values=True
    )