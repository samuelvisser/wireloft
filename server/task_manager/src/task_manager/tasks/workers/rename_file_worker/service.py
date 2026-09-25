from __future__ import annotations

import shutil
from pathlib import Path

from sqlalchemy.orm import Session

from backend.db.models.media_download import EpisodeMediaDownload
from backend.services.media_download_history import record_media_download_history
from backend.types.download_profile_types import MediaDownloadArtifactStatus
from backend.types.media_download_history_types import MediaDownloadHistoryAction
from backend.utils.artifact_identity import inspect_artifact
from backend.utils.episode_download_scope import EpisodeDownloadScope
from backend.utils.output_template import output_template_fields, resolve_episode_output_path
from dailywire_downloader import hls_asset_marker, hls_asset_root
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
        scope = EpisodeDownloadScope.resolve(s, episode_id=episode_id).select(
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
                if destination.exists():
                    raise FileExistsError(
                        f"Cannot rename '{source}' to '{destination}': destination already exists"
                    )
                destination.parent.mkdir(parents=True, exist_ok=True)
                thumbnail_destination = _planned_thumbnail_destination(download, destination)
                if thumbnail_destination is not None and thumbnail_destination.exists():
                    raise FileExistsError(
                        f"Cannot rename thumbnail to '{thumbnail_destination}': destination already exists"
                    )
                _assert_hls_assets_can_move(source, destination)

                shutil.move(str(source), str(destination))
                hls_assets_moved = False
                try:
                    hls_assets_moved = _move_hls_assets_if_present(source, destination)
                    _move_thumbnail_if_present(download, thumbnail_destination)
                except BaseException:
                    # Keep the media and its accessories together if a later move fails.
                    if hls_assets_moved:
                        _rollback_hls_assets(source, destination)
                    if destination.exists() and not source.exists():
                        shutil.move(str(destination), str(source))
                    raise

                _record_artifact_location(download, destination)
                record_media_download_history(
                    s,
                    download.id,
                    MediaDownloadHistoryAction.ARTIFACT_RENAMED,
                    metadata={
                        "old_path": str(source),
                        "new_path": str(destination),
                        "reason": "output_template_rename",
                        "recovered": False,
                    },
                )
                s.commit()
                renamed += 1
            elif destination.exists():
                # A previous attempt can be interrupted after the filesystem move
                # but before its database commit. Reconcile the sidecar in the same
                # recovery pass so it remains beside the recovered media artifact.
                thumbnail_destination = _planned_thumbnail_destination(download, destination)
                _move_hls_assets_if_present(source, destination)
                _move_thumbnail_if_present(download, thumbnail_destination)
                _record_artifact_location(download, destination)
                record_media_download_history(
                    s,
                    download.id,
                    MediaDownloadHistoryAction.ARTIFACT_RENAMED,
                    metadata={
                        "old_path": str(source),
                        "new_path": str(destination),
                        "reason": "output_template_rename",
                        "recovered": True,
                    },
                )
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



def _assert_hls_assets_can_move(source: Path, destination: Path) -> None:
    if source.suffix.lower() != ".m3u8":
        return
    source_marker = hls_asset_marker(source)
    if not source_marker.is_file():
        return
    destination_assets = hls_asset_root(destination)
    if destination_assets.exists():
        raise FileExistsError(
            f"Cannot rename HLS assets to '{destination_assets}': destination already exists"
        )


def _move_hls_assets_if_present(source: Path, destination: Path) -> bool:
    if source.suffix.lower() != ".m3u8":
        return False

    source_assets = hls_asset_root(source)
    destination_assets = hls_asset_root(destination)
    source_marker = hls_asset_marker(source)
    destination_marker = hls_asset_marker(destination)

    if source_marker.is_file():
        if destination_assets.exists():
            raise FileExistsError(
                f"Cannot rename HLS assets to '{destination_assets}': destination already exists"
            )
        destination_assets.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source_assets), str(destination_assets))
        return True

    # Recovery after an interrupted rename can find the master at its new name
    # while the companion directory was already moved before the database commit.
    if destination_marker.is_file():
        return False
    return False


def _rollback_hls_assets(source: Path, destination: Path) -> None:
    source_assets = hls_asset_root(source)
    destination_assets = hls_asset_root(destination)
    if hls_asset_marker(destination).is_file() and not source_assets.exists():
        shutil.move(str(destination_assets), str(source_assets))


def _planned_thumbnail_destination(
    download: EpisodeMediaDownload,
    media_destination: Path,
) -> Path | None:
    if not download.thumbnail_path:
        return None
    suffix = Path(download.thumbnail_path).suffix
    return media_destination.with_suffix(suffix) if suffix else None


def _move_thumbnail_if_present(
    download: EpisodeMediaDownload,
    destination: Path | None,
) -> None:
    if not download.thumbnail_path or destination is None:
        return

    source = Path(download.thumbnail_path)
    if source == destination:
        return
    if source.exists():
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(destination))
        download.thumbnail_path = str(destination)
    elif destination.exists():
        download.thumbnail_path = str(destination)
    else:
        download.thumbnail_path = None


def _record_artifact_location(download: EpisodeMediaDownload, path: Path) -> None:
    identity = inspect_artifact(path)
    download.file_path = str(path)
    download.artifact_status = MediaDownloadArtifactStatus.AVAILABLE.value
    download.artifact_error = None
    download.artifact_stat_dev = identity.stat_dev
    download.artifact_stat_ino = identity.stat_ino
    download.artifact_size_bytes = identity.size_bytes
    download.artifact_fingerprint = identity.fingerprint
