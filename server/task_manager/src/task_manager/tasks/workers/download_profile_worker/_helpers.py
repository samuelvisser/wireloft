from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from typing import Optional, Sequence
from zoneinfo import ZoneInfo

from sqlalchemy import exists, false, func, or_, select
from sqlalchemy.orm import Session, selectin_polymorphic, selectinload

from backend.db.models import DownloadProfileBase, Episode, PodcastDownloadProfile, Season, SeriesDownloadProfile
from backend.db.models.Metadata import Metadata
from backend.db.models.media_download import EpisodeMediaDownload
from backend.types.download_profile_types import MediaDownloadArtifactStatus
from backend.types.media_download_history_types import MediaDownloadHistoryAction
from backend.types.episode_types import EpisodePublishStatus
from backend.types.media_types import MediaType
from backend.services.media_download_history import record_media_download_history
from backend.utils.output_template import resolve_episode_output_path
from config import get_settings
from task_manager.tasks.helpers.episodes.automatic_download_timing import (
    AUTOMATIC_DOWNLOAD_DELAY_META_KEY,
    is_trusted_automatic_download_delay_value,
)
from task_manager.tasks.helpers.episodes.metadata import ensure_utc
from task_manager.tasks.media_download_operations import (
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


def automatic_episode_download_ready_at(episode: Episode) -> datetime | None:
    """Return the earliest instant an automatic episode download may start."""
    delay_minutes = (
        get_settings().download_settings.automatic_episode_download_delay_minutes
    )
    if delay_minutes <= 0:
        return None

    clocks: list[datetime] = []
    if episode.published_date is not None:
        clocks.append(ensure_utc(episode.published_date))

    transition = next(
        (
            item
            for item in episode.meta_items
            if (
                item.key == AUTOMATIC_DOWNLOAD_DELAY_META_KEY
                and is_trusted_automatic_download_delay_value(item.value)
            )
        ),
        None,
    )
    if transition is not None and transition.updated_at is not None:
        clocks.append(ensure_utc(transition.updated_at))

    if not clocks:
        return None
    return max(clocks) + timedelta(minutes=delay_minutes)


def _episode_identifier_type_predicate(allowed_types: set[str]):
    patterns = {
        "ep": "ep.%",
        "ep-extra": "ep-extra.%",
        "trailer": "trailer.%",
        "aux": "aux.%",
    }
    predicates = [
        Episode.episode_identifier.like(patterns[episode_type])
        for episode_type in allowed_types
        if episode_type in patterns
    ]
    return or_(*predicates) if predicates else false()


def get_download_profile_episodes(
        s: Session,
        profile: DownloadProfileBase,
        *,
        only_episode: Optional[Episode] = None,
        apply_automatic_download_delay: bool = True,
) -> list[Episode]:
    """Episodes a Download Profile currently wants represented by artifacts.

    Apply the stable profile predicates in SQL so large shows do not materialize
    thousands of Episode ORM objects merely to discard nearly all of them.

    Automatic downloads also observe the configured post-publication delay. The
    delay is applied after a Podcast Download Profile's episode-count scope is
    selected so a newly published episode does not temporarily backfill an older
    episode outside that scope.
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
        _episode_identifier_type_predicate(allowed_types),
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

    if apply_automatic_download_delay:
        delay_minutes = (
            get_settings().download_settings.automatic_episode_download_delay_minutes
        )
        if delay_minutes > 0:
            cutoff = _utc_now() - timedelta(minutes=delay_minutes)
            recent_trusted_monitor_transition = exists(
                select(Metadata.id).where(
                    Metadata.parent_table == Episode.__tablename__,
                    Metadata.parent_id == Episode.id,
                    Metadata.key == AUTOMATIC_DOWNLOAD_DELAY_META_KEY,
                    Metadata.value.like("monitor:%"),
                    Metadata.updated_at > cutoff,
                )
            )
            # Daily Wire's publishedAt is the normal clock and remains the only
            # clock after startup/backfill. A later WireLoft timestamp participates
            # only when the pending monitor proved it followed the live lifecycle
            # continuously from the transition into LIVE.
            stmt = stmt.where(
                or_(Episode.published_date.is_(None), Episode.published_date <= cutoff),
                ~recent_trusted_monitor_transition,
            )

    if needs_global_podcast_scope:
        stmt = stmt.order_by(published_at.desc(), Episode.id.desc())

    return list(s.scalars(stmt))


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

    if existing is None:
        download = EpisodeMediaDownload(
            type=MediaType.EPISODE.value,
            media_item_id=episode.id,
            local_media_profile_id=profile.local_media_profile_id,
            download_profile_id=profile.id,
            artifact_status=MediaDownloadArtifactStatus.ABSENT.value,
            file_path="",
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
        if not _wants_redownload(profile, episode, existing):
            s.flush()
            return DownloadAction(existing.id, False)
        prepare_media_download_artifact(s, existing)
        existing.file_path = target_path
        s.flush()
        return DownloadAction(existing.id, True, is_redownload=True)

    prepare_media_download_artifact(s, existing)
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
    """Reconcile artifacts that have fallen outside a podcast retention limit."""
    if profile.download_episode_count > 0:
        kept_episode_ids = {
            episode.id
            for episode in get_download_profile_episodes(
                s,
                profile,
                apply_automatic_download_delay=False,
            )
        }
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
        cutoff = _utc_now() - timedelta(days=profile.download_days_in_past)
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
        if profile.delete_older_episodes:
            # Retention removes only the current artifact. MediaDownload identity
            # and historical facts remain durable after the first successful file.
            prepare_media_download_artifact(s, row)
        row.download_profile_id = None

    if rows:
        s.flush()
    return len(rows)
