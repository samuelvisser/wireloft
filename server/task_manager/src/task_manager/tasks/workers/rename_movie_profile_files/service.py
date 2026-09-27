from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from backend.db.models import Movie, MovieExtra, MovieLocalMediaProfile
from backend.db.models.media_download import MediaDownloadBase
from backend.services.media_download_history import record_media_download_history
from backend.types.download_profile_types import MediaDownloadArtifactStatus
from backend.types.media_download_history_types import MediaDownloadHistoryAction
from backend.types.media_types import MediaType
from backend.utils.artifact_identity import inspect_artifact
from backend.utils.output_template import resolve_movie_output_path
from task_manager.scheduler.results import TaskResult
from task_manager.tasks.helpers.progress import update_progress
from task_manager.tasks.workers.file_watcher.service import resolve_media_download_file


_PHYSICAL_STATUSES = (
    MediaDownloadArtifactStatus.AVAILABLE.value,
    MediaDownloadArtifactStatus.CORRUPTED.value,
)


@dataclass(frozen=True)
class _Move:
    download_id: int
    source: Path
    destination: Path
    thumbnail_source: Path | None
    thumbnail_destination: Path | None


@dataclass(frozen=True)
class _StagedMove:
    move: _Move
    staged_media: Path
    staged_thumbnail: Path | None


def _temporary_path(path: Path) -> Path:
    return path.with_name(f".{path.name}.wireloft-rename-{uuid4().hex}.tmp")


def _thumbnail_destination(
    download: MediaDownloadBase,
    destination: Path,
) -> Path | None:
    if not download.thumbnail_path:
        return None
    suffix = Path(download.thumbnail_path).suffix
    return destination.with_suffix(suffix) if suffix else None


def _record_location(
    download: MediaDownloadBase,
    destination: Path,
    thumbnail_destination: Path | None,
) -> None:
    identity = inspect_artifact(destination)
    download.file_path = str(destination)
    download.thumbnail_path = (
        str(thumbnail_destination)
        if thumbnail_destination is not None and thumbnail_destination.exists()
        else None
    )
    download.artifact_status = MediaDownloadArtifactStatus.AVAILABLE.value
    download.artifact_error = None
    download.artifact_stat_dev = identity.stat_dev
    download.artifact_stat_ino = identity.stat_ino
    download.artifact_size_bytes = identity.size_bytes
    download.artifact_fingerprint = identity.fingerprint


def _rollback_staging(staged: list[_StagedMove]) -> None:
    for item in staged:
        move = item.move
        try:
            if move.destination.exists() and not item.staged_media.exists():
                item.staged_media.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(move.destination), str(item.staged_media))
        except OSError:
            pass

        if item.staged_thumbnail is None or move.thumbnail_destination is None:
            continue
        try:
            if (
                move.thumbnail_destination.exists()
                and not item.staged_thumbnail.exists()
            ):
                item.staged_thumbnail.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(
                    str(move.thumbnail_destination),
                    str(item.staged_thumbnail),
                )
        except OSError:
            pass

    for item in reversed(staged):
        move = item.move
        try:
            if item.staged_media.exists():
                move.source.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(item.staged_media), str(move.source))
        except OSError:
            pass

        if item.staged_thumbnail is None or move.thumbnail_source is None:
            continue
        try:
            if item.staged_thumbnail.exists():
                move.thumbnail_source.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(
                    str(item.staged_thumbnail),
                    str(move.thumbnail_source),
                )
        except OSError:
            pass


def run_rename_movie_profile_files(
    session: Session,
    *,
    local_media_profile_id: int,
    progress=None,
) -> TaskResult:
    profile = session.get(MovieLocalMediaProfile, local_media_profile_id)
    if profile is None:
        return TaskResult(summary="Local Media Profile no longer exists")

    downloads = list(session.scalars(
        select(MediaDownloadBase)
        .options(
            joinedload(MediaDownloadBase.media),
            joinedload(MediaDownloadBase.local_media_profile),
        )
        .where(
            MediaDownloadBase.local_media_profile_id == local_media_profile_id,
            MediaDownloadBase.type.in_(
                (MediaType.MOVIE.value, MediaType.MOVIE_EXTRA.value)
            ),
            MediaDownloadBase.artifact_status.in_(_PHYSICAL_STATUSES),
        )
        .order_by(MediaDownloadBase.id.asc())
    ).unique())

    if not downloads:
        update_progress(progress, 100, "No existing files need renaming")
        return TaskResult(
            summary="No existing files need renaming",
            data={
                "files_considered": 0,
                "files_renamed": 0,
                "files_unchanged": 0,
            },
        )

    moves: list[_Move] = []
    unchanged = 0
    for index, download in enumerate(downloads, start=1):
        source = resolve_media_download_file(session, download)
        if source is None:
            raise FileNotFoundError(
                f"Cannot rename media download {download.id}: "
                f"'{download.file_path}' does not exist"
            )

        media = download.media
        if isinstance(media, Movie):
            movie = media
        elif isinstance(media, MovieExtra):
            movie = media.movie
        else:
            raise ValueError(
                f"Media download {download.id} is not a movie or movie extra"
            )

        extension = source.suffix.removeprefix(".")
        if not extension:
            raise ValueError(
                f"Cannot determine extension for media download {download.id}"
            )
        destination = resolve_movie_output_path(
            profile.output_template,
            movie=movie,
            media_item=media,
            extension=extension,
        )
        if source == destination:
            unchanged += 1
            continue

        moves.append(_Move(
            download_id=download.id,
            source=source,
            destination=destination,
            thumbnail_source=(
                Path(download.thumbnail_path)
                if download.thumbnail_path
                else None
            ),
            thumbnail_destination=_thumbnail_destination(download, destination),
        ))
        update_progress(
            progress,
            min(20, round(index / len(downloads) * 20)),
            "Planning file renames",
        )

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

    destinations = [
        path
        for move in moves
        for path in (move.destination, move.thumbnail_destination)
        if path is not None
    ]
    if len(destinations) != len(set(destinations)):
        raise FileExistsError(
            "Multiple managed artifacts resolve to the same destination"
        )

    source_list = [
        path
        for move in moves
        for path in (move.source, move.thumbnail_source)
        if path is not None and path.exists()
    ]
    if len(source_list) != len(set(source_list)):
        raise FileExistsError(
            "Multiple MediaDownloads claim the same source artifact"
        )
    source_paths = set(source_list)
    for move in moves:
        if move.destination.exists() and move.destination not in source_paths:
            raise FileExistsError(
                f"Cannot rename '{move.source}' to '{move.destination}': "
                "destination already exists"
            )
        if (
            move.thumbnail_destination is not None
            and move.thumbnail_destination.exists()
            and move.thumbnail_destination not in source_paths
        ):
            raise FileExistsError(
                "Cannot rename thumbnail: destination already exists"
            )

    session.commit()

    staged: list[_StagedMove] = []
    try:
        for index, move in enumerate(moves, start=1):
            staged_media = _temporary_path(move.source)
            staged_thumbnail = (
                _temporary_path(move.thumbnail_source)
                if (
                    move.thumbnail_source is not None
                    and move.thumbnail_source.exists()
                )
                else None
            )
            shutil.move(str(move.source), str(staged_media))
            staged_item = _StagedMove(
                move=move,
                staged_media=staged_media,
                staged_thumbnail=staged_thumbnail,
            )
            staged.append(staged_item)
            if staged_thumbnail is not None and move.thumbnail_source is not None:
                shutil.move(
                    str(move.thumbnail_source),
                    str(staged_thumbnail),
                )
            update_progress(
                progress,
                20 + round(index / len(moves) * 30),
                f"Staged {index}/{len(moves)} file(s)",
            )

        for index, item in enumerate(staged, start=1):
            move = item.move
            move.destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(item.staged_media), str(move.destination))
            if (
                item.staged_thumbnail is not None
                and move.thumbnail_destination is not None
            ):
                move.thumbnail_destination.parent.mkdir(
                    parents=True,
                    exist_ok=True,
                )
                shutil.move(
                    str(item.staged_thumbnail),
                    str(move.thumbnail_destination),
                )
            update_progress(
                progress,
                50 + round(index / len(staged) * 40),
                f"Renamed {index}/{len(staged)} file(s)",
            )
    except BaseException:
        _rollback_staging(staged)
        raise

    try:
        for item in staged:
            download = session.get(MediaDownloadBase, item.move.download_id)
            if download is None:
                raise RuntimeError(
                    f"Media download {item.move.download_id} disappeared "
                    "during File Rename"
                )
            _record_location(
                download,
                item.move.destination,
                item.move.thumbnail_destination,
            )
            record_media_download_history(
                session,
                download.id,
                MediaDownloadHistoryAction.ARTIFACT_RENAMED,
                metadata={
                    "old_path": str(item.move.source),
                    "new_path": str(item.move.destination),
                    "reason": "output_template_rename",
                    "recovered": False,
                },
            )
        session.commit()
    except BaseException:
        session.rollback()
        _rollback_staging(staged)
        raise

    update_progress(progress, 100, f"Renamed {len(moves)} file(s)")
    return TaskResult(
        summary=f"Renamed {len(moves)} file{'s' if len(moves) != 1 else ''}",
        data={
            "files_considered": len(downloads),
            "files_renamed": len(moves),
            "files_unchanged": unchanged,
        },
    )
