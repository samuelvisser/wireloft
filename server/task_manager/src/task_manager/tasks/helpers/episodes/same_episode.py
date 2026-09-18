from __future__ import annotations

from typing import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models import Episode, Season, Show
from backend.types.download_profile_types import EpIdType
from backend.types.episode_types import EpisodePublishStatus
from backend.types.show_types import EpisodeIdentifier
from backend.utils.episode import EpisodeIdentifierInfo
from dailywire_api.records import DwEpisodeRecord
from .metadata import ensure_utc


PENDING_EPISODE_STATUSES = {
    EpisodePublishStatus.SCHEDULED.value,
    EpisodePublishStatus.DELAYED.value,
    EpisodePublishStatus.LIVE.value,
    EpisodePublishStatus.DW_PROCESSING.value,
    EpisodePublishStatus.PUBLISHED_WITH_COUNTDOWN.value,
}


def pending_episodes_for_show(s: Session, show_id: int) -> list[Episode]:
    return list(
        s.scalars(
            select(Episode).where(
                Episode.show_id == show_id,
                Episode.publish_status.in_(PENDING_EPISODE_STATUSES),
            )
        )
    )


def _same_publication_time(local: Episode, remote: DwEpisodeRecord) -> bool:
    if local.published_date is None or remote.published_date is None:
        return False
    left = ensure_utc(local.published_date)
    right = ensure_utc(remote.published_date)
    return abs((left - right).total_seconds()) <= 60


def _matches_source_number(
    info: EpisodeIdentifierInfo,
    remote: DwEpisodeRecord,
) -> bool:
    if remote.ep_number is None or info.episode_number is None:
        return False
    if int(info.episode_number) != remote.ep_number:
        return False
    if info.type == EpIdType.EP:
        return remote.ep_segment == 0
    if info.type == EpIdType.EP_EXTRA and info.sub_episode_number is not None:
        return int(info.sub_episode_number) == remote.ep_segment
    return False


def _matches_identity(
    show: Show,
    local: Episode,
    season: Season,
    remote: DwEpisodeRecord,
) -> bool:
    identifier_type = EpisodeIdentifier(show.episode_identifier)
    try:
        info = EpisodeIdentifierInfo.from_identifier(local.episode_identifier)
    except ValueError:
        return _same_publication_time(local, remote)

    if identifier_type is EpisodeIdentifier.NUMBERED:
        if info.type in {EpIdType.EP, EpIdType.EP_EXTRA}:
            return _matches_source_number(info, remote)
        return _same_publication_time(local, remote)

    if identifier_type is EpisodeIdentifier.SEASONAL:
        if (
            info.type in {EpIdType.EP, EpIdType.EP_EXTRA}
            and info.season_number == season.season_number
        ):
            return _matches_source_number(info, remote)
        return _same_publication_time(local, remote)

    return _same_publication_time(local, remote)


def reconcile_single_pending_episode_slug(
    s: Session,
    *,
    show: Show,
    season: Season,
    remote_records: Sequence[DwEpisodeRecord],
) -> Episode | None:
    """Adopt a changed Daily Wire slug onto the sole pending local episode."""
    pending = pending_episodes_for_show(s, show.id)
    if len(pending) != 1:
        return None
    local = pending[0]
    if local.season_id != season.id:
        return None
    if any(record.slug == local.slug for record in remote_records):
        return None

    known_slugs = set(
        s.scalars(select(Episode.slug).where(Episode.show_id == show.id))
    )
    matches = [
        record
        for record in remote_records
        if record.slug not in known_slugs
        and _matches_identity(show, local, season, record)
    ]
    if len(matches) != 1:
        return None

    local.slug = matches[0].slug
    s.flush()
    return local
