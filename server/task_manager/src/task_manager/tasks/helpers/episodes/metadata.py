from __future__ import annotations

from datetime import datetime, timedelta, timezone

from backend.db.models import Episode
from backend.types.episode_types import EpisodePublishStatus
from config import get_settings
from config.settings.submodels import parse_metadata_refresh_intervals
from dailywire_api.records import DwEpisodeDetailRecord


METADATA_REFRESH_REQUESTED_EVENT = "episode.metadata_refresh_requested"


def ensure_utc(value: datetime) -> datetime:
    """Return a timezone-aware UTC datetime, treating legacy naive values as UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def metadata_refresh_offsets_seconds() -> tuple[int, ...]:
    return parse_metadata_refresh_intervals(
        get_settings().new_episode_schedule.metadata_refresh_intervals
    )


def metadata_watch_deadline(published_date: datetime | None) -> datetime | None:
    if published_date is None:
        return None
    return ensure_utc(published_date) + timedelta(
        seconds=metadata_refresh_offsets_seconds()[-1]
    )


def metadata_watch_expired(
        published_date: datetime | None,
        *,
        now: datetime | None = None,
) -> bool:
    """Whether the last configured metadata refresh offset has already passed."""
    deadline = metadata_watch_deadline(published_date)
    if deadline is None:
        return True
    current = ensure_utc(now or datetime.now(timezone.utc))
    return current >= deadline


def metadata_is_final_for_new_episode(
        publish_status: str | EpisodePublishStatus,
        published_date: datetime | None,
        *,
        now: datetime | None = None,
) -> bool:
    """Choose the initial persistent metadata-finality state for a new episode."""
    status = (
        publish_status.value
        if isinstance(publish_status, EpisodePublishStatus)
        else str(publish_status)
    )
    if status != EpisodePublishStatus.PUBLISHED_FINAL.value:
        return False
    return metadata_watch_expired(published_date, now=now)


def update_episode_from_dailywire(
        episode: Episode,
        dw_episode: DwEpisodeDetailRecord,
) -> None:
    """Refresh Daily Wire metadata without changing WireLoft-owned lifecycle state."""
    protected_fields = {
        "id",
        "show_id",
        "season_id",
        "index",
        "episode_identifier",
        "publish_status",
        "metadata_is_final",
    }
    model_fields = set(Episode.__mapper__.attrs.keys())
    for field, value in dw_episode.model_dump(
            mode="python",
            by_alias=False,
    ).items():
        if field in model_fields and field not in protected_fields:
            setattr(episode, field, value)
