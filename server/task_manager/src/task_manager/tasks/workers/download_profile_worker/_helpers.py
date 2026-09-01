from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.db.models import DownloadProfileBase, Episode, PodcastDownloadProfile, SeriesDownloadProfile
from backend.db.models.media_download import EpisodeMediaDownload, MediaDownloadBase
from backend.types.download_profile_types import MediaDownloadStatus
from backend.types.episode_types import EpisodePublishStatus
from backend.types.media_types import MediaType
from backend.utils.output_template import resolve_episode_output_path
from config import get_settings
from task_manager.scheduler.executor import trigger_now

logger = logging.getLogger(__name__)

# Statuses that are safe to (re)trigger: nothing is actively running or already finished.
_TRIGGERABLE_STATUSES = {
    MediaDownloadStatus.PENDING.value,
    MediaDownloadStatus.ERROR.value,
    MediaDownloadStatus.MISSING.value,
    MediaDownloadStatus.CORRUPTED.value,
}

# CANCELLED is deliberately absent: a profile sweep or cron run must not undo
# the user's explicit stop. Only a manual download request or Retry re-arms it.
_COMPLETED_STATUSES = {MediaDownloadStatus.DOWNLOADED.value, MediaDownloadStatus.REDOWNLOADED.value}
_NEEDS_RESET_BEFORE_TRIGGER = _TRIGGERABLE_STATUSES - {MediaDownloadStatus.PENDING.value}


def resolve_target_profiles(
        s: Session, *, resource_type: Optional[str], resource_id: Optional[int]
) -> Sequence[DownloadProfileBase]:
    """Resolve which enabled Download Profiles a worker run should act on.

    ``resource_type``/``resource_id`` come straight from the triggering event or
    cron/manual call: an ``episode`` or ``show`` id scopes the run to that show's
    profiles; a ``download_profile`` id runs just that profile; anything else
    (cron's ``resource_id=0``, ``app.startup``'s ``None``) sweeps every enabled
    profile in the system.
    """
    if resource_type == "episode":
        episode = s.get(Episode, resource_id) if resource_id is not None else None
        if episode is None:
            return []
        return _enabled_profiles_for_show(s, episode.show_id)

    if resource_type == "show":
        if resource_id is None:
            return []
        return _enabled_profiles_for_show(s, resource_id)

    if resource_type == "download_profile" and resource_id:
        profile = s.get(DownloadProfileBase, resource_id)
        if profile is None or not profile.enable_profile:
            return []
        return [profile]

    # Global sweep: cron, app.startup, or an explicit resource_id of 0/None
    return list(
        s.execute(
            select(DownloadProfileBase).where(DownloadProfileBase.enable_profile.is_(True))
        ).scalars()
    )


def _enabled_profiles_for_show(s: Session, show_id: int) -> Sequence[DownloadProfileBase]:
    return list(
        s.execute(
            select(DownloadProfileBase).where(
                DownloadProfileBase.show_id == show_id,
                DownloadProfileBase.enable_profile.is_(True),
            )
        ).scalars()
    )


def _episode_type_prefix(episode: Episode) -> str:
    """The EpIdType prefix of an episode identifier, e.g. "ep" from "ep.101"."""
    return episode.episode_identifier.split(".", 1)[0]


def _episode_recency_key(episode: Episode) -> tuple[datetime, int]:
    """Sort podcast episodes newest-first with a deterministic id tie-breaker."""
    return episode.published_date or episode.went_live_date or datetime.min, episode.id or 0


def _utc_now_naive() -> datetime:
    """Now in UTC without tzinfo.

    Episode date columns are plain ``DateTime`` (no ``timezone=True``), so SQLite
    round-trips them as naive datetimes that represent UTC wall-clock time. Every
    comparison against them has to use the same naive-UTC convention or it either
    raises (aware - naive) or silently compares against the wrong instant.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


def get_download_profile_episodes(
        s: Session,
        profile: DownloadProfileBase,
        *,
        only_episode: Optional[Episode] = None,
) -> list[Episode]:
    """Episodes a Download Profile currently wants downloaded.

    Applies the filters shared by every profile type (episode type, publish
    status) plus the type-specific scope: a recency window or latest-episode
    count for podcasts, and a season selection for series.
    """
    is_podcast = isinstance(profile, PodcastDownloadProfile)
    needs_global_podcast_scope = is_podcast and profile.download_episode_count > 0

    # An episode-count limit is relative to every eligible episode in the show.
    # Even an event-triggered single-episode run therefore has to calculate the
    # global top N first and only then decide whether the triggering episode is
    # inside that set.
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
        # A "No Show Today" placeholder has no real media behind it (Daily
        # Wire's own episode-details endpoint 404s for it) and must never be
        # queued, regardless of what episode types the profile otherwise wants.
        if episode.is_no_show_today:
            continue

        if _episode_type_prefix(episode) not in allowed_types:
            continue

        status = episode.publish_status
        if status == EpisodePublishStatus.PUBLISHED_FINAL.value:
            pass
        elif status == EpisodePublishStatus.PUBLISHED_WITH_COUNTDOWN.value:
            if not (is_podcast and profile.download_with_countdown):
                continue
        else:
            # Scheduled, delayed, live or still processing on DW: never downloadable yet
            continue

        if cutoff is not None:
            published = episode.published_date or episode.went_live_date
            if published is not None and published < cutoff:
                continue

        if allowed_season_ids is not None:
            if episode.season_id not in allowed_season_ids:
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
    """What (if anything) a profile needs done for one episode's download row."""
    media_download_id: int
    attempt_generation: int
    needs_trigger: bool
    is_redownload: bool = False


def ensure_episode_download(s: Session, profile: DownloadProfileBase, episode: Episode) -> DownloadAction:
    """Create/reuse the media download row an episode needs under a profile.

    Mirrors the manual download path (one row per episode + Local Media Profile)
    but never conflicts: an in-flight or already-finished download is left alone
    (unless a podcast profile wants the countdown-era file replaced), and a
    pending/errored row is (re)armed for the caller to trigger.
    """
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
            download_status=MediaDownloadStatus.PENDING.value,
            file_path=str(resolve_episode_output_path(profile.local_media_profile.output_template, episode=episode)),
            progress=0,
        )
        s.add(download)
        s.flush()
        return DownloadAction(
            media_download_id=download.id,
            attempt_generation=download.attempt_generation,
            needs_trigger=True,
        )

    # A manual download may already occupy this (episode, local media profile)
    # pairing without attribution; adopt it so it counts towards this profile.
    if existing.download_profile_id is None:
        existing.download_profile_id = profile.id

    if existing.download_status in _TRIGGERABLE_STATUSES:
        if existing.download_status in _NEEDS_RESET_BEFORE_TRIGGER:
            _reset_download(existing)
        s.flush()
        return DownloadAction(
            media_download_id=existing.id,
            attempt_generation=existing.attempt_generation,
            needs_trigger=True,
        )

    if existing.download_status in _COMPLETED_STATUSES and _wants_redownload(profile, episode, existing):
        _reset_download(existing)
        s.flush()
        return DownloadAction(
            media_download_id=existing.id,
            attempt_generation=existing.attempt_generation,
            needs_trigger=True,
            is_redownload=True,
        )

    s.flush()
    return DownloadAction(
        media_download_id=existing.id,
        attempt_generation=existing.attempt_generation,
        needs_trigger=False,
    )


def _wants_redownload(profile: DownloadProfileBase, episode: Episode, existing: EpisodeMediaDownload) -> bool:
    """Whether an already-downloaded file needs replacing with the final version.

    Only true for a podcast profile that both downloads countdown-era episodes
    *and* wants them replaced once final, and only when the file we actually
    have on disk was fetched while the episode was still in its countdown
    phase: a file downloaded after the episode was already final never needs
    redownloading, no matter how "final" it looks now.
    """
    return (
        isinstance(profile, PodcastDownloadProfile)
        and profile.download_with_countdown
        and profile.redownload_final
        and episode.publish_status == EpisodePublishStatus.PUBLISHED_FINAL.value
        and existing.downloaded_publish_status == EpisodePublishStatus.PUBLISHED_WITH_COUNTDOWN.value
    )


def _reset_download(download: MediaDownloadBase) -> None:
    download.attempt_generation += 1
    download.download_status = MediaDownloadStatus.PENDING.value
    download.progress = 0
    download.error_message = None
    download.downloaded_bytes = None
    download.format_downloaded = None
    download.started_at = None
    download.finished_at = None


def remaining_download_budget(s: Session) -> int:
    """How many new downloads may be triggered right now, per the configured cap."""
    max_concurrent = get_settings().download_settings.max_concurrent_downloads
    in_flight = s.execute(
        select(func.count())
        .select_from(MediaDownloadBase)
        .where(MediaDownloadBase.download_status == MediaDownloadStatus.DOWNLOADING.value)
    ).scalar_one()
    return max(0, max_concurrent - in_flight)


def trigger_next_pending_downloads(s: Session, *, budget: Optional[int] = None) -> int:
    """Start queued episode or movie downloads as the concurrency budget allows.

    A Download Profile sweep can only trigger up to the budget available at
    that moment and leaves the rest PENDING; without this, those would sit
    idle until the next full sweep (the verification cron, by default every
    couple of hours). Call this whenever a download finishes (success or
    failure alike free up a concurrency slot) so the queue keeps draining
    itself between sweeps instead of stalling after the first batch.
    """
    if budget is None:
        budget = remaining_download_budget(s)
    if budget <= 0:
        return 0

    stmt = (
        select(MediaDownloadBase)
        .where(MediaDownloadBase.download_status == MediaDownloadStatus.PENDING.value)
        .order_by(MediaDownloadBase.id)
        .limit(budget)
    )
    pending = list(s.execute(stmt).scalars())
    for download in pending:
        if download.type == "movie":
            trigger_now(
                def_key="download_movie",
                resource_type="movie",
                resource_id=download.media_item_id,
                media_download_id=download.id,
                attempt_generation=download.attempt_generation,
            )
            continue
        trigger_now(
            def_key="download_episode",
            resource_type="episode",
            resource_id=download.media_item_id,
            media_download_id=download.id,
            attempt_generation=download.attempt_generation,
            is_redownload=bool(getattr(download, "is_redownload_attempt", False)),
        )
    return len(pending)


def cleanup_older_episodes(s: Session, profile: PodcastDownloadProfile) -> int:
    """Reconcile queued/completed downloads that fell outside a podcast limit."""
    if profile.download_episode_count > 0:
        kept_episode_ids = {episode.id for episode in get_download_profile_episodes(s, profile)}

        # A pending row outside latest-N must be removed even when the user wants
        # to keep already-downloaded older files; otherwise queue draining could
        # still start an episode the profile no longer wants. Other stale rows
        # are removed only when file retention is enabled, matching the existing
        # delete-older behavior for completed downloads.
        removable_statuses = {MediaDownloadStatus.PENDING.value}
        if profile.delete_older_episodes:
            removable_statuses |= _TRIGGERABLE_STATUSES | _COMPLETED_STATUSES

        stmt = select(EpisodeMediaDownload).where(
            EpisodeMediaDownload.download_profile_id == profile.id,
            EpisodeMediaDownload.download_status.in_(removable_statuses),
        )
        if kept_episode_ids:
            stmt = stmt.where(EpisodeMediaDownload.media_item_id.notin_(kept_episode_ids))
        rows = list(s.execute(stmt).scalars())
    elif profile.download_days_in_past > 0:
        if not profile.delete_older_episodes:
            return 0
        cutoff = _utc_now_naive() - timedelta(days=profile.download_days_in_past)
        stmt = (
            select(EpisodeMediaDownload)
            .join(Episode, Episode.id == EpisodeMediaDownload.media_item_id)
            .where(
                EpisodeMediaDownload.download_profile_id == profile.id,
                EpisodeMediaDownload.download_status.in_(_COMPLETED_STATUSES),
                Episode.published_date.is_not(None),
                Episode.published_date < cutoff,
            )
        )
        rows = list(s.execute(stmt).scalars())
    else:
        return 0

    for row in rows:
        if row.download_status in _COMPLETED_STATUSES:
            _delete_download_file(row.file_path)
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
