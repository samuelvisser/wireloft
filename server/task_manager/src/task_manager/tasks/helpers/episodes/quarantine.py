from __future__ import annotations

import re
from datetime import datetime

from sqlalchemy import Integer, cast, func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from backend.db.models import Episode
from backend.db.models.Metadata import Metadata
from backend.types.episode_types import EpisodePublishStatus
from backend.types.show_types import EpisodeIdentifier
from .metadata import ensure_utc


PREVIOUS_IDENTIFIER_META_KEY = "no_usable_media.previous_identifier"
_NOT_USABLE_COUNTER_KEY = "ep_id.latest_not_usable_num"
_NUMBERED_MAIN_RE = re.compile(r"^ep\.(\d+)$")
_SEASONAL_MAIN_RE = re.compile(r"^ep\.S(\d+)E(\d+)$")
_EXTRA_NUMBERED_RE_TEMPLATE = r"^ep-extra\.%s\.(\d+)$"
_EXTRA_SEASONAL_RE_TEMPLATE = r"^ep-extra\.S%02dE%02d\.(\d+)$"


def _utc_timestamp(value: datetime) -> int:
    return int(ensure_utc(value).timestamp())


def _identifiers_for_show(s: Session, episode: Episode) -> list[str]:
    return list(s.scalars(
        select(Episode.episode_identifier).where(
            Episode.show_id == episode.show_id,
            Episode.id != episode.id,
        )
    ))


def _max_matching(identifiers: list[str], pattern: re.Pattern[str], group: int = 1) -> int:
    maximum = 0
    for identifier in identifiers:
        match = pattern.fullmatch(identifier)
        if match:
            maximum = max(maximum, int(match.group(group)))
    return maximum


def _rollback_numbered_head(s: Session, episode: Episode, previous_identifier: str) -> None:
    match = _NUMBERED_MAIN_RE.fullmatch(previous_identifier)
    if not match:
        return
    episode_number = int(match.group(1))
    show = episode.show
    if int(show.get_meta("ep_id.latest_ep_num") or 0) != episode_number:
        return

    identifiers = _identifiers_for_show(s, episode)
    new_head = _max_matching(identifiers, _NUMBERED_MAIN_RE)
    show.set_meta("ep_id.latest_ep_num", str(new_head))
    extra_pattern = re.compile(_EXTRA_NUMBERED_RE_TEMPLATE % new_head) if new_head else re.compile(r"a^")
    show.set_meta("ep_id.latest_ep_extra_num", str(_max_matching(identifiers, extra_pattern)))


def _rollback_seasonal_head(s: Session, episode: Episode, previous_identifier: str) -> None:
    match = _SEASONAL_MAIN_RE.fullmatch(previous_identifier)
    if not match:
        return
    season_number = int(match.group(1))
    episode_number = int(match.group(2))
    if episode.season is None or episode.season.index != season_number:
        return
    show = episode.show
    counter_key = f"ep_id.latest_season_{season_number}_ep"
    if int(show.get_meta(counter_key) or 0) != episode_number:
        return

    identifiers = _identifiers_for_show(s, episode)
    main_pattern = re.compile(rf"^ep\.S{season_number:02d}E(\d+)$")
    new_head = _max_matching(identifiers, main_pattern)
    show.set_meta(counter_key, str(new_head))
    extra_pattern = (
        re.compile(_EXTRA_SEASONAL_RE_TEMPLATE % (season_number, new_head))
        if new_head
        else re.compile(r"a^")
    )
    show.set_meta("ep_id.latest_ep_extra_num", str(_max_matching(identifiers, extra_pattern)))


def _rollback_date_head(s: Session, episode: Episode, previous_identifier: str) -> None:
    if not previous_identifier.startswith("ep.") or episode.published_date is None:
        return
    show = episode.show
    timestamp = _utc_timestamp(episode.published_date)
    if int(show.get_meta("ep_id.latest_ep_date") or 0) != timestamp:
        return
    remaining = list(s.scalars(
        select(Episode.published_date).where(
            Episode.show_id == episode.show_id,
            Episode.id != episode.id,
            Episode.episode_identifier.startswith("ep."),
            Episode.published_date.is_not(None),
        )
    ))
    new_head = max((_utc_timestamp(value) for value in remaining), default=0)
    show.set_meta("ep_id.latest_ep_date", str(new_head))


def rollback_identifier_head(s: Session, episode: Episode, previous_identifier: str) -> None:
    identifier_type = EpisodeIdentifier(episode.show.episode_identifier)
    if identifier_type is EpisodeIdentifier.NUMBERED:
        _rollback_numbered_head(s, episode, previous_identifier)
    elif identifier_type is EpisodeIdentifier.SEASONAL:
        _rollback_seasonal_head(s, episode, previous_identifier)
    elif identifier_type is EpisodeIdentifier.DATE_BASED:
        _rollback_date_head(s, episode, previous_identifier)


def _reserve_not_usable_number(s: Session, episode: Episode) -> int:
    """Atomically reserve the next per-show quarantine identifier number.

    Pending-episode workers run independently and can quarantine several episodes
    from the same show at once. Here, we increment the not usable number counter
    using SQLite's upsert, making sure it is unique.
    """
    # Flush any ORM-side metadata first so the Core upsert sees the transaction's
    # complete state. This remains part of the caller's transaction and rolls back
    # together with the episode transition if anything later fails.
    s.flush()

    statement = (
        sqlite_insert(Metadata)
        .values(
            parent_table="shows",
            parent_id=episode.show_id,
            key=_NOT_USABLE_COUNTER_KEY,
            value="1",
        )
        .on_conflict_do_update(
            index_elements=[Metadata.parent_table, Metadata.parent_id, Metadata.key],
            set_={
                "value": cast(Metadata.value, Integer) + 1,
                "updated_at": func.now(),
            },
        )
        .returning(Metadata.value)
    )
    current = int(s.execute(statement).scalar_one())

    # The Show relationship may have been eagerly loaded before another worker
    # advanced the counter. Force the next metadata access in this transaction to
    # see the value reserved by the database rather than that stale collection.
    s.expire(episode.show, ["meta_items"])
    return current


def quarantine_episode_identifier(s: Session, episode: Episode) -> bool:
    """Move an episode out of the canonical identifier namespace without file side effects."""
    if episode.episode_identifier.startswith("not-usable."):
        return False

    previous_identifier = episode.episode_identifier
    episode.set_meta(PREVIOUS_IDENTIFIER_META_KEY, previous_identifier)
    current = _reserve_not_usable_number(s, episode)
    episode.episode_identifier = f"not-usable.{current}"
    s.flush()
    rollback_identifier_head(s, episode, previous_identifier)
    s.flush()
    return True


def vacated_canonical_identifiers_for_show(s: Session, show_id: int) -> set[str]:
    """Return currently-free canonical identifiers reserved by quarantined rows.

    This allows a replacement Daily Wire row to reclaim a logical main identifier
    even when a newer episode has already advanced the normal monotonic allocator.
    If another local row already owns the identifier, it is no longer considered
    vacated and is never offered for reclamation.
    """
    episodes = list(s.scalars(select(Episode).where(Episode.show_id == show_id)))
    occupied = {episode.episode_identifier for episode in episodes}
    vacated: set[str] = set()
    for episode in episodes:
        if episode.publish_status != EpisodePublishStatus.NO_USABLE_MEDIA.value:
            continue
        previous = episode.get_meta(PREVIOUS_IDENTIFIER_META_KEY)
        if previous and previous.startswith("ep.") and previous not in occupied:
            vacated.add(previous)
    return vacated


def _advance_head_for_identifier(s: Session, episode: Episode, identifier: str) -> None:
    show = episode.show
    identifiers = _identifiers_for_show(s, episode)
    identifier_type = EpisodeIdentifier(show.episode_identifier)

    if identifier_type is EpisodeIdentifier.NUMBERED:
        match = _NUMBERED_MAIN_RE.fullmatch(identifier)
        if match:
            number = int(match.group(1))
            show.set_meta("ep_id.latest_ep_num", str(max(int(show.get_meta("ep_id.latest_ep_num") or 0), number)))
            extra_pattern = re.compile(_EXTRA_NUMBERED_RE_TEMPLATE % number)
            show.set_meta("ep_id.latest_ep_extra_num", str(_max_matching(identifiers, extra_pattern)))
    elif identifier_type is EpisodeIdentifier.SEASONAL:
        match = _SEASONAL_MAIN_RE.fullmatch(identifier)
        if match:
            season_number = int(match.group(1))
            number = int(match.group(2))
            key = f"ep_id.latest_season_{season_number}_ep"
            show.set_meta(key, str(max(int(show.get_meta(key) or 0), number)))
            extra_pattern = re.compile(_EXTRA_SEASONAL_RE_TEMPLATE % (season_number, number))
            show.set_meta("ep_id.latest_ep_extra_num", str(_max_matching(identifiers, extra_pattern)))
    elif identifier_type is EpisodeIdentifier.DATE_BASED and episode.published_date is not None:
        timestamp = _utc_timestamp(episode.published_date)
        show.set_meta("ep_id.latest_ep_date", str(max(int(show.get_meta("ep_id.latest_ep_date") or 0), timestamp)))


def restore_quarantined_identifier(s: Session, episode: Episode) -> bool:
    """Restore the identifier displaced by quarantine when it is still available."""
    previous_identifier = episode.get_meta(PREVIOUS_IDENTIFIER_META_KEY)
    if not previous_identifier:
        return True

    collision = s.scalar(
        select(Episode.id).where(
            Episode.show_id == episode.show_id,
            Episode.id != episode.id,
            Episode.episode_identifier == previous_identifier,
        ).limit(1)
    )
    if collision is not None:
        return False

    episode.episode_identifier = previous_identifier
    _advance_head_for_identifier(s, episode, previous_identifier)
    for item in list(episode.meta_items):
        if item.key == PREVIOUS_IDENTIFIER_META_KEY:
            episode.meta_items.remove(item)
    s.flush()
    return True
