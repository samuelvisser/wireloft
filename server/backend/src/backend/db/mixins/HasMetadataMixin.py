from sqlalchemy import event
from sqlalchemy.orm import declared_attr, Mapped, Session

from backend.db.models.Metadata import Metadata


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