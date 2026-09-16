from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from backend.utils.episode_download_scope import EpisodeDownloadScope
from dailywire_downloader import DownloadCancelled
from task_manager.tasks.helpers.download_profiles import (
    disable_download_profiles_for_episode_scope,
)
from task_manager.tasks.helpers.downloads.show_episode_downloads import (
    cancel_active_download_attempts,
    delete_episode_download_artifact,
)
from task_manager.tasks.helpers.progress import update_progress


def run_delete_show_downloads_worker(
        s: Session,
        *,
        show_id: int,
        local_media_profile_id: int | None = None,
        download_profiles_disabled: int = 0,
        progress=None,
) -> dict[str, Any]:
    """Delete existing show artifacts after affected Download Profiles are disabled."""
    scope = EpisodeDownloadScope.resolve(s, show_id=show_id).select(
        local_media_profile_id=local_media_profile_id,
    )
    base_result = scope.result_data()
    downloads = list(scope.downloads)

    # The API disables profiles before this worker can be dispatched. Keep this
    # idempotent guard for recovered/manual task execution and commit it before
    # cancellation helpers deliberately roll back their read transaction.
    disabled_during_worker = disable_download_profiles_for_episode_scope(s, scope)
    s.commit()
    disabled_profile_count = max(download_profiles_disabled, disabled_during_worker)

    if not downloads:
        update_progress(progress, 100, "No downloaded episodes match this request")
        return {
            **base_result,
            "episode_files": 0,
            "download_profiles_disabled": disabled_profile_count,
        }

    total = len(downloads)
    update_progress(progress, 1, f"Preparing to delete {total} episode download(s)")

    # Any automatic work that won the profile lock before the disable is now
    # fully committed and no later profile reconciliation can create more work.
    # Cancel those existing attempts for the whole scope before removing files.
    cancel_active_download_attempts(
        s,
        downloads,
        reason="Deleted by show download cleanup",
    )

    for index, download in enumerate(downloads, start=1):
        if progress is not None and callable(progress) and progress():
            raise DownloadCancelled("Show download deletion was canceled")

        # Also protect against an explicit per-episode retry started by the user
        # after the operation began. Automatic retries cannot appear here because
        # the affected Download Profiles are durably disabled and serialized.
        cancel_active_download_attempts(
            s,
            [download],
            reason="Deleted by show download cleanup",
        )
        delete_episode_download_artifact(s, download)
        # Make each destructive step durable independently. A user may cancel a
        # long-running show cleanup without rolling already removed files back
        # into database state that claims they still exist.
        s.commit()

        percentage = min(99, max(1, int(index * 100 / total)))
        update_progress(
            progress,
            percentage,
            f"Deleted {index}/{total} episode file(s)",
        )

    update_progress(progress, 100, f"Deleted {total} episode file(s)")
    return {
        **base_result,
        "episode_files": total,
        "download_profiles_disabled": disabled_profile_count,
    }
