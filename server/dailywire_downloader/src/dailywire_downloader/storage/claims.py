from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol


class DownloadPathClaimType(StrEnum):
    DIRECT_RESERVATION = "direct_reservation"
    PUBLICATION_LOCK = "publication_lock"


@dataclass(frozen=True)
class DownloadPathClaimRecord:
    id: str
    claim_type: DownloadPathClaimType
    candidate_path: Path


class DownloadPathClaimJournal(Protocol):
    """Durable ownership journal supplied by the embedding application."""

    def create_claim(
        self,
        claim_type: DownloadPathClaimType,
        candidate: str | Path,
    ) -> DownloadPathClaimRecord | None:
        """Claim a candidate before creating its filesystem ownership marker."""
        ...

    def delete_claim(self, record_id: str) -> bool:
        """Release a durable claim after its filesystem marker is gone."""
        ...

    def list_claims(
        self,
        claim_type: DownloadPathClaimType,
    ) -> list[DownloadPathClaimRecord]:
        """Return durable claims of one type for targeted crash recovery."""
        ...
