from __future__ import annotations

from datetime import datetime

from sqlalchemy import Integer, cast, func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from backend.db.models import Episode
from backend.db.models.Metadata import Metadata
from backend.types.episode_types import EpisodePublishStatus
from backend.types.show_types import EpisodeIdentifier
from backend.utils.episode import EpisodeIdentifierInfo
from .metadata import ensure_utc


PREVIOUS_IDENTIFIER_META_KEY = "no_usable_media.previous_identifier"
_NOT_USABLE_COUNTER_KEY = "ep_id.latest_not_usable_num"


def _utc_timestamp(value: datetime) -> int:
    return int(ensure_utc(value).timestamp())


def _rollback_date_head(s: Session, episode: Episode, previous_identifier: str) -> None:
    if not previous_identifier.startswith("ep.") or episode.published_date is None:
        return
    show = episode.show
    timestamp = _utc_timestamp(episode.published_date)
    if int(show.get_meta("ep_id.latest_ep_date") or 0) != timestamp:
        return
    remaining = list(
        s.scalars(
            select(Episode.published_date).where(
                Episode.show_id == episode.show_id,
                Episode.id != episode.id,
                Episode.episode_identifier.startswith("ep."),
                Episode.published_date.is_not(None),
            )
        )
    )
    new_head = max((_utc_timestamp(value) for value in remaining), default=0)
    show.set_meta("ep_id.latest_ep_date", str(new_head))


def rollback_identifier_head(s: Session, episode: Episode, previous_identifier: str) -> None:
    """Roll back only state that still participates in canonical allocation."""
    if EpisodeIdentifier(episode.show.episode_identifier) is EpisodeIdentifier.DATE_BASED:
        _rollback_date_head(s, episode, previous_identifier)


def _reserve_not_usable_number(s: Session, episode: Episode) -> int:
    """Atomically reserve the next per-show quarantine identifier number."""
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
    s.expire(episode.show, ["meta_items"])
    return current


def quarantine_episode_identifier(s: Session, episode: Episode) -> bool:
    """Move an episode out of the canonical identifier namespace."""
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
    """Return currently free source-backed identifiers displaced by quarantine."""
    episodes = list(s.scalars(select(Episode).where(Episode.show_id == show_id)))
    occupied = {episode.episode_identifier for episode in episodes}
    show_identifier_type = None
    if episodes:
        show_identifier_type = EpisodeIdentifier(episodes[0].show.episode_identifier)
    vacated: set[str] = set()
    for episode in episodes:
        if episode.publish_status != EpisodePublishStatus.NO_USABLE_MEDIA.value:
            continue
        previous = episode.get_meta(PREVIOUS_IDENTIFIER_META_KEY)
        if not previous or previous in occupied:
            continue
        try:
            info = EpisodeIdentifierInfo.from_identifier(previous)
        except ValueError:
            continue
        if info.source_slot is not None or (
            show_identifier_type is EpisodeIdentifier.DATE_BASED
            and info.type == "ep"
        ):
            vacated.add(previous)
    return vacated


def _advance_date_head_for_identifier(episode: Episode, identifier: str) -> None:
    if (
        EpisodeIdentifier(episode.show.episode_identifier) is not EpisodeIdentifier.DATE_BASED
        or episode.published_date is None
    ):
        return
    try:
        info = EpisodeIdentifierInfo.from_identifier(identifier)
    except ValueError:
        return
    if info.type != "ep":
        return
    timestamp = _utc_timestamp(episode.published_date)
    episode.show.set_meta(
        "ep_id.latest_ep_date",
        str(max(int(episode.show.get_meta("ep_id.latest_ep_date") or 0), timestamp)),
    )


def restore_quarantined_identifier(s: Session, episode: Episode) -> bool:
    """Restore the identifier displaced by quarantine when it is still available."""
    previous_identifier = episode.get_meta(PREVIOUS_IDENTIFIER_META_KEY)
    if not previous_identifier:
        return True

    collision = s.scalar(
        select(Episode.id)
        .where(
            Episode.show_id == episode.show_id,
            Episode.id != episode.id,
            Episode.episode_identifier == previous_identifier,
        )
        .limit(1)
    )
    if collision is not None:
        return False

    episode.episode_identifier = previous_identifier
    _advance_date_head_for_identifier(episode, previous_identifier)
    for item in list(episode.meta_items):
        if item.key == PREVIOUS_IDENTIFIER_META_KEY:
            episode.meta_items.remove(item)
    s.flush()
    return True
