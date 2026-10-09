from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from typing import Optional, Sequence
from zoneinfo import ZoneInfo

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, selectin_polymorphic, selectinload

from backend.db.models import DownloadProfileBase, Episode, PodcastDownloadProfile, Season, SeriesDownloadProfile
from backend.db.models.media_download import EpisodeMediaDownload
from backend.types.download_profile_types import MediaDownloadArtifactStatus
from backend.types.media_download_history_types import MediaDownloadHistoryAction
from backend.types.episode_types import EpisodePublishStatus
from backend.types.media_types import MediaType
from backend.services.media_download_history import record_media_download_history
from backend.utils.episode import episode_identifier_type_predicate
from backend.utils.output_template import resolve_episode_output_path
from config import get_settings
from task_manager.scheduler.db import TaskOperation
from task_manager.scheduler.types import OperationStatus
from task_manager.tasks.media_download_operations import (
    MEDIA_DOWNLOAD_OPERATION_KIND,
    dispatch_queued_media_download_operations,
    get_active_media_download_operation,
    prepare_media_download_artifact,
    remaining_media_download_budget,
)
from task_manager.tasks.workers.file_watcher.service import resolve_media_download_file


def _download_profile_stmt():
    """Load concrete profile subclasses without per-profile inheritance queries."""
    return select(DownloadProfileBase).options(
        selectin_polymorphic(
            DownloadProfileBase,
            [PodcastDownloadProfile, SeriesDownloadProfile],
        ),
        selectinload(SeriesDownloadProfile.seasons),
    )


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
        profile = s.scalars(
            _download_profile_stmt().where(DownloadProfileBase.id == resource_id)
        ).one_or_none()
        if profile is None or not profile.enable_profile:
            return []
        return [profile]

    return list(s.scalars(
        _download_profile_stmt().where(DownloadProfileBase.enable_profile.is_(True))
    ))


def _enabled_profiles_for_show(s: Session, show_id: int) -> Sequence[DownloadProfileBase]:
    return list(s.scalars(
        _download_profile_stmt().where(
            DownloadProfileBase.show_id == show_id,
            DownloadProfileBase.enable_profile.is_(True),
        )
    ))


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def get_download_profile_episodes(
        s: Session,
        profile: DownloadProfileBase,
        *,
        only_episode: Optional[Episode] = None,
) -> list[Episode]:
    """Episodes a Download Profile currently wants represented by artifacts.

    Apply the stable profile predicates in SQL so large shows do not materialize
    thousands of Episode ORM objects merely to discard nearly all of them.
    """
    podcast_profile = (
        profile if isinstance(profile, PodcastDownloadProfile) else None
    )
    series_profile = (
        profile if isinstance(profile, SeriesDownloadProfile) else None
    )

    allowed_types = set(profile.ep_id_type_list)
    if not allowed_types:
        return []

    eligible_statuses = [EpisodePublishStatus.PUBLISHED_FINAL]
    if podcast_profile is not None and podcast_profile.download_with_countdown:
        eligible_statuses.append(EpisodePublishStatus.PUBLISHED_WITH_COUNTDOWN)

    published_at = func.coalesce(Episode.published_date, Episode.went_live_date)
    stmt = select(Episode).where(
        Episode.show_id == profile.show_id,
        Episode.publish_status.in_(eligible_statuses),
        episode_identifier_type_predicate(Episode.episode_identifier, allowed_types),
    )

    if (
        podcast_profile is not None
        and podcast_profile.download_days_in_past > 0
    ):
        cutoff = _utc_now() - timedelta(days=podcast_profile.download_days_in_past)
        # Preserve the old behavior where an episode with no publication instant
        # was not rejected by the days-in-past rule alone.
        stmt = stmt.where(or_(published_at.is_(None), published_at >= cutoff))

    if (
        podcast_profile is not None
        and podcast_profile.download_starting_from is not None
    ):
        wireloft_timezone = ZoneInfo(get_settings().timezone)
        local_start = datetime.combine(
            podcast_profile.download_starting_from,
            time.min,
            tzinfo=wireloft_timezone,
        )
        utc_start = local_start.astimezone(timezone.utc)
        stmt = stmt.where(
            published_at.is_not(None),
            published_at >= utc_start,
        )

    if series_profile is not None:
        allowed_season_ids = {season.id for season in series_profile.seasons}
        season_predicates = []
        if allowed_season_ids:
            season_predicates.append(Episode.season_id.in_(allowed_season_ids))

        if series_profile.include_upcoming_seasons and series_profile.seasons:
            max_chosen_season_index = max(
                season.index for season in series_profile.seasons
            )
            season_predicates.append(
                Episode.season.has(Season.index > max_chosen_season_index)
            )

        if not season_predicates:
            return []
        stmt = stmt.where(or_(*season_predicates))

    needs_global_podcast_scope = (
        podcast_profile is not None
        and podcast_profile.download_episode_count > 0
    )
    if needs_global_podcast_scope:
        scoped_episode_ids = (
            stmt.with_only_columns(Episode.id)
            .order_by(published_at.desc(), Episode.id.desc())
            .limit(podcast_profile.download_episode_count)
        )
        stmt = select(Episode).where(Episode.id.in_(scoped_episode_ids))

    if only_episode is not None:
        stmt = stmt.where(Episode.id == only_episode.id)

    if needs_global_podcast_scope:
        stmt = stmt.order_by(published_at.desc(), Episode.id.desc())

    return list(s.scalars(stmt))


@dataclass(frozen=True)
class DownloadAction:
    """Whether one persistent MediaDownload needs a new media.download operation."""

    media_download_id: int
    needs_operation: bool
    is_redownload: bool = False
    prepare_existing_artifact: bool | None = None

    @property
    def needs_trigger(self) -> bool:
        """Compatibility name for callers while execution is operation-backed."""
        return self.needs_operation


def ensure_episode_download(
        s: Session,
        profile: DownloadProfileBase,
        episode: Episode,
        *,
        defer_artifact_preparation: bool = False,
) -> DownloadAction:
    """Reconcile one desired episode artifact without encoding worker state on it."""
    existing: Optional[EpisodeMediaDownload] = (
        s.query(EpisodeMediaDownload)
        .filter(
            EpisodeMediaDownload.media_item_id == episode.id,
            EpisodeMediaDownload.local_media_profile_id == profile.local_media_profile_id,
        )
        .one_or_none()
    )
    redownload_when_final = (
        isinstance(profile, PodcastDownloadProfile)
        and profile.download_with_countdown
        and profile.redownload_final
        and episode.publish_status == EpisodePublishStatus.PUBLISHED_WITH_COUNTDOWN
    )

    if existing is None:
        download = EpisodeMediaDownload(
            type=MediaType.EPISODE.value,
            media_item_id=episode.id,
            local_media_profile_id=profile.local_media_profile_id,
            download_profile_id=profile.id,
            artifact_status=MediaDownloadArtifactStatus.ABSENT.value,
            file_path="",
            redownload_when_final=redownload_when_final,
        )
        s.add(download)
        s.flush()
        download.file_path = str(resolve_episode_output_path(
            profile.local_media_profile.output_template,
            episode=episode,
            local_media_profile=profile.local_media_profile,
            media_download=download,
        ))
        s.flush()
        record_media_download_history(
            s,
            download.id,
            MediaDownloadHistoryAction.CREATED,
            metadata={
                "file_path": download.file_path,
                "local_media_profile_id": profile.local_media_profile_id,
                "download_profile_id": profile.id,
            },
        )
        return DownloadAction(download.id, True)

    if redownload_when_final and not existing.automatic_retry_suppressed:
        existing.redownload_when_final = True

    target_path = str(resolve_episode_output_path(
        profile.local_media_profile.output_template,
        episode=episode,
        local_media_profile=profile.local_media_profile,
        media_download=existing,
    ))

    if get_active_media_download_operation(s, existing.id) is not None:
        if existing.download_profile_id != profile.id:
            existing.download_profile_id = profile.id
        s.flush()
        return DownloadAction(existing.id, False)

    if existing.artifact_status != MediaDownloadArtifactStatus.ABSENT.value:
        resolve_media_download_file(s, existing)

    if existing.download_profile_id != profile.id:
        existing.download_profile_id = profile.id

    if existing.automatic_retry_suppressed:
        s.flush()
        return DownloadAction(existing.id, False)

    if existing.artifact_status == MediaDownloadArtifactStatus.AVAILABLE.value:
        s.flush()
        return DownloadAction(existing.id, False)

    if defer_artifact_preparation:
        needs_preparation = (
            existing.artifact_status != MediaDownloadArtifactStatus.ABSENT.value
        )
        s.flush()
        return DownloadAction(
            existing.id,
            True,
            prepare_existing_artifact=needs_preparation,
        )

    prepare_media_download_artifact(s, existing)
    existing.file_path = target_path
    s.flush()
    return DownloadAction(existing.id, True)


def remaining_download_budget(s: Session) -> int:
    """Compatibility wrapper: concurrency is now calculated from active TaskRuns."""
    return remaining_media_download_budget(s)


def trigger_next_pending_downloads(s: Session, *, budget: Optional[int] = None) -> int:
    """Compatibility wrapper: pending downloads are durable queued operations."""
    return dispatch_queued_media_download_operations(s, budget=budget)


def _active_media_download_ids(s: Session) -> set[int]:
    """Load active download identities once, rather than querying each old file."""
    return {
        int(download_id)
        for download_id in s.scalars(
            select(TaskOperation.resource_id).where(
                TaskOperation.kind == MEDIA_DOWNLOAD_OPERATION_KIND,
                TaskOperation.resource_type == "media_download",
                TaskOperation.status.in_((
                    OperationStatus.QUEUED.value,
                    OperationStatus.RUNNING.value,
                    OperationStatus.WAITING.value,
                )),
            )
        )
        if download_id is not None
    }


def cleanup_older_episodes(s: Session, profile: PodcastDownloadProfile) -> int:
    """Remove downloads outside the rolling window, optionally including manual ones."""
    count_limit = profile.download_episode_count > 0
    date_limit = profile.download_days_in_past > 0
    if not count_limit and not date_limit:
        return 0
    if date_limit and not profile.delete_older_episodes:
        return 0

    include_manual = (
        profile.delete_older_episodes
        and profile.include_manually_downloaded_episodes
    )
    # A manually downloaded episode has no owning Download Profile. Restrict the
    # opt-in to this show's eligible episode types and Local Media Profile, so a
    # different profile using the same format cannot lose its downloads.
    ownership = EpisodeMediaDownload.download_profile_id == profile.id
    if include_manual:
        eligible_statuses = [EpisodePublishStatus.PUBLISHED_FINAL]
        if profile.download_with_countdown:
            eligible_statuses.append(EpisodePublishStatus.PUBLISHED_WITH_COUNTDOWN)
        ownership = or_(
            ownership,
            and_(
                EpisodeMediaDownload.download_profile_id.is_(None),
                EpisodeMediaDownload.local_media_profile_id == profile.local_media_profile_id,
                Episode.show_id == profile.show_id,
                episode_identifier_type_predicate(Episode.episode_identifier, set(profile.ep_id_type_list)),
                Episode.publish_status.in_(eligible_statuses),
            ),
        )

    stmt = select(EpisodeMediaDownload).where(ownership)
    if include_manual or date_limit:
        stmt = stmt.join(Episode, Episode.id == EpisodeMediaDownload.media_item_id)
    if count_limit:
        # Use exactly the same eligible latest-N set as download selection. A
        # publication-delay window must not make a recent episode look obsolete.
        kept_episode_ids = {
            episode.id for episode in get_download_profile_episodes(s, profile)
        }
        if kept_episode_ids:
            stmt = stmt.where(
                EpisodeMediaDownload.media_item_id.notin_(kept_episode_ids)
            )
        if not profile.delete_older_episodes:
            stmt = stmt.where(
                EpisodeMediaDownload.artifact_status
                == MediaDownloadArtifactStatus.ABSENT.value
            )
        rows = list(s.scalars(stmt))
    else:
        cutoff = _utc_now() - timedelta(days=profile.download_days_in_past)
        rows = list(s.scalars(stmt.where(
            Episode.published_date.is_not(None),
            Episode.published_date < cutoff,
        )))

    active_download_ids = _active_media_download_ids(s) if rows else set()
    removed = 0
    for row in rows:
        # Retain downloads that are queued, waiting, or still executing. A later
        # sweep can remove them once their operation has finished.
        if row.id in active_download_ids:
            continue
        if profile.delete_older_episodes:
            prepare_media_download_artifact(s, row)

        # Retention cleanup is the end of this download's lifetime.
        s.delete(row)
        removed += 1

    if removed:
        s.flush()
    return removed
