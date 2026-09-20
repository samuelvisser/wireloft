from __future__ import annotations

from datetime import datetime

from pydantic import AliasChoices, AliasGenerator, AliasPath, BaseModel, ConfigDict
from pydantic.alias_generators import to_camel, to_snake

from backend.api.datetime import api_datetime


def response_model_config(*, nested_source: str | None = None) -> ConfigDict:
    """Build the shared response config, optionally accepting fields from a nested source."""
    validation_alias = (
        to_snake
        if nested_source is None
        else lambda name: AliasChoices(
            to_snake(name),
            AliasPath(nested_source, to_snake(name)),
        )
    )
    return ConfigDict(
        alias_generator=AliasGenerator(
            serialization_alias=to_camel,
            validation_alias=validation_alias,
        ),
        populate_by_name=True,
        from_attributes=True,
        extra="ignore",
        use_enum_values=True,
        json_encoders={datetime: api_datetime},
    )


class ResponseBase(BaseModel):
    """Base class for API response models with camelCase JSON output via aliases."""

    model_config = response_model_config()


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