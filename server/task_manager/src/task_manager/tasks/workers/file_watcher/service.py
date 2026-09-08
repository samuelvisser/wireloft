from __future__ import annotations

from dataclasses import dataclass, replace
import logging
import os
import stat
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from backend.db.models.media_download import MediaDownloadBase
from backend.types.download_profile_types import MediaDownloadArtifactStatus
from backend.utils.artifact_identity import ArtifactIdentity, inspect_artifact
from config import get_settings

from ._helpers import TrackedDownloadSnapshot, get_tracked_downloads

logger = logging.getLogger(__name__)

_HEALTHY_STATUS = MediaDownloadArtifactStatus.AVAILABLE.value
_PROBLEM_STATUSES = (
    MediaDownloadArtifactStatus.MISSING.value,
    MediaDownloadArtifactStatus.CORRUPTED.value,
)
_MIN_SIZE_RATIO = 0.5
_TEMPORARY_SUFFIXES = (".part", ".rawts")


@dataclass(frozen=True)
class _RenamedArtifact:
    path: str
    identity: ArtifactIdentity


async def run_file_watcher(
    s: Session,
    *,
    show_id: Optional[int] = None,
    show_slug: Optional[str] = None,
    progress=None,
) -> None:
    """Reconcile persistent MediaDownload artifact facts with the filesystem.

    Database access is intentionally split from filesystem access. The watcher
    first copies the required database facts into detached snapshots and closes
    that read transaction. All potentially slow local/SMB/NFS filesystem work
    then runs without a database transaction. A final short write transaction
    applies results only when the database row still matches the snapshot.
    """
    settings = get_settings().file_watcher
    if not settings.enabled:
        print("file_watcher is disabled (file_watcher.enabled=false), skipping")
        return

    print("Starting file_watcher")
    downloads = get_tracked_downloads(s, show_id=show_id, show_slug=show_slug)

    # SELECT starts SQLAlchemy's implicit transaction. End it before any stat,
    # directory scan, or fingerprint read can block on a local/network filesystem.
    # The detached dataclass snapshots remain usable without the Session.
    s.commit()

    changes: list[tuple[TrackedDownloadSnapshot, TrackedDownloadSnapshot]] = []
    for download in downloads:
        reconciled = _reconcile(
            download,
            verify_file_size=settings.verify_file_size,
        )
        if reconciled != download:
            changes.append((download, reconciled))

    updated = _apply_reconciliations(s, changes)
    print(f"file_watcher completed: checked {len(downloads)} artifact(s), updated {updated}")


def _reconcile(
    download: TrackedDownloadSnapshot,
    *,
    verify_file_size: bool,
) -> TrackedDownloadSnapshot:
    path = download.file_path
    try:
        path_stat = os.stat(path)
    except FileNotFoundError:
        renamed, rename_error = _find_same_directory_rename(download)
        if renamed is not None:
            reconciled = replace(download, file_path=renamed.path)
            reconciled = _set_identity(reconciled, renamed.identity)
            problem = _size_problem(
                reconciled,
                size=renamed.identity.size_bytes,
                verify_file_size=verify_file_size,
            )
            if problem is None:
                return replace(
                    reconciled,
                    artifact_status=_HEALTHY_STATUS,
                    artifact_error=None,
                )
            status, message = problem
            return _apply_problem(reconciled, status, message)

        message = f"File not found at '{path}'"
        if rename_error:
            message = f"{message}; {rename_error}"
        return _apply_problem(download, MediaDownloadArtifactStatus.MISSING, message)
    except OSError as exc:
        return _apply_problem(
            download,
            MediaDownloadArtifactStatus.MISSING,
            f"Could not check '{path}': {exc}",
        )

    if not stat.S_ISREG(path_stat.st_mode):
        return _apply_problem(
            download,
            MediaDownloadArtifactStatus.CORRUPTED,
            f"Expected a file at '{path}' but found something else",
        )

    reconciled = download
    if not _has_complete_identity(reconciled):
        try:
            identity = inspect_artifact(path)
        except FileNotFoundError:
            return _apply_problem(
                reconciled,
                MediaDownloadArtifactStatus.MISSING,
                f"File not found at '{path}'",
            )
        except (OSError, ValueError) as exc:
            return _apply_problem(
                reconciled,
                MediaDownloadArtifactStatus.MISSING,
                f"Could not check '{path}': {exc}",
            )
        reconciled = _set_identity(reconciled, identity)

    problem = _size_problem(
        reconciled,
        size=path_stat.st_size,
        verify_file_size=verify_file_size,
    )
    if problem is not None:
        status, message = problem
        return _apply_problem(reconciled, status, message)

    if reconciled == download:
        reconciled = _refresh_filesystem_identity_if_content_matches(
            reconciled,
            path_stat=path_stat,
        )

    if reconciled.artifact_status in _PROBLEM_STATUSES:
        return replace(
            reconciled,
            artifact_status=_HEALTHY_STATUS,
            artifact_error=None,
        )

    return reconciled


def _size_problem(
    download: TrackedDownloadSnapshot,
    *,
    size: int,
    verify_file_size: bool,
) -> Optional[tuple[MediaDownloadArtifactStatus, str]]:
    path = download.file_path
    if size == 0:
        return MediaDownloadArtifactStatus.CORRUPTED, f"File at '{path}' is empty"

    if verify_file_size and download.downloaded_bytes and size < download.downloaded_bytes * _MIN_SIZE_RATIO:
        return MediaDownloadArtifactStatus.CORRUPTED, (
            f"File at '{path}' is only {size} bytes, well under the "
            f"{download.downloaded_bytes} recorded when it finished downloading"
        )
    return None


def _has_complete_identity(download: TrackedDownloadSnapshot) -> bool:
    return (
        bool(download.artifact_stat_dev)
        and bool(download.artifact_stat_ino)
        and download.artifact_size_bytes is not None
        and bool(download.artifact_fingerprint)
    )


def _refresh_filesystem_identity_if_content_matches(
    download: TrackedDownloadSnapshot,
    *,
    path_stat: os.stat_result,
) -> TrackedDownloadSnapshot:
    """Refresh volatile filesystem IDs only when durable identity still matches."""
    stat_dev = str(path_stat.st_dev)
    stat_ino = str(path_stat.st_ino)
    if stat_dev == download.artifact_stat_dev and stat_ino == download.artifact_stat_ino:
        return download
    if path_stat.st_size != download.artifact_size_bytes:
        return download

    try:
        identity = inspect_artifact(download.file_path)
    except (OSError, ValueError):
        return download
    if identity.fingerprint != download.artifact_fingerprint:
        return download

    return replace(
        download,
        artifact_stat_dev=identity.stat_dev,
        artifact_stat_ino=identity.stat_ino,
    )


def _find_same_directory_rename(
    download: TrackedDownloadSnapshot,
) -> tuple[Optional[_RenamedArtifact], Optional[str]]:
    original = Path(download.file_path)
    parent = original.parent
    candidates: list[tuple[str, os.stat_result]] = []

    try:
        with os.scandir(parent) as entries:
            for entry in entries:
                if entry.name.endswith(_TEMPORARY_SUFFIXES):
                    continue
                try:
                    candidate_stat = entry.stat(follow_symlinks=False)
                except OSError:
                    continue
                if stat.S_ISREG(candidate_stat.st_mode):
                    candidates.append((entry.path, candidate_stat))
    except OSError as exc:
        return None, f"could not scan '{parent}' for a same-directory rename: {exc}"

    size_candidates = [
        candidate
        for candidate in candidates
        if candidate[1].st_size == download.artifact_size_bytes
    ]
    if not size_candidates:
        return None, None

    # Try filesystem IDs first so a normal local rename hashes only one
    # candidate. The fingerprint still confirms it, protecting against inode
    # reuse and filesystems that report weak identifiers such as zero.
    inode_candidates = [
        candidate
        for candidate in size_candidates
        if str(candidate[1].st_dev) == download.artifact_stat_dev
        and str(candidate[1].st_ino) == download.artifact_stat_ino
    ]
    if len(inode_candidates) == 1:
        inode_match = _inspect_matching_candidate(download, inode_candidates[0][0])
        if inode_match is not None:
            return inode_match, None

    fingerprint_matches = _fingerprint_matches(download, size_candidates)
    if len(fingerprint_matches) == 1:
        return fingerprint_matches[0], None
    if len(fingerprint_matches) > 1:
        return None, f"multiple files in '{parent}' have the same artifact fingerprint"
    return None, None


def _inspect_matching_candidate(
    download: TrackedDownloadSnapshot,
    candidate_path: str,
) -> Optional[_RenamedArtifact]:
    try:
        identity = inspect_artifact(candidate_path)
    except (OSError, ValueError):
        return None
    if identity.size_bytes != download.artifact_size_bytes:
        return None
    if identity.fingerprint != download.artifact_fingerprint:
        return None
    return _RenamedArtifact(path=candidate_path, identity=identity)


def _fingerprint_matches(
    download: TrackedDownloadSnapshot,
    candidates: list[tuple[str, os.stat_result]],
) -> list[_RenamedArtifact]:
    matches: list[_RenamedArtifact] = []
    for candidate_path, _candidate_stat in candidates:
        match = _inspect_matching_candidate(download, candidate_path)
        if match is not None:
            matches.append(match)
    return matches


def _set_identity(
    download: TrackedDownloadSnapshot,
    identity: ArtifactIdentity,
) -> TrackedDownloadSnapshot:
    return replace(
        download,
        artifact_stat_dev=identity.stat_dev,
        artifact_stat_ino=identity.stat_ino,
        artifact_size_bytes=identity.size_bytes,
        artifact_fingerprint=identity.fingerprint,
    )


def _apply_problem(
    download: TrackedDownloadSnapshot,
    status: MediaDownloadArtifactStatus,
    message: str,
) -> TrackedDownloadSnapshot:
    if download.artifact_status == status.value and download.artifact_error == message:
        return download
    return replace(
        download,
        artifact_status=status.value,
        artifact_error=message,
    )


def _apply_reconciliations(
    s: Session,
    changes: list[tuple[TrackedDownloadSnapshot, TrackedDownloadSnapshot]],
) -> int:
    if not changes:
        return 0

    updated = 0
    table = MediaDownloadBase.__table__
    with s.begin():
        for original, reconciled in changes:
            stmt = (
                table.update()
                .where(
                    table.c.id == original.id,
                    _matches_snapshot_value(table.c.file_path, original.file_path),
                    _matches_snapshot_value(table.c.artifact_status, original.artifact_status),
                    _matches_snapshot_value(table.c.artifact_error, original.artifact_error),
                    _matches_snapshot_value(table.c.downloaded_bytes, original.downloaded_bytes),
                    _matches_snapshot_value(table.c.artifact_stat_dev, original.artifact_stat_dev),
                    _matches_snapshot_value(table.c.artifact_stat_ino, original.artifact_stat_ino),
                    _matches_snapshot_value(table.c.artifact_size_bytes, original.artifact_size_bytes),
                    _matches_snapshot_value(table.c.artifact_fingerprint, original.artifact_fingerprint),
                )
                .values(
                    file_path=reconciled.file_path,
                    artifact_status=reconciled.artifact_status,
                    artifact_error=reconciled.artifact_error,
                    artifact_stat_dev=reconciled.artifact_stat_dev,
                    artifact_stat_ino=reconciled.artifact_stat_ino,
                    artifact_size_bytes=reconciled.artifact_size_bytes,
                    artifact_fingerprint=reconciled.artifact_fingerprint,
                )
            )
            result = s.execute(stmt)
            if result.rowcount == 1:
                updated += 1
                _log_applied_change(original, reconciled)
            else:
                logger.info(
                    "file_watcher: skipped stale result for media_download %s because the row changed while filesystem checks were running",
                    original.id,
                )

    return updated


def _matches_snapshot_value(column, value):
    if value is None:
        return column.is_(None)
    return column == value


def _log_applied_change(
    original: TrackedDownloadSnapshot,
    reconciled: TrackedDownloadSnapshot,
) -> None:
    if original.file_path != reconciled.file_path:
        logger.info(
            "file_watcher: media_download %s renamed %s -> %s",
            original.id,
            original.file_path,
            reconciled.file_path,
        )

    if reconciled.artifact_status in _PROBLEM_STATUSES and (
        original.artifact_status != reconciled.artifact_status
        or original.artifact_error != reconciled.artifact_error
    ):
        logger.warning(
            "file_watcher: media_download %s -> %s (%s)",
            original.id,
            reconciled.artifact_status,
            reconciled.artifact_error,
        )
    elif original.artifact_status in _PROBLEM_STATUSES and reconciled.artifact_status == _HEALTHY_STATUS:
        logger.info("file_watcher: media_download %s file is healthy again", original.id)
    elif (
        original.artifact_stat_dev != reconciled.artifact_stat_dev
        or original.artifact_stat_ino != reconciled.artifact_stat_ino
    ):
        logger.info(
            "file_watcher: refreshed filesystem identity for media_download %s",
            original.id,
        )
