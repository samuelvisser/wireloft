from __future__ import annotations

from pathlib import Path

from .mode_direct_download import (
    DownloadPathReservation,
    cleanup_abandoned_direct_download_path_reservations,
    reserve_unique_download_path,
)
from .mode_temp_folder_download import (
    TemporaryDownloadFilesystemError,
    TemporaryDownloadWorkspace,
    cleanup_abandoned_publication_locks,
    cleanup_abandoned_temporary_downloads,
    create_temporary_download_workspace,
    publish_temporary_download,
)


def cleanup_abandoned_download_path_reservations(download_root: str | Path) -> int:
    """Remove filesystem claims left behind by either download mode."""
    return (
        cleanup_abandoned_direct_download_path_reservations(download_root)
        + cleanup_abandoned_publication_locks(download_root)
    )
