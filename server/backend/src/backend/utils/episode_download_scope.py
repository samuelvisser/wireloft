from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass, field, replace
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from backend.db.models import Episode, Show
from backend.db.models.media_download import EpisodeMediaDownload


@dataclass(frozen=True)
class EpisodeDownloadScope:
    """Reusable SQL-backed selection of episode MediaDownloads."""

    show: Show
    episode: Episode | None
    downloads: tuple[EpisodeMediaDownload, ...]
    _session: Session = field(repr=False, compare=False)
    _local_media_profile_id: int | None = field(default=None, repr=False, compare=False)
    _artifact_statuses: frozenset[str] | None = field(default=None, repr=False, compare=False)

    @staticmethod
    def _downloads(
            s: Session,
            *,
            show_id: int,
            episode_id: int | None,
            local_media_profile_id: int | None,
            artifact_statuses: frozenset[str] | None,
    ) -> tuple[EpisodeMediaDownload, ...]:
        stmt = (
            select(EpisodeMediaDownload)
            .options(joinedload(EpisodeMediaDownload.local_media_profile))
            .join(Episode, Episode.id == EpisodeMediaDownload.media_item_id)
            .where(Episode.show_id == show_id)
        )
        if episode_id is not None:
            stmt = stmt.where(Episode.id == episode_id)
        if local_media_profile_id is not None:
            stmt = stmt.where(
                EpisodeMediaDownload.local_media_profile_id
                == local_media_profile_id
            )
        if artifact_statuses is not None:
            stmt = stmt.where(
                EpisodeMediaDownload.artifact_status.in_(artifact_statuses)
            )
        return tuple(
            s.scalars(stmt.order_by(EpisodeMediaDownload.id.asc()))
        )

    @classmethod
    def resolve(
            cls,
            s: Session,
            *,
            show_id: int | None = None,
            episode_id: int | None = None,
            local_media_profile_id: int | None = None,
            artifact_statuses: Collection[str] | None = None,
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

        accepted_statuses = (
            frozenset(artifact_statuses)
            if artifact_statuses is not None
            else None
        )
        downloads = cls._downloads(
            s,
            show_id=show.id,
            episode_id=episode.id if episode is not None else None,
            local_media_profile_id=local_media_profile_id,
            artifact_statuses=accepted_statuses,
        )
        return cls(
            show=show,
            episode=episode,
            downloads=downloads,
            _session=s,
            _local_media_profile_id=local_media_profile_id,
            _artifact_statuses=accepted_statuses,
        )

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
        """Return this scope narrowed in SQL by profile and/or artifact state."""
        selected_profile_id = (
            local_media_profile_id
            if local_media_profile_id is not None
            else self._local_media_profile_id
        )
        selected_statuses = (
            frozenset(artifact_statuses)
            if artifact_statuses is not None
            else self._artifact_statuses
        )
        if (
            selected_profile_id == self._local_media_profile_id
            and selected_statuses == self._artifact_statuses
        ):
            return self

        downloads = self._downloads(
            self._session,
            show_id=self.show.id,
            episode_id=self.episode.id if self.episode is not None else None,
            local_media_profile_id=selected_profile_id,
            artifact_statuses=selected_statuses,
        )
        return replace(
            self,
            downloads=downloads,
            _local_media_profile_id=selected_profile_id,
            _artifact_statuses=selected_statuses,
        )

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
