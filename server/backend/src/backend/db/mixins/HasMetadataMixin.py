from collections.abc import Mapping

from sqlalchemy import event
from sqlalchemy.orm import declared_attr, Mapped

from backend.db.models.Metadata import Metadata
from backend.utils.custom_metadata import (
    CUSTOM_METADATA_DB_PREFIX,
    custom_metadata_storage_key,
    is_valid_custom_metadata_key,
)


class HasMetadataMixin:
    # Create a basic SQLAlchemy relationship to the Metadata table
    @declared_attr
    def meta_items(cls) -> Mapped[list[Metadata]]:
        from sqlalchemy import and_, literal
        from sqlalchemy.orm import relationship, foreign

        return relationship(
            Metadata,
            primaryjoin=lambda: and_(
                foreign(Metadata.parent_id) == cls.id,
                Metadata.parent_table == literal(cls.__tablename__),
            ),
            cascade="all, delete-orphan",
            lazy="selectin",
            overlaps="meta_items"
        )

    def set_meta(self, key: str, value: str | None):
        for m in self.meta_items:
            if m.key == key:
                m.value = value
                return m
        m = Metadata(key=key, value=value)
        self.meta_items.append(m)
        return m

    def get_meta(self, key: str) -> str | None:
        for m in self.meta_items:
            if m.key == key:
                return m.value
        return None

    @property
    def custom_metadata(self) -> dict[str, str]:
        """Return only user-editable metadata, isolated from WireLoft internal keys."""
        result: dict[str, str] = {}
        for item in self.meta_items:
            if not item.key.startswith(CUSTOM_METADATA_DB_PREFIX):
                continue
            key = item.key[len(CUSTOM_METADATA_DB_PREFIX):]
            if is_valid_custom_metadata_key(key):
                result[key] = item.value
        return result

    def replace_custom_metadata(self, values: Mapping[str, str]) -> None:
        """Replace this item's custom values without touching WireLoft metadata."""
        storage_values = {
            custom_metadata_storage_key(key): value
            for key, value in values.items()
        }
        current = {
            item.key: item
            for item in self.meta_items
            if item.key.startswith(CUSTOM_METADATA_DB_PREFIX)
        }

        for storage_key, item in list(current.items()):
            if storage_key not in storage_values:
                self.meta_items.remove(item)

        for storage_key, value in storage_values.items():
            item = current.get(storage_key)
            if item is None:
                self.meta_items.append(Metadata(key=storage_key, value=value))
            else:
                item.value = value


def _on_append(parent, meta, initiator):
    meta.parent_table = parent.__class__.__tablename__

    # If the parent already has a DB identity (it already exists in the db), set it now:
    if getattr(parent, "id", None) is not None:
        meta.parent_id = parent.id


@event.listens_for(HasMetadataMixin, "mapper_configured", propagate=True)
def _wire_meta_events(mapper, cls):
    # cls is now a mapped subclass (e.g., Show, Episode)
    attr = getattr(cls, "meta_items")     # InstrumentedAttribute
    event.listen(attr, "append", _on_append, propagate=True)
