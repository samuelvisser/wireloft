from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models import DownloadProfileBase
from backend.utils.episode_download_scope import EpisodeDownloadScope
from dailywire_downloader import DownloadCancelled
from task_manager.events.transactional import queue_event
from task_manager.scheduler.types import OperationSource
from task_manager.tasks.helpers.downloads.show_episode_downloads import (
    cancel_active_download_attempts,
    delete_episode_download_artifact,
)
from task_manager.tasks.helpers.progress import update_progress


def _disable_show_download_profiles(s: Session, *, show_id: int) -> int:
    """Disable every Download Profile attached to the show before deleting files."""
    profiles = list(s.scalars(
        select(DownloadProfileBase).where(DownloadProfileBase.show_id == show_id)
    ))
    disabled = 0
    for profile in profiles:
        if not profile.enable_profile:
            continue
        profile.enable_profile = False
        disabled += 1
        queue_event(s, "download_profile.updated", {
            "resource_id": profile.id,
            "id": profile.id,
            "show_id": profile.show_id,
            "profile_type": profile.type,
        })

    # This must be durable before any artifact is removed. It prevents a normal
    # Download Profile sweep from rebuilding files while the delete operation is
    # still working through the show.
    s.commit()
    return disabled


def run_delete_show_downloads_worker(
        s: Session,
        *,
        show_id: int,
        local_media_profile_id: int | None = None,
        progress=None,
) -> dict[str, Any]:
    """Delete existing show artifacts after disabling the show's Download Profiles."""
    scope = EpisodeDownloadScope.resolve(s, show_id=show_id).select(
        local_media_profile_id=local_media_profile_id,
    )
    base_result = scope.result_data()
    downloads = list(scope.downloads)
    download_profile_count = _disable_show_download_profiles(s, show_id=scope.show.id)

    if not downloads:
        update_progress(progress, 100, "No downloaded episodes match this request")
        return {
            **base_result,
            "episode_files": 0,
            "download_profiles_disabled": download_profile_count,
        }

    total = len(downloads)
    update_progress(progress, 1, f"Preparing to delete {total} episode download(s)")

    for index, download in enumerate(downloads, start=1):
        if progress is not None and callable(progress) and progress():
            raise DownloadCancelled("Show download deletion was canceled")

        # Cancel immediately before destructive work. An already-running profile
        # worker may have loaded its now-disabled profile before this operation
        # committed that state, so retain the per-item cancellation race guard.
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

        # Close the cancellation/requeue race for an in-flight Download Profile
        # worker. Once the profile-disable commit is visible, no new automatic
        # replacement can be created. Never cancel an explicit user retry.
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
    return {
        **base_result,
        "episode_files": total,
        "download_profiles_disabled": download_profile_count,
    }
