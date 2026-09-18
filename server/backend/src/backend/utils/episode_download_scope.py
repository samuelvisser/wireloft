from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass, replace
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from backend.db.models import Episode, Show
from backend.db.models.media_download import EpisodeMediaDownload


@dataclass(frozen=True)
class EpisodeDownloadScope:
    """Reusable selection of episode MediaDownloads.

    The base scope is anchored to either one show or one episode. Actions can then
    narrow it to one Local Media Profile (or leave it as all profiles), and may
    optionally restrict it to artifact states relevant to that action.
    """

    show: Show
    episode: Episode | None
    downloads: tuple[EpisodeMediaDownload, ...]

    @classmethod
    def resolve(
            cls,
            s: Session,
            *,
            show_id: int | None = None,
            episode_id: int | None = None,
    ) -> EpisodeDownloadScope:
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

        stmt = (
            select(EpisodeMediaDownload)
            .options(joinedload(EpisodeMediaDownload.local_media_profile))
            .join(Episode, Episode.id == EpisodeMediaDownload.media_item_id)
            .where(Episode.show_id == show.id)
        )
        if episode is not None:
            stmt = stmt.where(Episode.id == episode.id)

        downloads = tuple(s.scalars(stmt.order_by(EpisodeMediaDownload.id.asc())))
        return cls(show=show, episode=episode, downloads=downloads)

    @property
    def local_media_profile_ids(self) -> tuple[int, ...]:
        return tuple(sorted({download.local_media_profile_id for download in self.downloads}))

    @property
    def local_media_profile_count(self) -> int:
        return len(self.local_media_profile_ids)

    @property
    def episode_ids(self) -> tuple[int, ...]:
        return tuple(sorted({download.media_item_id for download in self.downloads}))

    def select(
            self,
            *,
            local_media_profile_id: int | None = None,
            artifact_statuses: Collection[str] | None = None,
    ) -> EpisodeDownloadScope:
        """Return this scope narrowed by profile and/or artifact state."""
        downloads = self.downloads
        if local_media_profile_id is not None:
            downloads = tuple(
                download
                for download in downloads
                if download.local_media_profile_id == local_media_profile_id
            )
        if artifact_statuses is not None:
            accepted_statuses = frozenset(artifact_statuses)
            downloads = tuple(
                download
                for download in downloads
                if download.artifact_status in accepted_statuses
            )
        if downloads == self.downloads:
            return self
        return replace(self, downloads=downloads)

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
