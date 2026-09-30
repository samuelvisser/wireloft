from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from backend.db.models import Episode, Show, ShowLocalMediaProfile
from backend.db.models.media_download import EpisodeMediaDownload
from backend.services.custom_indexes import ensure_episode_custom_indexes_ready
from backend.types.download_profile_types import MediaDownloadArtifactStatus
from backend.utils.output_template import resolve_episode_output_path
from backend.services.download_relocation import DownloadRelocation, plan_download_relocation, relocate_downloads
from task_manager.scheduler.results import TaskResult
from task_manager.tasks.helpers.progress import update_progress
from task_manager.tasks.workers.file_watcher.service import resolve_media_download_file


logger = logging.getLogger(__name__)


_PHYSICAL_STATUSES = (
    MediaDownloadArtifactStatus.AVAILABLE.value,
    MediaDownloadArtifactStatus.CORRUPTED.value,
    MediaDownloadArtifactStatus.MISSING.value,
)


def run_rename_show_profile_files(
    session: Session,
    *,
    show_id: int,
    local_media_profile_id: int,
    episode_ids: list[int] | tuple[int, ...] | None = None,
    expected_sources: dict[str, str] | None = None,
    progress=None,
) -> TaskResult:
    profile = session.get(ShowLocalMediaProfile, local_media_profile_id)
    if profile is None:
        return TaskResult(summary="Local Media Profile no longer exists")

    show = session.get(Show, show_id)
    if show is None:
        return TaskResult(summary="Show no longer exists")

    stmt = (
        select(EpisodeMediaDownload)
        .options(joinedload(EpisodeMediaDownload.local_media_profile))
        .join(Episode, Episode.id == EpisodeMediaDownload.media_item_id)
        .where(
            Episode.show_id == show_id,
            EpisodeMediaDownload.local_media_profile_id == local_media_profile_id,
            EpisodeMediaDownload.artifact_status.in_(_PHYSICAL_STATUSES),
        )
        .order_by(Episode.index.asc(), EpisodeMediaDownload.id.asc())
    )
    if episode_ids is not None:
        ids = tuple(dict.fromkeys(int(value) for value in episode_ids))
        if not ids:
            return TaskResult(summary="No files need renaming")
        stmt = stmt.where(Episode.id.in_(ids))

    downloads = list(session.scalars(stmt).unique())
    if not downloads:
        update_progress(progress, 100, "No existing files need renaming")
        return TaskResult(
            summary="No existing files need renaming",
            data={"files_considered": 0, "files_renamed": 0, "files_unchanged": 0},
        )

    moves: list[DownloadRelocation] = []
    unchanged = 0
    for index, download in enumerate(downloads, start=1):
        source = resolve_media_download_file(session, download)
        if source is None:
            raise FileNotFoundError(
                f"Cannot rename media download {download.id}: '{download.file_path}' does not exist"
            )
        if expected_sources is not None and str(source) != expected_sources.get(str(download.media_item_id)):
            unchanged += 1
            continue
        extension = source.suffix.removeprefix(".")
        if not extension:
            raise ValueError(f"Cannot determine extension for media download {download.id}")
        episode = session.get(Episode, download.media_item_id)
        if episode is None:
            raise ValueError(f"Episode for media download {download.id} no longer exists")

        ensure_episode_custom_indexes_ready(session, episode=episode, profile=profile)
        destination = resolve_episode_output_path(
            profile.output_template,
            episode=episode,
            local_media_profile=profile,
            media_download=download,
            extension=extension,
        )
        if source == destination:
            unchanged += 1
            continue
        moves.append(plan_download_relocation(download, source, destination))
        update_progress(progress, min(20, round(index / len(downloads) * 20)), "Planning file renames")

    if not moves:
        update_progress(progress, 100, "Files already have the expected names")
        return TaskResult(
            summary="Files already have the expected names",
            data={
                "files_considered": len(downloads),
                "files_renamed": 0,
                "files_unchanged": unchanged,
            },
        )

    renamed, skipped = relocate_downloads(session, moves, progress=progress, skip_existing=True)
    summary = f"Renamed {renamed} file(s)" + (f"; skipped {skipped} existing destination(s)" if skipped else "")
    update_progress(progress, 100, summary)
    return TaskResult(summary=summary, data={
        "files_considered": len(downloads), "files_renamed": renamed,
        "files_unchanged": unchanged, "files_skipped_existing": skipped,
    })
