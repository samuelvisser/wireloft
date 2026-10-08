from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from backend.types.download_profile_types import MediaDownloadArtifactStatus
from backend.utils.episode_download_scope import EpisodeDownloadScope
from backend.utils.output_template import output_template_fields, resolve_episode_output_path
from backend.services.download_relocation import plan_download_relocation, relocate_downloads
from task_manager.scheduler.results import TaskResult
from task_manager.tasks.helpers.progress import update_progress
from task_manager.tasks.workers.file_watcher.service import resolve_media_download_file


_PHYSICAL_ARTIFACT_STATUSES = (
    MediaDownloadArtifactStatus.AVAILABLE.value,
    MediaDownloadArtifactStatus.MISSING.value,
    MediaDownloadArtifactStatus.CORRUPTED.value,
)
_IDENTIFIER_DERIVED_TEMPLATE_FIELDS = frozenset({
    "episode_identifier",
    "episode_label",
    "episode_number",
    "episode_sub_number",
    "episode_type",
    "episode_extra_type",
})


async def run_rename_file_worker(
        s: Session,
        *,
        episode_id: int,
        local_media_profile_id: int | None = None,
        identifier_fields_only: bool = False,
        progress=None,
) -> TaskResult:
    """Move existing episode artifacts to paths rendered from current metadata.

    ``MediaDownload.file_path`` is the source of truth for the current artifact
    location. If that path is missing, the shared FileWatcher reconciliation path
    first attempts to find a same-directory manual rename and persists the newly
    discovered source path. The destination is then rendered from the episode's
    current data and its current Local Media Profile template.
    """
    try:
        scope = EpisodeDownloadScope.resolve(
            s,
            episode_id=episode_id,
            local_media_profile_id=local_media_profile_id,
            artifact_statuses=_PHYSICAL_ARTIFACT_STATUSES,
        )
    except ValueError:
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

    episode = scope.episode
    assert episode is not None
    downloads = list(scope.downloads)
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

    # Per-file commits make completed filesystem moves durable. Keep already
    # loaded episode/profile/download state alive across those commits so no lazy
    # SELECT can reopen a transaction immediately before the next filesystem move.
    expire_on_commit = s.expire_on_commit
    s.expire_on_commit = False
    try:
        for index, download in enumerate(downloads, start=1):
            if not download.file_path:
                raise ValueError(f"Media download {download.id} has no current file path")

            output_template = download.local_media_profile.output_template
            s.commit()
            resolved_source = resolve_media_download_file(
                s,
                download,
                release_read_transaction=True,
            )
            source = resolved_source or Path(download.file_path)
            extension = source.suffix.removeprefix(".")
            if not extension:
                raise ValueError(f"Cannot determine the extension for media download {download.id}")

            destination = resolve_episode_output_path(
                output_template,
                episode=episode,
                local_media_profile=download.local_media_profile,
                media_download=download,
                extension=extension,
            )

            if resolved_source is not None and source == destination:
                unchanged += 1
            elif resolved_source is not None:
                move = plan_download_relocation(download, source, destination)
                relocate_downloads(s, [move])
                renamed += 1
            elif destination.exists():
                move = plan_download_relocation(download, source, destination)
                relocate_downloads(s, [move])
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
    finally:
        s.expire_on_commit = expire_on_commit

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
