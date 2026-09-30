from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.db import Base


class DownloadBatchItem(Base):
    """Durable, size-weighted child ownership for a batch execution.

    The complete target set is inserted before destructive preparation. Recovery
    reuses a prepared child instead of deleting a successfully replaced file.
    A missing child is an error, never permission to create another replacement.
    """
    __tablename__ = "download_batch_items"
    __table_args__ = (UniqueConstraint("owner_key", "media_download_id", name="uq_download_batch_target"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    owner_key: Mapped[str] = mapped_column(String(80), index=True)
    owner_run_id: Mapped[int | None] = mapped_column(ForeignKey("task_runs.id", ondelete="SET NULL"), index=True)
    owner_operation_id: Mapped[str | None] = mapped_column(ForeignKey("task_operations.id", ondelete="CASCADE"), index=True)
    media_download_id: Mapped[int]
    title: Mapped[str] = mapped_column(Text)
    weight: Mapped[int] = mapped_column(BigInteger)
    child_operation_id: Mapped[str | None] = mapped_column(ForeignKey("task_operations.id", ondelete="SET NULL"))
    owns_operation: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    prepared: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    error: Mapped[str | None] = mapped_column(Text)
