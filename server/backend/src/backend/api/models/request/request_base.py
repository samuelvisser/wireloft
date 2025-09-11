from __future__ import annotations

from pydantic import BaseModel, AliasGenerator
from pydantic.alias_generators import to_camel, to_snake


class RequestModel(BaseModel):
    """Base class for API request models with camelCase JSON output via aliases."""

    def __init__(self):
        super().__init__()

        self.model_config.setdefault('alias_generator', AliasGenerator(
            serialization_alias=to_snake,
            validation_alias=to_camel,
        ))