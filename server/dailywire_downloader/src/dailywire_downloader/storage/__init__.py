from __future__ import annotations

from pathlib import Path

from .claims import DownloadPathClaimJournal
from .direct import (
    DownloadPathReservation,
    cleanup_abandoned_direct_download_path_reservations,
    reserve_unique_download_path,
)
from .filesystem import (
    FilesystemInspection,
    FilesystemStorageKind,
    classify_filesystem_type,
    inspect_filesystem,
    same_filesystem,
)
from .temporary import (
    TemporaryDownloadFilesystemError,
    TemporaryDownloadWorkspace,
    cleanup_abandoned_publication_locks,
    create_temporary_download_workspace,
    publish_temporary_download,
)


def cleanup_abandoned_download_path_reservations(
    download_root: str | Path,
    *,
    path_claims: DownloadPathClaimJournal | None = None,
) -> int:
    """Remove filesystem claims left behind by either download mode."""
    return (
        cleanup_abandoned_direct_download_path_reservations(
            download_root,
            path_claims=path_claims,
        )
        + cleanup_abandoned_publication_locks(
            download_root,
            path_claims=path_claims,
        )
    )
