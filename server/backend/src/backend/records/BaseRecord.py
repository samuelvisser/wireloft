from pydantic import BaseModel, ConfigDict


class BaseRecord(BaseModel):
    """Base Pydantic record for backend API responses/inputs.

    Mirrors dailywire_api.records.BaseRecord behavior for aliases and immutability
    so our API behaves consistently.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="ignore",
        validate_by_name=True,
        validate_by_alias=True,
        serialize_by_alias=True
    )
