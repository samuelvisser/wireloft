from pydantic import BaseModel, ConfigDict, AliasGenerator
from pydantic.alias_generators import to_camel

from dailywire_api.utils.alias import to_camel_with_acronyms

class BaseRecord(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra='ignore',
        validate_by_name=True,
        validate_by_alias=True,
        serialize_by_alias=True,
        alias_generator=AliasGenerator(
            serialization_alias=to_camel,
            validation_alias=to_camel_with_acronyms,
        ),
    )