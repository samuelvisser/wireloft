from datetime import datetime

from sqlalchemy import CheckConstraint, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.db import Base
from backend.db.datetime_types import UTCDateTime


class DownloadPathClaim(Base):
    """Durable pointer to one temporary filesystem claim owned by WireLoft."""

    __tablename__ = "download_path_claims"
    __table_args__ = (
        CheckConstraint(
            "claim_type IN ('direct_reservation', 'publication_lock')",
            name="claim_type",
        ),
    )

    # The id is the SHA-256 digest of the canonical candidate path. Using the
    # digest as the key serializes all WireLoft claim types for one destination
    # without requiring a potentially very long filesystem path to be indexed.
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    claim_type: Mapped[str] = mapped_column(String(32), nullable=False)
    candidate_path: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        server_default=func.now(),
        nullable=False,
    )
