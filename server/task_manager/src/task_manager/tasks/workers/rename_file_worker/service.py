from __future__ import annotations

import shutil
from pathlib import Path

from sqlalchemy.orm import Session

from backend.db.models import DownloadProfileBase, Episode
from backend.db.models.media_download import EpisodeMediaDownload
from backend.types.download_profile_types import MediaDownloadArtifactStatus
from backend.utils.output_template import output_template_fields, resolve_episode_output_path
from task_manager.scheduler.results import TaskResult
from task_manager.tasks.helpers.progress import update_progress


_PHYSICAL_ARTIFACT_STATUSES = (
    MediaDownloadArtifactStatus.AVAILABLE.value,
    MediaDownloadArtifactStatus.CORRUPTED.value,
)
_IDENTIFIER_DERIVED_TEMPLATE_FIELDS = frozenset({
    "episode_identifier",
    "episode_label",
    "episode_number",
    "episode_type",
})


async def run_rename_file_worker(
        s: Session,
        *,
        episode_id: int,
        download_profile_id: int | None = None,
        local_media_profile_id: int | None = None,
        identifier_fields_only: bool = False,
        progress=None,
) -> TaskResult:
    """Move existing episode artifacts to paths rendered from current metadata.

    ``MediaDownload.file_path`` is the source of truth for the current artifact
    location. The destination is always rendered from the episode's current data
    and its current Local Media Profile template, which makes the operation
    idempotent and lets retries recover a move that reached the filesystem before
    the database path was committed.
    """
    if download_profile_id is not None and local_media_profile_id is not None:
        raise ValueError("Rename File can filter by Download Profile or Local Media Profile, not both")

    episode = s.get(Episode, episode_id)
    if episode is None:
        update_progress(progress, 100, f"Episode {episode_id} no longer exists")
        return TaskResult(
            summary="Episode no longer exists",
            data={
                "files_renamed": 0,
                "files_unchanged": 0,
                "files_recovered": 0,
                "files_considered": 0,
            },
        )

    scoped_local_media_profile_id = local_media_profile_id
    if download_profile_id is not None:
        download_profile = s.get(DownloadProfileBase, download_profile_id)
        if download_profile is None:
            raise ValueError(f"Download Profile {download_profile_id} no longer exists")
        scoped_local_media_profile_id = download_profile.local_media_profile_id

    query = (
        s.query(EpisodeMediaDownload)
        .filter(
            EpisodeMediaDownload.media_item_id == episode.id,
            EpisodeMediaDownload.artifact_status.in_(_PHYSICAL_ARTIFACT_STATUSES),
        )
        .order_by(EpisodeMediaDownload.id.asc())
    )
    if scoped_local_media_profile_id is not None:
        query = query.filter(
            EpisodeMediaDownload.local_media_profile_id == scoped_local_media_profile_id,
        )

    downloads = query.all()
    if identifier_fields_only:
        downloads = [
            download
            for download in downloads
            if output_template_fields(download.local_media_profile.output_template)
            & _IDENTIFIER_DERIVED_TEMPLATE_FIELDS
        ]

    if not downloads:
        update_progress(progress, 100, f"No existing files to rename for '{episode.title}'")
        return TaskResult(
            summary="No existing files to rename",
            data={
                "files_renamed": 0,
                "files_unchanged": 0,
                "files_recovered": 0,
                "files_considered": 0,
            },
        )

    renamed = 0
    unchanged = 0
    recovered = 0
    total = len(downloads)

    for index, download in enumerate(downloads, start=1):
        if not download.file_path:
            raise ValueError(f"Media download {download.id} has no current file path")

        source = Path(download.file_path)
        extension = source.suffix.removeprefix(".")
        if not extension:
            raise ValueError(f"Cannot determine the extension for media download {download.id}")

        destination = resolve_episode_output_path(
            download.local_media_profile.output_template,
            episode=episode,
            extension=extension,
        )

        if source == destination:
            unchanged += 1
        elif source.exists():
            if destination.exists():
                raise FileExistsError(
                    f"Cannot rename '{source}' to '{destination}': destination already exists"
                )
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(destination))
            download.file_path = str(destination)
            # The filesystem cannot participate in the SQL transaction. Persist
            # every completed move immediately so later failures cannot roll the
            # database path back behind already-moved files.
            s.commit()
            renamed += 1
        elif destination.exists():
            # A previous attempt can be interrupted after shutil.move() but before
            # its database commit. Treat that exact state as successful recovery.
            download.file_path = str(destination)
            s.commit()
            recovered += 1
        else:
            raise FileNotFoundError(
                f"Cannot rename media download {download.id}: '{source}' does not exist"
            )

        percentage = round(index / total * 100)
        update_progress(
            progress,
            percentage,
            f"Processed {index}/{total} file{'s' if total != 1 else ''} for '{episode.title}'",
        )

    changed = renamed + recovered
    if changed:
        summary = f"Renamed {changed} file{'s' if changed != 1 else ''}"
    else:
        summary = "File already has the expected name" if total == 1 else "Files already have the expected names"

    return TaskResult(
        summary=summary,
        data={
            "files_renamed": renamed,
            "files_unchanged": unchanged,
            "files_recovered": recovered,
            "files_considered": total,
        },
    )
