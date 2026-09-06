from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models import DownloadProfileBase, Episode, PodcastDownloadProfile, SeriesDownloadProfile
from backend.db.models.media_download import EpisodeMediaDownload
from backend.types.download_profile_types import MediaDownloadArtifactStatus
from backend.types.episode_types import EpisodePublishStatus
from backend.types.media_types import MediaType
from backend.utils.download_files import remove_download_artifacts
from backend.utils.output_template import resolve_episode_output_path
from task_manager.tasks.media_download_operations import (
    dispatch_queued_media_download_operations,
    get_active_media_download_operation,
    prepare_media_download_artifact,
    remaining_media_download_budget,
)

logger = logging.getLogger(__name__)


def resolve_target_profiles(
        s: Session, *, resource_type: Optional[str], resource_id: Optional[int]
) -> Sequence[DownloadProfileBase]:
    """Resolve which enabled Download Profiles a worker run should act on."""
    if resource_type == "episode":
        episode = s.get(Episode, resource_id) if resource_id is not None else None
        if episode is None:
            return []
        return _enabled_profiles_for_show(s, episode.show_id)

    if resource_type == "show":
        if resource_id is None:
            return []
        return _enabled_profiles_for_show(s, resource_id)

    if resource_type in {"download_profile", "download_profile_series"} and resource_id:
        profile = s.get(DownloadProfileBase, resource_id)
        if profile is None or not profile.enable_profile:
            return []
        return [profile]

    return list(
        s.execute(
            select(DownloadProfileBase).where(DownloadProfileBase.enable_profile.is_(True))
        ).scalars()
    )


def _enabled_profiles_for_show(s: Session, show_id: int) -> Sequence[DownloadProfileBase]:
    return list(
        s.execute(select(DownloadProfileBase).where(
            DownloadProfileBase.show_id == show_id,
            DownloadProfileBase.enable_profile.is_(True),
        )).scalars()
    )


def _episode_type_prefix(episode: Episode) -> str:
    return episode.episode_identifier.split(".", 1)[0]


def _episode_recency_key(episode: Episode) -> tuple[datetime, int]:
    return episode.published_date or episode.went_live_date or datetime.min, episode.id or 0


def _utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def get_download_profile_episodes(
        s: Session,
        profile: DownloadProfileBase,
        *,
        only_episode: Optional[Episode] = None,
) -> list[Episode]:
    """Episodes a Download Profile currently wants represented by artifacts."""
    is_podcast = isinstance(profile, PodcastDownloadProfile)
    needs_global_podcast_scope = is_podcast and profile.download_episode_count > 0

    if only_episode is not None and not needs_global_podcast_scope:
        candidates: list[Episode] = [only_episode]
    else:
        candidates = list(
            s.execute(select(Episode).where(Episode.show_id == profile.show_id)).scalars()
        )

    allowed_types = set(profile.ep_id_type_list)

    cutoff: Optional[datetime] = None
    if is_podcast and profile.download_days_in_past > 0:
        cutoff = _utc_now_naive() - timedelta(days=profile.download_days_in_past)

    allowed_season_ids: Optional[set[int]] = None
    max_chosen_season_index: Optional[int] = None
    include_upcoming = False
    if isinstance(profile, SeriesDownloadProfile):
        allowed_season_ids = {season.id for season in profile.seasons}
        if profile.seasons:
            max_chosen_season_index = max(season.index for season in profile.seasons)
        include_upcoming = profile.include_upcoming_seasons

    eligible: list[Episode] = []
    for episode in candidates:
        if _episode_type_prefix(episode) not in allowed_types:
            continue

        # Publication status is the single eligibility authority. NO_USABLE_MEDIA
        # and DW_PROCESSING are both naturally excluded because neither is a
        # downloadable publication state, with no placeholder-specific exception.
        publish_status = episode.publish_status
        if publish_status == EpisodePublishStatus.PUBLISHED_FINAL.value:
            pass
        elif publish_status == EpisodePublishStatus.PUBLISHED_WITH_COUNTDOWN.value:
            if not (is_podcast and profile.download_with_countdown):
                continue
        else:
            continue

        if cutoff is not None:
            published = episode.published_date or episode.went_live_date
            if published is not None and published < cutoff:
                continue

        if allowed_season_ids is not None and episode.season_id not in allowed_season_ids:
            is_upcoming = (
                include_upcoming
                and max_chosen_season_index is not None
                and episode.season is not None
                and episode.season.index > max_chosen_season_index
            )
            if not is_upcoming:
                continue

        eligible.append(episode)

    if is_podcast and profile.download_episode_count > 0:
        eligible.sort(key=_episode_recency_key, reverse=True)
        eligible = eligible[:profile.download_episode_count]

    if only_episode is not None:
        eligible = [episode for episode in eligible if episode.id == only_episode.id]

    return eligible


@dataclass(frozen=True)
class DownloadAction:
    """Whether one persistent MediaDownload needs a new media.download operation."""

    media_download_id: int
    needs_operation: bool
    is_redownload: bool = False

    @property
    def needs_trigger(self) -> bool:
        """Compatibility name for callers while execution is operation-backed."""
        return self.needs_operation


def ensure_episode_download(s: Session, profile: DownloadProfileBase, episode: Episode) -> DownloadAction:
    """Reconcile one desired episode artifact without encoding worker state on it."""
    existing: Optional[EpisodeMediaDownload] = (
        s.query(EpisodeMediaDownload)
        .filter(
            EpisodeMediaDownload.media_item_id == episode.id,
            EpisodeMediaDownload.local_media_profile_id == profile.local_media_profile_id,
        )
        .one_or_none()
    )

    target_path = str(resolve_episode_output_path(
        profile.local_media_profile.output_template,
        episode=episode,
    ))

    if existing is None:
        download = EpisodeMediaDownload(
            type=MediaType.EPISODE.value,
            media_item_id=episode.id,
            local_media_profile_id=profile.local_media_profile_id,
            download_profile_id=profile.id,
            artifact_status=MediaDownloadArtifactStatus.ABSENT.value,
            file_path=target_path,
        )
        s.add(download)
        s.flush()
        return DownloadAction(download.id, True)

    if existing.download_profile_id != profile.id:
        existing.download_profile_id = profile.id

    if get_active_media_download_operation(s, existing.id) is not None:
        s.flush()
        return DownloadAction(existing.id, False)

    if existing.automatic_retry_suppressed:
        s.flush()
        return DownloadAction(existing.id, False)

    if existing.artifact_status == MediaDownloadArtifactStatus.AVAILABLE.value:
        if not _wants_redownload(profile, episode, existing):
            s.flush()
            return DownloadAction(existing.id, False)
        prepare_media_download_artifact(existing)
        existing.file_path = target_path
        s.flush()
        return DownloadAction(existing.id, True, is_redownload=True)

    prepare_media_download_artifact(existing)
    existing.file_path = target_path
    s.flush()
    return DownloadAction(existing.id, True)


def _wants_redownload(profile: DownloadProfileBase, episode: Episode, existing: EpisodeMediaDownload) -> bool:
    return (
        isinstance(profile, PodcastDownloadProfile)
        and profile.download_with_countdown
        and profile.redownload_final
        and episode.publish_status == EpisodePublishStatus.PUBLISHED_FINAL.value
        and existing.downloaded_publish_status == EpisodePublishStatus.PUBLISHED_WITH_COUNTDOWN.value
    )


def remaining_download_budget(s: Session) -> int:
    """Compatibility wrapper: concurrency is now calculated from active TaskRuns."""
    return remaining_media_download_budget(s)


def trigger_next_pending_downloads(s: Session, *, budget: Optional[int] = None) -> int:
    """Compatibility wrapper: pending downloads are durable queued operations."""
    return dispatch_queued_media_download_operations(s, budget=budget)


def cleanup_older_episodes(s: Session, profile: PodcastDownloadProfile) -> int:
    """Remove artifact rows/operations that have fallen outside a podcast limit."""
    if profile.download_episode_count > 0:
        kept_episode_ids = {episode.id for episode in get_download_profile_episodes(s, profile)}
        stmt = select(EpisodeMediaDownload).where(
            EpisodeMediaDownload.download_profile_id == profile.id,
        )
        if kept_episode_ids:
            stmt = stmt.where(EpisodeMediaDownload.media_item_id.notin_(kept_episode_ids))
        candidates = list(s.execute(stmt).scalars())

        if profile.delete_older_episodes:
            rows = candidates
        else:
            rows = [
                row for row in candidates
                if row.artifact_status == MediaDownloadArtifactStatus.ABSENT.value
            ]
    elif profile.download_days_in_past > 0:
        if not profile.delete_older_episodes:
            return 0
        cutoff = _utc_now_naive() - timedelta(days=profile.download_days_in_past)
        rows = list(s.execute(
            select(EpisodeMediaDownload)
            .join(Episode, Episode.id == EpisodeMediaDownload.media_item_id)
            .where(
                EpisodeMediaDownload.download_profile_id == profile.id,
                Episode.published_date.is_not(None),
                Episode.published_date < cutoff,
            )
        ).scalars())
    else:
        return 0

    for row in rows:
        if row.artifact_status == MediaDownloadArtifactStatus.AVAILABLE.value:
            _delete_download_file(row.file_path)
        else:
            remove_download_artifacts(row.file_path)
        s.delete(row)
    if rows:
        s.flush()
    return len(rows)


def _delete_download_file(file_path: str) -> None:
    try:
        path = Path(file_path)
        if path.exists():
            path.unlink()
    except OSError:
        logger.warning("Could not delete download file '%s'", file_path, exc_info=True)
