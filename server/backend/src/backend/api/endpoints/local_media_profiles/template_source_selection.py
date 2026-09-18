from __future__ import annotations

from collections.abc import Mapping, Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session, contains_eager, joinedload

from backend.db.models import Episode, Show
from backend.types.local_media_profile_types import ShowLocalMediaProfileScope
from backend.types.show_types import ShowType


SHOW_TEMPLATE_SOURCE_LIMIT = 20


def _episode_ordering():
    return (
        Episode.published_date.desc().nullslast(),
        Episode.created_at.desc(),
        Episode.id.desc(),
    )


def _latest_show_ids(
    s: Session,
    show_type: ShowType,
    limit: int,
) -> list[int]:
    """Return show IDs ordered by their most recent episode."""
    ranked_episodes = (
        select(
            Episode.id.label("episode_id"),
            Episode.show_id.label("show_id"),
            Episode.published_date.label("published_date"),
            Episode.created_at.label("created_at"),
            func.row_number().over(
                partition_by=Episode.show_id,
                order_by=list(_episode_ordering()),
            ).label("show_episode_rank"),
        )
        .join(Show, Show.id == Episode.show_id)
        .where(Show.type == show_type.value)
        .subquery()
    )

    return list(s.scalars(
        select(ranked_episodes.c.show_id)
        .where(ranked_episodes.c.show_episode_rank == 1)
        .order_by(
            ranked_episodes.c.published_date.desc().nullslast(),
            ranked_episodes.c.created_at.desc(),
            ranked_episodes.c.episode_id.desc(),
        )
        .limit(limit)
    ).all())


def _balanced_episode_ids(
    show_ids: Sequence[int],
    episode_ids_by_show: Mapping[int, Sequence[int]],
    limit: int,
) -> list[int]:
    """Fill the quota in rounds so every show gets another episode before any show gets two more."""
    selected: list[int] = []
    episode_index = 0
    while len(selected) < limit:
        added_episode = False
        for show_id in show_ids:
            show_episode_ids = episode_ids_by_show.get(show_id, ())
            if episode_index >= len(show_episode_ids):
                continue
            selected.append(show_episode_ids[episode_index])
            added_episode = True
            if len(selected) == limit:
                return selected
        if not added_episode:
            break
        episode_index += 1

    return selected


def _episode_ids_for_show_type(
    s: Session,
    show_type: ShowType,
    limit: int,
) -> list[int]:
    """Spread a source quota as evenly as possible over recent shows."""
    if limit <= 0:
        return []

    show_ids = _latest_show_ids(s, show_type, limit)
    if not show_ids:
        return []

    ranked_episodes = (
        select(
            Episode.id.label("episode_id"),
            Episode.show_id.label("show_id"),
            Episode.published_date.label("published_date"),
            Episode.created_at.label("created_at"),
            func.row_number().over(
                partition_by=Episode.show_id,
                order_by=list(_episode_ordering()),
            ).label("show_episode_rank"),
        )
        .where(Episode.show_id.in_(show_ids))
        .subquery()
    )
    rows = s.execute(
        select(
            ranked_episodes.c.episode_id,
            ranked_episodes.c.show_id,
        )
        .where(ranked_episodes.c.show_episode_rank <= limit)
        .order_by(
            ranked_episodes.c.published_date.desc().nullslast(),
            ranked_episodes.c.created_at.desc(),
            ranked_episodes.c.episode_id.desc(),
        )
    ).all()

    episode_ids_by_show = {show_id: [] for show_id in show_ids}
    for episode_id, show_id in rows:
        episode_ids_by_show[show_id].append(episode_id)

    return _balanced_episode_ids(show_ids, episode_ids_by_show, limit)


def select_show_template_source_episodes(
    s: Session,
    show_scope: ShowLocalMediaProfileScope,
    *,
    limit: int = SHOW_TEMPLATE_SOURCE_LIMIT,
) -> list[Episode]:
    """Choose recent show examples while maximizing show and scope diversity."""
    if limit <= 0:
        return []

    if show_scope == ShowLocalMediaProfileScope.BOTH:
        podcast_limit = limit // 2
        series_limit = limit - podcast_limit
        episode_ids = [
            *_episode_ids_for_show_type(s, ShowType.PODCAST, podcast_limit),
            *_episode_ids_for_show_type(s, ShowType.SERIES, series_limit),
        ]
    elif show_scope == ShowLocalMediaProfileScope.PODCAST:
        episode_ids = _episode_ids_for_show_type(s, ShowType.PODCAST, limit)
    elif show_scope == ShowLocalMediaProfileScope.SERIES:
        episode_ids = _episode_ids_for_show_type(s, ShowType.SERIES, limit)
    else:
        raise ValueError(f"Unsupported show template source scope: {show_scope}")

    if not episode_ids:
        return []

    return list(s.scalars(
        select(Episode)
        .join(Episode.show)
        .options(contains_eager(Episode.show), joinedload(Episode.season))
        .where(Episode.id.in_(episode_ids))
        .order_by(
            func.lower(Show.title),
            Show.id,
            Episode.index,
            Episode.id,
        )
    ).all())
