from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from dailywire_downloader import DownloadCancelled
from task_manager.scheduler.types import OperationSource
from task_manager.tasks.helpers.downloads.show_episode_downloads import (
    cancel_active_download_attempts,
    delete_episode_download_artifact,
    resolve_episode_download_scope,
)
from task_manager.tasks.helpers.progress import update_progress


def run_delete_show_downloads_worker(
        s: Session,
        *,
        show_id: int,
        local_media_profile_id: int | None = None,
        progress=None,
) -> dict[str, Any]:
    """Delete existing show artifacts while retaining their MediaDownload rows."""
    scope = resolve_episode_download_scope(
        s,
        show_id=show_id,
        local_media_profile_id=local_media_profile_id,
    )
    base_result = scope.result_data()
    downloads = list(scope.downloads)

    if not downloads:
        update_progress(progress, 100, "No downloaded episodes match this request")
        return {**base_result, "episode_files": 0}

    total = len(downloads)
    update_progress(progress, 1, f"Preparing to delete {total} episode download(s)")

    for index, download in enumerate(downloads, start=1):
        if progress is not None and callable(progress) and progress():
            raise DownloadCancelled("Show download deletion was canceled")

        # Cancel immediately before destructive work. Doing this per item avoids a
        # long no-operation window in which an automatic Download Profile sweep
        # could replace a later canceled download before this worker reaches it.
        cancel_active_download_attempts(
            s,
            [download],
            reason="Deleted by show download cleanup",
        )
        delete_episode_download_artifact(
            s,
            download,
            suppress_automatic_retry=True,
        )
        # Make each destructive step durable independently. A user may cancel a
        # long-running show cleanup without rolling already removed files back
        # into database state that claims they still exist.
        s.commit()

        # Close the cancellation/requeue race using the same policy as an
        # individual cancel: only a SYSTEM replacement can have been created by
        # the automatic sweep. Never cancel an explicit retry another caller
        # deliberately started after this deletion became visible.
        cancel_active_download_attempts(
            s,
            [download],
            reason="Deleted by show download cleanup",
            source=OperationSource.SYSTEM.value,
        )

        percentage = min(99, max(1, int(index * 100 / total)))
        update_progress(
            progress,
            percentage,
            f"Deleted {index}/{total} episode file(s)",
        )

    update_progress(progress, 100, f"Deleted {total} episode file(s)")
    return {**base_result, "episode_files": total}
