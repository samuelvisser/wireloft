from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models import Episode, Show
from backend.db.models.media_download import EpisodeMediaDownload
from backend.types.download_profile_types import MediaDownloadArtifactStatus
from task_manager.scheduler.operation_control import cancel_operation
from task_manager.tasks.media_download_operations import (
    get_active_media_download_operation,
    prepare_media_download_artifact,
)
from task_manager.tasks.workers.file_watcher.service import resolve_media_download_file


@dataclass(frozen=True)
class EpisodeDownloadScope:
    show: Show
    episode: Episode | None
    downloads: tuple[EpisodeMediaDownload, ...]

    @property
    def local_media_profile_count(self) -> int:
        return len({download.local_media_profile_id for download in self.downloads})

    def result_data(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "show_id": self.show.id,
            "show_slug": self.show.slug,
            "show_title": self.show.title,
            "local_media_profiles": self.local_media_profile_count,
        }
        if self.episode is not None:
            data.update({
                "episode_id": self.episode.id,
                "episode_slug": self.episode.slug,
                "episode_title": self.episode.title,
            })
        return data


def resolve_episode_download_scope(
        s: Session,
        *,
        show_id: int | None = None,
        episode_id: int | None = None,
        local_media_profile_id: int | None = None,
) -> EpisodeDownloadScope:
    """Resolve the common show/episode media rows used by destructive download actions."""
    if (show_id is None) == (episode_id is None):
        raise ValueError("Provide exactly one show id or episode id")

    episode: Episode | None = None
    if episode_id is not None:
        episode = s.get(Episode, episode_id)
        if episode is None:
            raise ValueError(f"Episode {episode_id} no longer exists")
        show = episode.show
    else:
        show = s.get(Show, show_id)
        if show is None:
            raise ValueError(f"Show {show_id} no longer exists")

    downloads = selected_episode_downloads(
        s,
        show_id=show.id,
        episode_id=episode.id if episode is not None else None,
        local_media_profile_id=local_media_profile_id,
    )
    return EpisodeDownloadScope(
        show=show,
        episode=episode,
        downloads=tuple(downloads),
    )


def selected_episode_downloads(
        s: Session,
        *,
        show_id: int,
        episode_id: int | None = None,
        local_media_profile_id: int | None = None,
) -> list[EpisodeMediaDownload]:
    """Return existing episode media rows in the requested show/profile scope."""
    stmt = (
        select(EpisodeMediaDownload)
        .join(Episode, Episode.id == EpisodeMediaDownload.media_item_id)
        .where(Episode.show_id == show_id)
    )
    if episode_id is not None:
        stmt = stmt.where(Episode.id == episode_id)
    if local_media_profile_id is not None:
        stmt = stmt.where(
            EpisodeMediaDownload.local_media_profile_id == local_media_profile_id
        )
    return list(s.scalars(stmt.order_by(EpisodeMediaDownload.id.asc())))


def cancel_active_download_attempts(
        s: Session,
        downloads: list[EpisodeMediaDownload] | tuple[EpisodeMediaDownload, ...],
        *,
        reason: str,
        source: str | None = None,
) -> None:
    """Cancel matching active media.download operations before destructive artifact changes."""
    operation_ids = {
        active.id
        for download in downloads
        for active in (get_active_media_download_operation(s, download.id),)
        if active is not None and (source is None or active.source == source)
    }

    # cancel_operation owns its own short transaction. Drop this session's read
    # transaction first so SQLite never has to upgrade an old snapshot afterwards.
    s.rollback()
    for operation_id in operation_ids:
        try:
            cancel_operation(operation_id, reason=reason, acknowledge=True)
        except ValueError:
            pass
    s.expire_all()


def delete_episode_download_artifact(
        s: Session,
        download: EpisodeMediaDownload,
) -> None:
    """Remove one episode artifact through the canonical MediaDownload lifecycle."""
    if download.artifact_status != MediaDownloadArtifactStatus.ABSENT.value:
        resolve_media_download_file(
            s,
            download,
            release_read_transaction=True,
        )
    prepare_media_download_artifact(s, download)
    s.flush()
