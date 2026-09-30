from __future__ import annotations

from pathlib import Path

from backend.db import get_session
from dailywire_downloader.storage.identity import ArtifactIdentity
from dailywire_downloader.storage import temporary


def _is_committed_download_artifact(path: Path, identity: ArtifactIdentity) -> bool:
    """Return whether the database owns this exact published media content."""
    from sqlalchemy import select

    from backend.db.models.media_download import MediaDownloadBase
    from backend.types.download_profile_types import MediaDownloadArtifactStatus

    session = get_session()
    try:
        statement = (
            select(
                MediaDownloadBase.artifact_stat_dev,
                MediaDownloadBase.artifact_stat_ino,
                MediaDownloadBase.artifact_size_bytes,
                MediaDownloadBase.artifact_fingerprint,
            )
            .where(
                MediaDownloadBase.file_path == str(path),
                MediaDownloadBase.artifact_status == MediaDownloadArtifactStatus.AVAILABLE.value,
            )
        )
        for row in session.execute(statement):
            # Content identity is the portable path for NAS/network filesystems,
            # whose inode/device identifiers may change between mounts. Keep the
            # filesystem identity fast path for older rows without a fingerprint.
            if (
                row.artifact_size_bytes == identity.size_bytes
                and row.artifact_fingerprint
                and row.artifact_fingerprint == identity.fingerprint
            ):
                return True
            if (
                row.artifact_stat_dev == identity.stat_dev
                and row.artifact_stat_ino == identity.stat_ino
            ):
                return True
        return False
    finally:
        session.close()


def cleanup_abandoned_temporary_downloads(temporary_root: str | Path, download_root: str | Path) -> int:
    """Supply database ownership to the standalone filesystem reconciler."""
    return temporary.cleanup_abandoned_temporary_downloads(
        temporary_root, download_root, is_committed=_is_committed_download_artifact,
    )
