from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from backend.db.models import Show
from backend.db.models.Metadata import Metadata
from backend.db.models.media_item import Movie
from backend.utils.custom_metadata import (
    CUSTOM_METADATA_DB_PREFIX,
    CustomMetadataScope,
    custom_metadata_storage_key,
    is_valid_custom_metadata_key,
)


_PARENT_TABLE_BY_SCOPE: dict[CustomMetadataScope, str] = {
    "show": Show.__tablename__,
    "movie": Movie.__tablename__,
}


def get_custom_metadata_fields(
    session: Session,
    scope: CustomMetadataScope,
) -> list[str]:
    """Return every valid shared custom metadata field for one media scope."""
    parent_table = _PARENT_TABLE_BY_SCOPE[scope]
    rows = session.scalars(
        select(Metadata.key)
        .where(
            Metadata.parent_table == parent_table,
            Metadata.key.like(f"{CUSTOM_METADATA_DB_PREFIX}%"),
        )
        .distinct()
        .order_by(Metadata.key)
    ).all()

    fields: list[str] = []
    for storage_key in rows:
        key = storage_key[len(CUSTOM_METADATA_DB_PREFIX):]
        if is_valid_custom_metadata_key(key):
            fields.append(key)
    return fields


def remove_shared_custom_metadata_fields(
    session: Session,
    resource: Show | Movie,
    *,
    parent_table: str,
    fields: list[str],
) -> None:
    """Delete fields and all of their values for one metadata owner type."""
    if not fields:
        return

    storage_keys = [custom_metadata_storage_key(key) for key in fields]
    session.execute(
        delete(Metadata).where(
            Metadata.parent_table == parent_table,
            Metadata.key.in_(storage_keys),
        )
    )
    session.flush()
    # HasMetadataMixin uses a selectin-loaded collection. Reload the current
    # resource before replacing its remaining values so globally deleted rows
    # cannot be reintroduced from a stale relationship collection.
    session.expire(resource, ["meta_items"])

