from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from pydantic import BaseModel
from sqlalchemy.orm import DeclarativeBase


T = TypeVar("T", bound=DeclarativeBase)


def _values(
    data: BaseModel | Mapping[str, Any],
    *,
    exclude_none: bool = False,
    exclude_defaults: bool = False,
) -> dict[str, Any]:
    if isinstance(data, BaseModel):
        return data.model_dump(
            by_alias=True,
            exclude_none=exclude_none,
            exclude_defaults=exclude_defaults,
        )
    return dict(data)


def create_database_fields(
    model_cls: type[T],
    data: BaseModel | Mapping[str, Any],
    *,
    exclude_fields: set[str] | None = None,
) -> T:
    """Create an ORM model from fields that actually belong to its mapper."""
    values = _values(data)
    excluded = exclude_fields or set()
    valid_keys = set(model_cls.__mapper__.column_attrs.keys())
    return model_cls(
        **{
            key: value
            for key, value in values.items()
            if key in valid_keys and key not in excluded
        }
    )


def update_database_fields(
    db_model: T,
    data: BaseModel | Mapping[str, Any],
    *,
    exclude_fields: set[str] | None = None,
    ignore_extra_fields: bool = False,
    exclude_none: bool = False,
    exclude_defaults: bool = False,
) -> T:
    """Apply validated or mapped values to an ORM object without HTTP coupling."""
    values = _values(
        data,
        exclude_none=exclude_none,
        exclude_defaults=exclude_defaults,
    )
    excluded = exclude_fields or set()
    for field, value in values.items():
        if field in excluded:
            continue
        if not hasattr(db_model, field):
            if ignore_extra_fields:
                continue
            raise ValueError(
                f"Field {field!r} does not exist on {type(db_model).__name__}"
            )
        setattr(db_model, field, value)
    return db_model
