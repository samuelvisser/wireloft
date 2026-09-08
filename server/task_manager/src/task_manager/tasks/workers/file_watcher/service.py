from __future__ import annotations

from dataclasses import dataclass
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

from ._helpers import get_tracked_downloads

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


async def run_file_watcher(s: Session, *, show_id: Optional[int] = None, show_slug: Optional[str] = None, progress=None) -> None:
    """Reconcile persistent MediaDownload artifact facts with the filesystem.

    A missing path is searched only within its original parent directory. Device
    and inode cheaply narrow likely rename candidates; a sampled content
    fingerprint confirms identity and is also the fallback for network
    filesystems where filesystem identifiers are unstable or unhelpful.
    """
    settings = get_settings().file_watcher
    if not settings.enabled:
        print("file_watcher is disabled (file_watcher.enabled=false), skipping")
        return

    print("Starting file_watcher")
    downloads = get_tracked_downloads(s, show_id=show_id, show_slug=show_slug)
    updated = 0
    for download in downloads:
        if _reconcile(download, verify_file_size=settings.verify_file_size):
            updated += 1

    s.commit()
    print(f"file_watcher completed: checked {len(downloads)} artifact(s), updated {updated}")


def _reconcile(download: MediaDownloadBase, *, verify_file_size: bool) -> bool:
    path = download.file_path
    try:
        path_stat = os.stat(path)
    except FileNotFoundError:
        renamed, rename_error = _find_same_directory_rename(download)
        if renamed is not None:
            old_path = download.file_path
            download.file_path = renamed.path
            _set_identity(download, renamed.identity)
            logger.info(
                "file_watcher: media_download %s renamed %s -> %s",
                download.id,
                old_path,
                renamed.path,
            )
            problem = _size_problem(
                download,
                size=renamed.identity.size_bytes,
                verify_file_size=verify_file_size,
            )
            if problem is None:
                download.artifact_status = _HEALTHY_STATUS
                download.artifact_error = None
            else:
                status, message = problem
                download.artifact_status = status.value
                download.artifact_error = message
            return True

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

    identity_updated = False
    if not _has_complete_identity(download):
        try:
            identity = inspect_artifact(path)
        except FileNotFoundError:
            return _apply_problem(
                download,
                MediaDownloadArtifactStatus.MISSING,
                f"File not found at '{path}'",
            )
        except (OSError, ValueError) as exc:
            return _apply_problem(
                download,
                MediaDownloadArtifactStatus.MISSING,
                f"Could not check '{path}': {exc}",
            )
        _set_identity(download, identity)
        identity_updated = True

    problem = _size_problem(download, size=path_stat.st_size, verify_file_size=verify_file_size)
    if problem is not None:
        status, message = problem
        changed = _apply_problem(download, status, message)
        return changed or identity_updated

    if not identity_updated:
        identity_updated = _refresh_filesystem_identity_if_content_matches(
            download,
            path_stat=path_stat,
        )

    if download.artifact_status in _PROBLEM_STATUSES:
        logger.info("file_watcher: media_download %s file is healthy again", download.id)
        download.artifact_status = _HEALTHY_STATUS
        download.artifact_error = None
        return True

    return identity_updated


def _size_problem(
    download: MediaDownloadBase,
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
) -> bool:
    """Refresh only volatile filesystem IDs when the persisted artifact still matches.

    SMB/NFS reconnects can change identifiers while the path and content remain
    unchanged. Never replace the stored size/fingerprint merely because a file at
    the expected path changed; those values are the durable rename fallback.
    """
    stat_dev = str(path_stat.st_dev)
    stat_ino = str(path_stat.st_ino)
    if stat_dev == download.artifact_stat_dev and stat_ino == download.artifact_stat_ino:
        return False
    if path_stat.st_size != download.artifact_size_bytes:
        return False

    try:
        identity = inspect_artifact(download.file_path)
    except (OSError, ValueError):
        return False
    if identity.fingerprint != download.artifact_fingerprint:
        return False

    download.artifact_stat_dev = identity.stat_dev
    download.artifact_stat_ino = identity.stat_ino
    logger.info(
        "file_watcher: refreshed filesystem identity for media_download %s",
        download.id,
    )
    return True


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

    # Try the filesystem IDs first so a normal local rename hashes only one
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


def _set_identity(download: MediaDownloadBase, identity: ArtifactIdentity) -> None:
    download.artifact_stat_dev = identity.stat_dev
    download.artifact_stat_ino = identity.stat_ino
    download.artifact_size_bytes = identity.size_bytes
    download.artifact_fingerprint = identity.fingerprint


def _apply_problem(
    download: MediaDownloadBase,
    status: MediaDownloadArtifactStatus,
    message: str,
) -> bool:
    if download.artifact_status == status.value and download.artifact_error == message:
        return False
    logger.warning("file_watcher: media_download %s -> %s (%s)", download.id, status.value, message)
    download.artifact_status = status.value
    download.artifact_error = message
    return True
