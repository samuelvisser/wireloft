from __future__ import annotations

import re
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models import Episode, Season, Show
from backend.types.episode_types import EpisodePublishStatus
from backend.types.show_types import EpisodeIdentifier
from dailywire_api.records import DwEpisodeRecord
from .metadata import ensure_utc


PENDING_EPISODE_STATUSES = {
    EpisodePublishStatus.SCHEDULED.value,
    EpisodePublishStatus.DELAYED.value,
    EpisodePublishStatus.LIVE.value,
    EpisodePublishStatus.DW_PROCESSING.value,
    EpisodePublishStatus.PUBLISHED_WITH_COUNTDOWN.value,
}
_NUMBERED_RE = re.compile(r"^ep\.(\d+)$")
_SEASONAL_RE = re.compile(r"^ep\.S(\d+)E(\d+)$")


def pending_episodes_for_show(s: Session, show_id: int) -> list[Episode]:
    return list(s.scalars(
        select(Episode).where(
            Episode.show_id == show_id,
            Episode.publish_status.in_(PENDING_EPISODE_STATUSES),
        )
    ))


def _same_publication_time(local: Episode, remote: DwEpisodeRecord) -> bool:
    if local.published_date is None or remote.published_date is None:
        return False
    left = ensure_utc(local.published_date)
    right = ensure_utc(remote.published_date)
    return abs((left - right).total_seconds()) <= 60


def _matches_identity(show: Show, local: Episode, season: Season, remote: DwEpisodeRecord) -> bool:
    identifier_type = EpisodeIdentifier(show.episode_identifier)
    if identifier_type is EpisodeIdentifier.NUMBERED:
        match = _NUMBERED_RE.fullmatch(local.episode_identifier)
        if match:
            return bool(
                remote.ep_number is not None
                and int(match.group(1)) == remote.ep_number
                and remote.ep_segment == 0
            )
        # Extras/auxiliary pending rows do not have a stable canonical main
        # identifier. Publication time is the conservative secondary identity.
        return _same_publication_time(local, remote)
    if identifier_type is EpisodeIdentifier.SEASONAL:
        match = _SEASONAL_RE.fullmatch(local.episode_identifier)
        if match:
            return bool(
                int(match.group(1)) == season.index
                and remote.ep_number is not None
                and int(match.group(2)) == remote.ep_number
                and remote.ep_segment == 0
            )
        return _same_publication_time(local, remote)
    return _same_publication_time(local, remote)


def reconcile_single_pending_episode_slug(
    s: Session,
    *,
    show: Show,
    season: Season,
    remote_records: Sequence[DwEpisodeRecord],
) -> Episode | None:
    """Adopt a changed Daily Wire slug onto the sole pending local episode.

    A slug is mutable before publication, so this deliberately relies on WireLoft's
    stronger local identity (canonical episode number/season or publication time).
    Ambiguous candidates are never guessed.
    """
    pending = pending_episodes_for_show(s, show.id)
    if len(pending) != 1:
        return None
    local = pending[0]
    if local.season_id != season.id:
        return None
    if any(record.slug == local.slug for record in remote_records):
        return None

    known_slugs = set(s.scalars(select(Episode.slug).where(Episode.show_id == show.id)))
    matches = [
        record
        for record in remote_records
        if record.slug not in known_slugs and _matches_identity(show, local, season, record)
    ]
    if len(matches) != 1:
        return None

    local.slug = matches[0].slug
    s.flush()
    return local
