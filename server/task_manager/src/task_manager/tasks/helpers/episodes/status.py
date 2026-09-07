from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from backend.types.episode_types import EpisodePublishStatus
from config import get_settings
from controller.m3u8 import get_vod_info
from dailywire_api.records import DwEpisodeDetailRecord, DwEpisodeRecord
from .metadata import ensure_utc
from .no_show import is_no_show_today_slug


_AUTHORITATIVE_REMOTE_STATUSES = {
    EpisodePublishStatus.SCHEDULED,
    EpisodePublishStatus.DELAYED,
    EpisodePublishStatus.LIVE,
}


@dataclass(frozen=True)
class EpisodeRemoteSnapshot:
    """Facts observed from one Daily Wire detail response, without lifecycle timers."""

    status: EpisodePublishStatus
    has_usable_media: bool
    hls_duration_seconds: float | None = None


def _static_status(ep: DwEpisodeRecord) -> EpisodePublishStatus | None:
    upstream = ep.publish_status.upper()
    if "SCHEDULED" in upstream:
        return EpisodePublishStatus.SCHEDULED
    if "LIVE" in upstream:
        return EpisodePublishStatus.LIVE
    if "delayed-start" in ep.slug.casefold():
        return EpisodePublishStatus.DELAYED
    return None


def _normalize_status(
    value: str | EpisodePublishStatus | None,
) -> EpisodePublishStatus | None:
    if value is None:
        return None
    if isinstance(value, EpisodePublishStatus):
        return value
    try:
        return EpisodePublishStatus(value)
    except ValueError:
        return None


def _minutes_since(value: datetime | None, *, now: datetime | None = None) -> float | None:
    if value is None:
        return None
    current = ensure_utc(now or datetime.now(timezone.utc))
    return max(0.0, (current - ensure_utc(value)).total_seconds() / 60.0)


def _hls_duration(detail: DwEpisodeDetailRecord) -> float | None:
    if not detail.video_url:
        return None
    return float(get_vod_info(detail.video_url).seconds)


def has_usable_media(
    detail: DwEpisodeDetailRecord,
    *,
    hls_duration_seconds: float | None = None,
) -> bool:
    """Whether the detail record exposes settled media WireLoft may publish.

    Recovery requires all three agreed signals: a media playlist, Daily Wire
    metadata duration above 12 seconds, and an HLS duration above 12 seconds.
    The characteristic processing state therefore intentionally does not qualify
    even though its HLS playlist can already be playable.
    """
    if (
        is_no_show_today_slug(detail.slug)
        or detail.duration <= 12
        or not detail.video_url
    ):
        return False

    duration = hls_duration_seconds
    if duration is None:
        duration = _hls_duration(detail)
    return duration is not None and duration > 12


def observe_episode_detail(
    detail: DwEpisodeDetailRecord,
    *,
    inspect_static_media: bool = False,
) -> EpisodeRemoteSnapshot:
    """Interpret one Daily Wire response without applying WireLoft state/history.

    Authoritative scheduled/live/delayed states normally do not need HLS probing.
    Quarantine recovery and final metadata settling can opt into media inspection
    when they need to decide whether ownership may safely transfer.
    """
    if is_no_show_today_slug(detail.slug):
        return EpisodeRemoteSnapshot(EpisodePublishStatus.NO_USABLE_MEDIA, False)

    static = _static_status(detail)
    if static is not None and not inspect_static_media:
        return EpisodeRemoteSnapshot(static, False)

    hls_duration_seconds = _hls_duration(detail) if detail.video_url else None
    usable = has_usable_media(detail, hls_duration_seconds=hls_duration_seconds)

    if static is not None:
        return EpisodeRemoteSnapshot(static, usable, hls_duration_seconds)

    if (
        detail.publish_status.upper() == "PUBLISHED"
        and detail.duration < 12
        and hls_duration_seconds is not None
        and hls_duration_seconds > 12
    ):
        return EpisodeRemoteSnapshot(
            EpisodePublishStatus.DW_PROCESSING,
            False,
            hls_duration_seconds,
        )

    if not usable:
        return EpisodeRemoteSnapshot(
            EpisodePublishStatus.NO_USABLE_MEDIA,
            False,
            hls_duration_seconds,
        )

    if not detail.is_downloadable:
        return EpisodeRemoteSnapshot(
            EpisodePublishStatus.PUBLISHED_WITH_COUNTDOWN,
            True,
            hls_duration_seconds,
        )

    return EpisodeRemoteSnapshot(
        EpisodePublishStatus.PUBLISHED_FINAL,
        True,
        hls_duration_seconds,
    )


def resolve_episode_status(
    detail: DwEpisodeDetailRecord,
    *,
    current_status: str | EpisodePublishStatus | None = None,
    now: datetime | None = None,
    snapshot: EpisodeRemoteSnapshot | None = None,
) -> EpisodeRemoteSnapshot:
    """Apply WireLoft's allowed transitions and safety timers to one snapshot."""
    snapshot = snapshot or observe_episode_detail(detail)
    current = _normalize_status(current_status)
    age_minutes = _minutes_since(detail.published_date, now=now)
    timing = get_settings().episode_status_timing

    # Daily Wire directly exposes these states (or, for delayed, the stable slug
    # marker). They are stronger evidence than WireLoft's inferred publication
    # states and may therefore move a previously-final row back to pending.
    if snapshot.status in _AUTHORITATIVE_REMOTE_STATUSES:
        return snapshot

    # No usable media is an explicit ownership boundary. Never allow an age-based
    # publication fallback to overwrite quarantine evidence.
    if snapshot.status is EpisodePublishStatus.NO_USABLE_MEDIA:
        return snapshot

    # The processing signature is useful only for a bounded window after the
    # Daily Wire release timestamp. It becomes quarantine evidence when stale.
    if (
        snapshot.status is EpisodePublishStatus.DW_PROCESSING
        and age_minutes is not None
        and age_minutes >= timing.dw_processing_max_minutes
    ):
        return EpisodeRemoteSnapshot(
            EpisodePublishStatus.NO_USABLE_MEDIA,
            False,
            snapshot.hls_duration_seconds,
        )

    # Once final, weaker inferred snapshots must not cause ordinary regressions.
    # Strong evidence above (authoritative pending state or unusable media) still
    # transfers ownership as intended.
    if (
        current is EpisodePublishStatus.PUBLISHED_FINAL
        and snapshot.status in {
            EpisodePublishStatus.DW_PROCESSING,
            EpisodePublishStatus.PUBLISHED_WITH_COUNTDOWN,
        }
    ):
        return EpisodeRemoteSnapshot(
            EpisodePublishStatus.PUBLISHED_FINAL,
            snapshot.has_usable_media,
            snapshot.hls_duration_seconds,
        )

    # This fallback applies only to a snapshot that currently looks like the
    # published countdown state; scheduled/delayed/live and no-usable states have
    # already returned above and can never be overwritten by episode age.
    if (
        snapshot.status is EpisodePublishStatus.PUBLISHED_WITH_COUNTDOWN
        and age_minutes is not None
        and age_minutes >= timing.published_final_after_minutes
    ):
        return EpisodeRemoteSnapshot(
            EpisodePublishStatus.PUBLISHED_FINAL,
            snapshot.has_usable_media,
            snapshot.hls_duration_seconds,
        )

    return snapshot


def is_published_final(episode: DwEpisodeRecord) -> bool:
    """Back-catalog shortcut for records old enough to be safely considered final."""
    if is_no_show_today_slug(episode.slug) or _static_status(episode) is not None:
        return False
    age_minutes = _minutes_since(episode.published_date)
    return (
        age_minutes is not None
        and age_minutes >= get_settings().episode_status_timing.published_final_after_minutes
    )


def get_publish_status_from_dw_detail(detail: DwEpisodeDetailRecord) -> EpisodePublishStatus:
    """Compatibility wrapper returning only the resolved lifecycle status."""
    return resolve_episode_status(detail).status
