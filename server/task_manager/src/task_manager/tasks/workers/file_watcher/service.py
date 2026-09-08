from __future__ import annotations

from dataclasses import dataclass
import logging
import os
import stat
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import set_committed_value

from backend.db.models.media_download import MediaDownloadBase
from backend.types.download_profile_types import MediaDownloadArtifactStatus
from backend.utils.artifact_identity import ArtifactIdentity, inspect_artifact
from config import get_settings

from ._helpers import get_tracked_downloads

logger = logging.getLogger(__name__)

_HEALTHY_STATUS = MediaDownloadArtifactStatus.AVAILABLE.value
_PROBLEM_STATUSES = (
    MediaDownloadArtifactStatus.MISSING.value,
    MediaDownloadArtifactStatus.CORRUPTED.value,
)
_MIN_SIZE_RATIO = 0.5
_TEMPORARY_SUFFIXES = (".part", ".rawts")
_ARTIFACT_GUARD_FIELDS = (
    "file_path",
    "artifact_status",
    "artifact_error",
    "downloaded_bytes",
    "artifact_stat_dev",
    "artifact_stat_ino",
    "artifact_size_bytes",
    "artifact_fingerprint",
)
_ArtifactUpdates = dict[str, str | int | None]


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
    loads MediaDownload ORM objects, detaches them, and closes the read
    transaction before any potentially slow local/SMB/NFS filesystem work.
    Reconciliation returns only proposed field updates, leaving each detached
    model unchanged so its original values can guard the final short write.
    """
    settings = get_settings().file_watcher
    if not settings.enabled:
        print("file_watcher is disabled (file_watcher.enabled=false), skipping")
        return

    print("Starting file_watcher")
    downloads = get_tracked_downloads(s, show_id=show_id, show_slug=show_slug)

    # SELECT starts SQLAlchemy's implicit transaction. Detach the fully loaded
    # MediaDownload objects before ending that transaction so their scalar
    # values remain available without any chance of lazy database access.
    for download in downloads:
        s.expunge(download)
    s.rollback()

    changes: list[tuple[MediaDownloadBase, _ArtifactUpdates]] = []
    for download in downloads:
        updates = _reconcile(
            download,
            verify_file_size=settings.verify_file_size,
        )
        if updates:
            changes.append((download, updates))

    updated = _apply_reconciliations(s, changes)
    print(f"file_watcher completed: checked {len(downloads)} artifact(s), updated {updated}")


def resolve_media_download_file(
    s: Session,
    download: MediaDownloadBase,
    *,
    verify_file_size: bool | None = None,
    release_read_transaction: bool = False,
) -> Path | None:
    """Return the current physical file, reconciling the artifact first when needed.

    This is the shared entrypoint for code that wants to consume an existing
    downloaded artifact. It deliberately uses the same reconciliation path as the
    scheduled FileWatcher, including same-directory rename discovery, identity
    refresh, missing/corrupted state transitions, and guarded database writeback.

    Read-only callers may set ``release_read_transaction`` so a transaction opened
    only to load the artifact is committed before any potentially slow filesystem
    I/O. The helper refuses to do that when SQLAlchemy still has pending ORM
    mutations, preserving ownership of wider write transactions.
    """
    if download.artifact_status == MediaDownloadArtifactStatus.ABSENT.value:
        return None

    if release_read_transaction:
        _release_clean_read_transaction(s)

    if verify_file_size is None:
        verify_file_size = get_settings().file_watcher.verify_file_size

    updates = _reconcile(download, verify_file_size=verify_file_size)
    if updates and not _apply_reconciliation_with_transaction(s, download, updates):
        return None

    path = Path(download.file_path)
    try:
        return path if path.is_file() else None
    except OSError:
        return None


def _release_clean_read_transaction(s: Session) -> bool:
    """End a caller's read transaction without expiring already-loaded objects."""
    if not s.in_transaction():
        return True
    if s.new or s.dirty or s.deleted:
        return False

    expire_on_commit = s.expire_on_commit
    s.expire_on_commit = False
    try:
        s.commit()
    finally:
        s.expire_on_commit = expire_on_commit
    return True


def _reconcile(
    download: MediaDownloadBase,
    *,
    verify_file_size: bool,
) -> _ArtifactUpdates:
    path = download.file_path
    try:
        path_stat = os.stat(path)
    except FileNotFoundError:
        renamed, rename_error = _find_same_directory_rename(download)
        if renamed is not None:
            values: _ArtifactUpdates = {
                "file_path": renamed.path,
                **_identity_values(renamed.identity),
            }
            problem = _size_problem(
                download,
                path=renamed.path,
                size=renamed.identity.size_bytes,
                verify_file_size=verify_file_size,
            )
            if problem is None:
                values.update(
                    artifact_status=_HEALTHY_STATUS,
                    artifact_error=None,
                )
            else:
                status, message = problem
                values.update(
                    artifact_status=status.value,
                    artifact_error=message,
                )
            return _changed_values(download, values)

        message = f"File not found at '{path}'"
        if rename_error:
            message = f"{message}; {rename_error}"
        return _problem_updates(download, MediaDownloadArtifactStatus.MISSING, message)
    except OSError as exc:
        return _problem_updates(
            download,
            MediaDownloadArtifactStatus.MISSING,
            f"Could not check '{path}': {exc}",
        )

    if not stat.S_ISREG(path_stat.st_mode):
        return _problem_updates(
            download,
            MediaDownloadArtifactStatus.CORRUPTED,
            f"Expected a file at '{path}' but found something else",
        )

    values: _ArtifactUpdates = {}
    identity_was_missing = not _has_complete_identity(download)
    if identity_was_missing:
        try:
            identity = inspect_artifact(path)
        except FileNotFoundError:
            return _problem_updates(
                download,
                MediaDownloadArtifactStatus.MISSING,
                f"File not found at '{path}'",
            )
        except (OSError, ValueError) as exc:
            return _problem_updates(
                download,
                MediaDownloadArtifactStatus.MISSING,
                f"Could not check '{path}': {exc}",
            )
        values.update(_identity_values(identity))

    problem = _size_problem(
        download,
        path=path,
        size=path_stat.st_size,
        verify_file_size=verify_file_size,
    )
    if problem is not None:
        status, message = problem
        values.update(
            artifact_status=status.value,
            artifact_error=message,
        )
        return _changed_values(download, values)

    if not identity_was_missing:
        values.update(
            _refresh_filesystem_identity_if_content_matches(
                download,
                path_stat=path_stat,
            )
        )

    if download.artifact_status in _PROBLEM_STATUSES:
        values.update(
            artifact_status=_HEALTHY_STATUS,
            artifact_error=None,
        )

    return _changed_values(download, values)


def _size_problem(
    download: MediaDownloadBase,
    *,
    path: str,
    size: int,
    verify_file_size: bool,
) -> Optional[tuple[MediaDownloadArtifactStatus, str]]:
    if size == 0:
        return MediaDownloadArtifactStatus.CORRUPTED, f"File at '{path}' is empty"

    if verify_file_size and download.downloaded_bytes and size < download.downloaded_bytes * _MIN_SIZE_RATIO:
        return MediaDownloadArtifactStatus.CORRUPTED, (
            f"File at '{path}' is only {size} bytes, well under the "
            f"{download.downloaded_bytes} recorded when it finished downloading"
        )
    return None


def _has_complete_identity(download: MediaDownloadBase) -> bool:
    return (
        bool(download.artifact_stat_dev)
        and bool(download.artifact_stat_ino)
        and download.artifact_size_bytes is not None
        and bool(download.artifact_fingerprint)
    )


def _refresh_filesystem_identity_if_content_matches(
    download: MediaDownloadBase,
    *,
    path_stat: os.stat_result,
) -> _ArtifactUpdates:
    """Refresh volatile filesystem IDs only when durable identity still matches."""
    stat_dev = str(path_stat.st_dev)
    stat_ino = str(path_stat.st_ino)
    if stat_dev == download.artifact_stat_dev and stat_ino == download.artifact_stat_ino:
        return {}
    if path_stat.st_size != download.artifact_size_bytes:
        return {}

    try:
        identity = inspect_artifact(download.file_path)
    except (OSError, ValueError):
        return {}
    if identity.fingerprint != download.artifact_fingerprint:
        return {}

    return _changed_values(
        download,
        {
            "artifact_stat_dev": identity.stat_dev,
            "artifact_stat_ino": identity.stat_ino,
        },
    )


def _find_same_directory_rename(
    download: MediaDownloadBase,
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
    download: MediaDownloadBase,
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
    download: MediaDownloadBase,
    candidates: list[tuple[str, os.stat_result]],
) -> list[_RenamedArtifact]:
    matches: list[_RenamedArtifact] = []
    for candidate_path, _candidate_stat in candidates:
        match = _inspect_matching_candidate(download, candidate_path)
        if match is not None:
            matches.append(match)
    return matches


def _identity_values(identity: ArtifactIdentity) -> _ArtifactUpdates:
    return {
        "artifact_stat_dev": identity.stat_dev,
        "artifact_stat_ino": identity.stat_ino,
        "artifact_size_bytes": identity.size_bytes,
        "artifact_fingerprint": identity.fingerprint,
    }


def _problem_updates(
    download: MediaDownloadBase,
    status: MediaDownloadArtifactStatus,
    message: str,
) -> _ArtifactUpdates:
    return _changed_values(
        download,
        {
            "artifact_status": status.value,
            "artifact_error": message,
        },
    )


def _changed_values(
    download: MediaDownloadBase,
    values: _ArtifactUpdates,
) -> _ArtifactUpdates:
    return {
        field: value
        for field, value in values.items()
        if getattr(download, field) != value
    }


def _apply_reconciliation_with_transaction(
    s: Session,
    original: MediaDownloadBase,
    values: _ArtifactUpdates,
) -> bool:
    if s.in_transaction():
        return _apply_reconciliation(s, original, values)

    expire_on_commit = s.expire_on_commit
    s.expire_on_commit = False
    try:
        with s.begin():
            return _apply_reconciliation(s, original, values)
    finally:
        s.expire_on_commit = expire_on_commit


def _apply_reconciliation(
    s: Session,
    original: MediaDownloadBase,
    values: _ArtifactUpdates,
) -> bool:
    table = MediaDownloadBase.__table__
    guards = [
        _matches_snapshot_value(table.c[field], getattr(original, field))
        for field in _ARTIFACT_GUARD_FIELDS
    ]
    stmt = (
        table.update()
        .where(table.c.id == original.id, *guards)
        .values(**values)
    )
    result = s.execute(stmt)
    if result.rowcount != 1:
        logger.info(
            "file_watcher: skipped stale result for media_download %s because the row changed while filesystem checks were running",
            original.id,
        )
        return False

    _log_applied_change(original, values)
    for field, value in values.items():
        set_committed_value(original, field, value)
    return True


def _apply_reconciliations(
    s: Session,
    changes: list[tuple[MediaDownloadBase, _ArtifactUpdates]],
) -> int:
    if not changes:
        return 0

    updated = 0
    expire_on_commit = s.expire_on_commit
    s.expire_on_commit = False
    try:
        with s.begin():
            for original, values in changes:
                if _apply_reconciliation(s, original, values):
                    updated += 1
    finally:
        s.expire_on_commit = expire_on_commit
    return updated


def _matches_snapshot_value(column, value):
    if value is None:
        return column.is_(None)
    return column == value


def _result_value(
    original: MediaDownloadBase,
    values: _ArtifactUpdates,
    field: str,
):
    if field in values:
        return values[field]
    return getattr(original, field)


def _log_applied_change(
    original: MediaDownloadBase,
    values: _ArtifactUpdates,
) -> None:
    file_path = _result_value(original, values, "file_path")
    artifact_status = _result_value(original, values, "artifact_status")
    artifact_error = _result_value(original, values, "artifact_error")
    artifact_stat_dev = _result_value(original, values, "artifact_stat_dev")
    artifact_stat_ino = _result_value(original, values, "artifact_stat_ino")

    if original.file_path != file_path:
        logger.info(
            "file_watcher: media_download %s renamed %s -> %s",
            original.id,
            original.file_path,
            file_path,
        )

    if artifact_status in _PROBLEM_STATUSES and (
        original.artifact_status != artifact_status
        or original.artifact_error != artifact_error
    ):
        logger.warning(
            "file_watcher: media_download %s -> %s (%s)",
            original.id,
            artifact_status,
            artifact_error,
        )
    elif original.artifact_status in _PROBLEM_STATUSES and artifact_status == _HEALTHY_STATUS:
        logger.info("file_watcher: media_download %s file is healthy again", original.id)
    elif (
        original.artifact_stat_dev != artifact_stat_dev
        or original.artifact_stat_ino != artifact_stat_ino
    ):
        logger.info(
            "file_watcher: refreshed filesystem identity for media_download %s",
            original.id,
        )
