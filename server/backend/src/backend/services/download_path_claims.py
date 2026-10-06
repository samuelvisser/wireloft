from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from backend.db import get_session
from backend.db.models.DownloadPathClaim import DownloadPathClaim
from dailywire_downloader.storage.claims import (
    DownloadPathClaimRecord,
    DownloadPathClaimType,
)

logger = logging.getLogger(__name__)


def _canonical_candidate_path(candidate: str | Path) -> Path:
    return Path(os.path.abspath(Path(candidate).expanduser()))


def _claim_id(candidate: Path) -> str:
    return hashlib.sha256(os.fsencode(candidate)).hexdigest()


class DatabaseDownloadPathClaimJournal:
    """Persist download-path ownership without coupling the downloader to SQLAlchemy."""

    def create_claim(
        self,
        claim_type: DownloadPathClaimType,
        candidate: str | Path,
    ) -> DownloadPathClaimRecord | None:
        canonical = _canonical_candidate_path(candidate)
        record_id = _claim_id(canonical)
        session = get_session()
        try:
            row = DownloadPathClaim(
                id=record_id,
                claim_type=claim_type.value,
                candidate_path=str(canonical),
            )
            session.add(row)
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                existing = session.get(DownloadPathClaim, record_id)
                if existing is not None and existing.candidate_path != str(canonical):
                    raise RuntimeError(
                        "Download path claim digest collision for distinct filesystem paths"
                    )
                return None
            return DownloadPathClaimRecord(
                id=record_id,
                claim_type=claim_type,
                candidate_path=canonical,
            )
        finally:
            session.close()

    def delete_claim(self, record_id: str) -> bool:
        """Best-effort cleanup; a stale row is safe and will be retried at startup."""
        session = get_session()
        try:
            row = session.get(DownloadPathClaim, record_id)
            if row is None:
                return True
            session.delete(row)
            try:
                session.commit()
            except Exception:
                session.rollback()
                logger.warning(
                    "Could not remove completed download path claim '%s'",
                    record_id,
                    exc_info=True,
                )
                return False
            return True
        finally:
            session.close()

    def list_claims(
        self,
        claim_type: DownloadPathClaimType,
    ) -> list[DownloadPathClaimRecord]:
        session = get_session()
        try:
            rows = session.execute(
                select(DownloadPathClaim)
                .where(DownloadPathClaim.claim_type == claim_type.value)
                .order_by(DownloadPathClaim.created_at, DownloadPathClaim.id)
            ).scalars()
            return [
                DownloadPathClaimRecord(
                    id=row.id,
                    claim_type=DownloadPathClaimType(row.claim_type),
                    candidate_path=Path(row.candidate_path),
                )
                for row in rows
            ]
        finally:
            session.close()


database_download_path_claims = DatabaseDownloadPathClaimJournal()
