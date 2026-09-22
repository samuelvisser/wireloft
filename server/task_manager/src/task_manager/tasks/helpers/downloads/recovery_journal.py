from __future__ import annotations

import hashlib
import logging
import os
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from backend.db import get_session
from backend.db.models.DownloadPathClaim import DownloadPathClaim

logger = logging.getLogger(__name__)


class DownloadPathClaimType(StrEnum):
    DIRECT_RESERVATION = "direct_reservation"
    PUBLICATION_LOCK = "publication_lock"


@dataclass(frozen=True)
class DownloadPathClaimRecord:
    id: str
    claim_type: DownloadPathClaimType
    candidate_path: Path


def _canonical_candidate_path(candidate: str | Path) -> Path:
    return Path(os.path.abspath(Path(candidate).expanduser()))


def _claim_id(candidate: Path) -> str:
    return hashlib.sha256(os.fsencode(candidate)).hexdigest()


def create_download_path_claim(
    claim_type: DownloadPathClaimType,
    candidate: str | Path,
) -> DownloadPathClaimRecord | None:
    """Persist a claim before its filesystem marker is created.

    The candidate path digest is the primary key, so two workers cannot journal
    the same destination at once even when they use different download modes.
    Returning ``None`` means another durable claim already owns this candidate.
    """
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


def delete_download_path_claim(record_id: str) -> bool:
    """Best-effort removal after the filesystem marker has been released.

    A failed database cleanup is safe: the stale row points to a marker that no
    longer exists and startup recovery will remove the row on the next restart.
    """
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


def list_download_path_claims(
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
