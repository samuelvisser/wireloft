from typing import TypeVar, Type

from fastapi import HTTPException

from pydantic import BaseModel as APIModel
from backend.db import Base as DatabaseModel

T = TypeVar("T", bound=DatabaseModel)

# Makes sure to map only fields that exist in the database. Silently ignores extra fields.
def create_database_fields(model_cls: Type[T], data: dict, *,
                           exclude_fields: set[str] | None = None
                           ) -> T:
    if exclude_fields:
        data = {k: v for k, v in data.items() if k not in exclude_fields}
    valid_keys = model_cls.__mapper__.attrs.keys()
    filtered = {k: v for k, v in data.items() if k in valid_keys}
    return model_cls(**filtered)


# Makes sure to map only fields that exist in the database. Throws error if extra fields.
def update_database_fields(db_model: T, data: APIModel, *,
                           exclude_fields: set[str] | None = None,
                           ignore_extra_fields=False
                           ) -> T:
    updates = data.model_dump(by_alias=True)
    if exclude_fields:
        updates = {k: v for k, v in updates.items() if k not in exclude_fields}
    for field, value in updates.items():
        if not hasattr(db_model, field):
            if ignore_extra_fields:
                continue
            raise HTTPException(status_code=422, detail=f"Field {field} does not exist in database")
        setattr(db_model, field, value)
    return db_model