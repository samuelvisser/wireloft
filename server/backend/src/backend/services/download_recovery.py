from __future__ import annotations

from datetime import datetime
from collections.abc import Callable
from pathlib import Path

from backend.db import get_session
from dailywire_downloader.storage import temporary
from dailywire_downloader.storage.identity import ArtifactIdentity, inspect_artifact
from dailywire_downloader.storage.replacement import reconcile_abandoned_replacements


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
    return (
        temporary.cleanup_abandoned_temporary_downloads(
            temporary_root, download_root, is_committed=_is_committed_download_artifact,
        )
        + temporary.cleanup_abandoned_destination_workspaces(
            download_root, is_committed=_is_committed_download_artifact,
        )
    )


def _commit_abandoned_replacement(
    record: dict,
    replay: Callable[[], bool],
) -> bool:
    """Reconcile one replacement during the existing paused startup recovery.

    Database ownership is verified before *any* filesystem changes. The durable
    journal stays on disk until both the atomic renames and this commit succeed.
    Repeated startup attempts may safely replay an interrupted publication.
    """
    from backend.db.models.media_download import EpisodeMediaDownload, MediaDownloadAsset, MediaDownloadBase
    from backend.services.media_download_history import record_media_download_history
    from backend.types.download_profile_types import MediaDownloadArtifactStatus
    from backend.types.media_download_history_types import MediaDownloadHistoryAction

    session = get_session()
    try:
        download = session.get(MediaDownloadBase, record["media_download_id"])
        media_record = record["media"]
        if download is None or download.file_path != media_record["path"]:
            return False

        recorded = (download.artifact_size_bytes, download.artifact_fingerprint)
        old_identity = media_record["old"]
        new_identity = media_record["new"]
        old = (old_identity["size_bytes"], old_identity["fingerprint"])
        new = (new_identity["size_bytes"], new_identity["fingerprint"])
        replacement_time = datetime.fromisoformat(record["downloaded_at"])
        committed = (
            recorded == new
            and download.artifact_status == MediaDownloadArtifactStatus.AVAILABLE.value
            and download.downloaded_at is not None
            and download.downloaded_at >= replacement_time
        )
        # A second download of identical content can have the same fingerprint.
        # The timestamp distinguishes this pending attempt from an artifact
        # committed by a different, newer operation.
        if recorded not in {old, new}:
            return False
        if (
            download.downloaded_at is not None
            and download.downloaded_at > replacement_time
            and not committed
        ):
            return False
        if download.automatic_retry_suppressed and not committed:
            return False

        if not replay():
            return False

        final_media_identity = inspect_artifact(media_record["path"])
        if (final_media_identity.size_bytes, final_media_identity.fingerprint) != new:
            return False
        for entry in record["assets"]:
            identity = inspect_artifact(entry["path"])
            if (identity.size_bytes, identity.fingerprint) != (
                entry["new"]["size_bytes"], entry["new"]["fingerprint"],
            ):
                return False

        if committed:
            # A previous run committed successfully but crashed before removing
            # the journal; no additional download history event is necessary.
            return True

        download.artifact_stat_dev = final_media_identity.stat_dev
        download.artifact_stat_ino = final_media_identity.stat_ino
        download.artifact_size_bytes = final_media_identity.size_bytes
        download.artifact_fingerprint = final_media_identity.fingerprint
        download.artifact_status = MediaDownloadArtifactStatus.AVAILABLE.value
        download.artifact_error = None
        download.automatic_retry_suppressed = False
        download.downloaded_bytes = record["downloaded_bytes"]
        download.format_downloaded = record["format_downloaded"]
        download.downloaded_at = replacement_time
        if isinstance(download, EpisodeMediaDownload):
            download.downloaded_publish_status = record["downloaded_publish_status"]

        download.assets.clear()
        session.flush()
        for entry in record["assets"]:
            download.assets.append(MediaDownloadAsset(
                asset_key=entry["asset_key"],
                kind=entry["kind"],
                path=entry["path"],
                suffix=entry["suffix"],
                size_bytes=entry["new"]["size_bytes"],
                fingerprint=entry["new"]["fingerprint"],
            ))

        record_media_download_history(
            session,
            download.id,
            MediaDownloadHistoryAction.COMPLETED,
            metadata={
                "is_redownload": True,
                "recovered_after_restart": True,
                "file_path": download.file_path,
                "downloaded_bytes": download.downloaded_bytes,
                "format_downloaded": download.format_downloaded,
            },
            occurred_at=replacement_time,
        )
        session.commit()
        return True
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def recover_abandoned_download_replacements(download_root: str | Path) -> int:
    """Use the established startup filesystem recovery for interrupted swaps."""
    return reconcile_abandoned_replacements(
        download_root, recover=_commit_abandoned_replacement,
    )
