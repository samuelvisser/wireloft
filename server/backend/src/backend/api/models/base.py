from __future__ import annotations

from pydantic import BaseModel, AliasGenerator
from pydantic import ConfigDict
from pydantic.alias_generators import to_camel, to_snake


class ResponseBase(BaseModel):
    """Base class for API response models with camelCase JSON output via aliases."""

    model_config = ConfigDict(
        alias_generator=AliasGenerator(
            serialization_alias=to_camel,
            validation_alias=to_snake,
        ),
        populate_by_name=True,
        from_attributes=True,
        extra='ignore'
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
        extra='ignore'
    )