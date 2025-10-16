from __future__ import annotations

from typing import Iterable, Optional, Sequence

from sqlalchemy import select, insert, case, or_

from backend.api.helpers import update_database_fields
from backend.db.core import get_session
from backend.db.models import Show, Season
from backend.db.models.media_item import Episode
from backend.utils.helpers import generate_uuid
from backend.types.media_types import MediaType

from backend.api.endpoints.dailywire.episodes.service import get_episodes_from_show_list

from dailywire_api.dw_api.client import MiddlewareClient, ByShowSeason, ByNextPage
from dailywire_api.records import EpisodeRecord

from ...registry import task


# ---------------- helpers ----------------

def count_total_episodes(show_slug: str) -> int:
    """
    Count total episodes for a show by fetching all episodes once.
    Note: We only keep the length as required.
    """
    all_eps = get_episodes_from_show_list(show_slug)
    return len(all_eps)


def get_seasons_sorted_desc(show_slug: str) -> Sequence[Season]:
    """Get seasons for a show from the DB sorted by Season.index descending."""
    s = get_session()
    try:
        return s.scalars(
            select(Season)
            .filter(Season.show.has(slug=show_slug))
            .order_by(Season.index.desc())
        ).all()
    finally:
        s.close()


def iter_paginated_episodes_for_season(
    client: MiddlewareClient,
    *,
    show_slug: str,
    season_dw_id: str,
    page_size: int = 10,
) -> Iterable[list[EpisodeRecord]]:
    """
    Yield lists of up to `page_size` EpisodeRecord items for a season, newest to oldest.
    """
    items, next_page_url, has_next = client.get_episodes_paginated(show_slug, ByShowSeason(
        season_id=season_dw_id,
        page_size=page_size
    ))
    if items:
        yield items
    while has_next and next_page_url:
        items, next_page_url, has_next = client.get_episodes_paginated(show_slug, ByNextPage(
            next_page_url=next_page_url
        ))
        if items:
            yield items


def upsert_episode(
    s, *, show: Show, season: Season, ep: EpisodeRecord, index_value: int
) -> Episode:
    """Create or update a single Episode row for the given EpisodeRecord."""

    # Check if the episode already exists in DB
    episode: Optional[Episode] = (
        s.query(Episode)
        .filter(Episode.show_id == show.id, Episode.dw_id == ep.id)
        .one_or_none()
    )

    if episode is None:
        # Create new
        episode = Episode(**{
            **ep.model_dump(mode="python", by_alias=False),
            **{
                "uuid": generate_uuid(),
                "type": MediaType.EPISODE.value,
                "show_id": show.id,
                "season_id": season.id,
                "index": index_value,
                "dw_id": ep.id,
                "publish_status": ep.status,
                "duration": int(ep.duration or 0),
                "published_date": ep.published_at,
            }
        })
        s.add(episode)
    else:
        # Update existing in place and reindex
        update_database_fields(episode, ep, ignore_extra_fields=True)
        episode.season_id = season.id
        episode.index = index_value
        episode.dw_id = ep.id
        episode.duration = int(ep.duration or 0)
        episode.publish_status = ep.status
        episode.published_date = ep.published_at

    s.flush()
    return episode


def index_one_season(
    *,
    s,
    show: Show,
    season: Season,
    start_index: int,
    page_size: int = 10,
) -> int:
    """
    Index a single season within its own transaction scope. On error, roll back
    all changes for the season and re-raise.

    Returns the next index to use for subsequent (older) episodes.
    """
    client = MiddlewareClient()
    current_index = start_index

    try:
        # Process in pages newest->oldest
        for batch in iter_paginated_episodes_for_season(client, show_slug=show.slug, season_dw_id=season.dw_id, page_size=page_size):
            for ep in batch:
                upsert_episode(s, show=show, season=season, ep=ep, index_value=current_index)
                current_index -= 1
        # Commit this season
        s.commit()
        return current_index
    except Exception:
        s.rollback()
        raise


# ---------------- task entrypoint ----------------

@task(
    key="index_show_worker",
    title="Index show episodes",
    description="Counts and indexes all episodes for a show, assigning descending episode indices (newest..oldest) and rolling back the current season on failure.",
    allowed_resource_types=("show",),
    default_max_retries=5,
    tracks_progress=True,
)
async def index_show_worker(*, resource_id: Optional[int] = None, show_slug: Optional[str] = None, progress=None) -> None:
    """
    Controller task that implements the multi-step indexing flow:
      1) Count total episodes via API.
      2) Load seasons from DB and sort by index desc.
      3) For each season, fetch episodes in pages of 10 (newest->oldest) and upsert
         into DB with a global descending index across the entire show.
      4) If any step fails within a season, rollback that season and re-raise to
         let the scheduler handle retries.
    """
    s = get_session()
    try:
        # Resolve the Show record by slug or id
        show: Optional[Show] = None
        if show_slug:
            show = s.execute(select(Show).where(Show.slug == show_slug)).scalar_one_or_none()
        elif resource_id is not None:
            show = s.get(Show, resource_id)
        if show is None:
            raise ValueError("Show not found; provide a valid show_slug or resource_id")
        # Ensure we have slug for API
        show_slug = show.slug

        # Step 1: count total episodes
        total = count_total_episodes(show_slug)
        if progress:
            progress.set(5, f"Found {total} episodes in '{show_slug}'")

        # Step 2: seasons sorted desc
        seasons = get_seasons_sorted_desc(show_slug)
        if not seasons:
            if progress:
                progress.set(100, "No seasons in database")
            return

        # Step 3: iterate seasons and index episodes
        current_index = total
        processed = 0
        for i, season in enumerate(seasons):
            # index this season in its own transaction scope
            try:
                current_index = index_one_season(s=s, show=show, season=season, start_index=current_index, page_size=10)
            except Exception as e:
                # rollback of the season has already occurred inside index_one_season
                # Re-raise to allow scheduler to retry; caller expects retry to be scheduled
                raise e

            # Update progress roughly based on completed seasons
            processed = total - current_index
            pct = int((processed / total) * 100) if total > 0 else 100
            if progress:
                progress.set(min(99, max(10, pct)), f"Indexed {processed}/{total} episodes (season {season.index})")

        if progress:
            progress.set(100, f"Indexed {processed}/{total} episodes for '{show_slug}'")
    finally:
        s.close()
