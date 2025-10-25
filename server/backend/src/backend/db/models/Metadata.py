from datetime import datetime

from sqlalchemy import DateTime, func, Index, UniqueConstraint
from sqlalchemy.orm import mapped_column, Mapped

from backend.db import Base


# Metadata table adds metadata to any record in the database
# If you want to add metadata to a specific table, use the HasMetadataMixin mixin to automatically generate the correct relationship
class Metadata(Base):
    __tablename__ = "metadata"
    __table_args__ = (
        Index("ix_metadata_parent", "parent_table", "parent_id"),
        UniqueConstraint("parent_table", "parent_id", "key", name="uq_metadata_parent_key"),
    )

    # Columns
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    parent_table: Mapped[str]
    parent_id: Mapped[int] = mapped_column(index=True)
    key: Mapped[str]
    value: Mapped[str]

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self):
        return f"<Metadata(id={self.id}, parent_table={self.parent_table}, parent_id={self.parent_id}, key={self.key}, value={self.value}, created_at={self.created_at}, updated_at={self.updated_at})>"

