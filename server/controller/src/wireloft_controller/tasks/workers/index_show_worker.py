from __future__ import annotations

from typing import Optional, Sequence, Dict, Tuple, Any

from sqlalchemy import select, insert, case, or_

from backend.api.helpers import update_database_fields, create_database_fields
from backend.db.core import get_session
from backend.db.models import Show, Season, Metadata
from backend.db.models.media_item import Episode
from backend.types.dailywire_user_info import WlDwMembershipLevel
from backend.types.show_types import EpisodeIdentifier
from backend.utils.helpers import generate_uuid
from backend.types.media_types import MediaType

from dailywire_api.dw_api.client import MiddlewareClient
from dailywire_api.records import EpisodeRecord
from dailywire_api.records.EpisodeDetailRecord import EpisodeDetailRecord
from dailywire_authorisation import DeviceAuthClient

from ...registry import task
from ...util.episodes import is_published_final, EpisodeMapList, map_all_episodes, EpisodeMapTuple, \
    get_episode_identifier_map_numbered, get_episode_identifier_map_date_based


# ---------------- helpers ----------------

def count_total_episodes(episodes_map: Dict[int, list[Any]]) -> int:
    """
    Count all episodes by counting the items in the map.
    """
    count = 0
    for _, eps in episodes_map.items():
        count += len(eps)

    return count


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


def upsert_episode(
        s, *, show: Show, season: Season, ep: EpisodeDetailRecord, index_value: int, ep_id: str
) -> Episode:
    """Create or update a single Episode row for the given EpisodeRecord."""

    # Check if the episode already exists in DB
    episode: Optional[Episode] = (
        s.query(Episode)
        .filter(Episode.show_id == show.id, Episode.dw_id == ep.dw_id)
        .one_or_none()
    )

    if episode is None:
        # Create new (only pass fields that exist on the SQLAlchemy model)
        episode = create_database_fields(Episode, data={
            **ep.model_dump(mode="python", by_alias=False),
            **{
                "uuid": generate_uuid(),
                "type": MediaType.EPISODE.value,
                "show_id": show.id,
                "season_id": season.id,
                "index": index_value,
                "episode_identifier": ep_id,
            }
        })
        s.add(episode)
    else:
        # Update existing in place and reindex
        update_database_fields(episode, ep, ignore_extra_fields=True)
        episode.season_id = season.id
        episode.index = index_value
        episode.episode_identifier = ep_id

    s.flush()
    return episode


def index_one_season(s, *,
                     show: Show,
                     season: Season,
                     episodes: list[Tuple[str, EpisodeRecord]],
                     start_index: int,
                     ) -> int:
    """
    Index a single season within its own transaction scope. On error, roll back
    all changes for the season and re-raise.

    Returns the next index to use for subsequent (older) episodes.
    """
    client = MiddlewareClient()
    current_index = start_index

    try:
        for ep_id, ep in episodes:
            if not is_published_final(ep):
                current_index -= 1
                continue
            
            epDetails = client.get_episode_details(ep.slug, require_member_exclusive=ep.is_member_exclusive)
            upsert_episode(s, show=show, season=season, ep=epDetails, index_value=current_index, ep_id=ep_id)
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
    # TODO: currently this task blocks any database writes as long as it runs. This is not ideal.

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

        # Get the desired membership level and access token
        membership_level: str = show.membership_level
        access_token: Optional[str] = None
        if membership_level is not WlDwMembershipLevel.FREE.value:
            tokens = DeviceAuthClient().get_token()
            if not tokens:
                if membership_level is not WlDwMembershipLevel.WL_ANY.value:
                    raise ValueError("No valid access token in token store")
                membership_level = WlDwMembershipLevel.FREE.value
            else:
                access_token = tokens.access_token

        # Get seasons sorted desc
        seasons = get_seasons_sorted_desc(show_slug)
        if not seasons:
            if progress:
                progress.set(100, "No seasons in database")
            return

        # Get a map of all episodes and add their identifiers
        ep_map: EpisodeMapList = map_all_episodes(show.slug, seasons, membership_level=membership_level, access_token=access_token)
        ep_id_map: EpisodeMapTuple
        if show.episode_identifier == EpisodeIdentifier.DATE_BASED.value:
            ep_id_map = get_episode_identifier_map_date_based(ep_map, throw_if_truncated=True)
        else:
            latest_ep_num, latest_aux_num, ep_id_map = get_episode_identifier_map_numbered(ep_map, throw_if_truncated=True)

            show.meta_items.append(Metadata(key="latest_ep_num", value=str(latest_ep_num)))
            show.meta_items.append(Metadata(key="latest_aux_num", value=str(latest_aux_num)))
            s.flush()

        total = count_total_episodes(ep_map)
        if progress:
            progress.set(5, f"Found {total} episodes in '{show_slug}'")

        # Iterate seasons and index episodes
        current_index = total
        processed = 0
        for i, season in enumerate(seasons):
            # index this season in its own transaction scope
            try:
                current_index = index_one_season(s,
                                                 show=show,
                                                 season=season,
                                                 episodes=ep_id_map[season.id],
                                                 start_index=current_index)
            except Exception as e:
                # rollback of the season has already occurred inside index_one_season
                # Re-raise to allow scheduler to retry; caller expects retry to be scheduled
                raise e

            # Update progress roughly based on completed seasons
            processed = total - current_index
            pct = int((processed / total) * 100) if total > 0 else 100
            if progress:
                progress.set(min(99, max(10, pct)), f"Indexed {processed}/{total} episodes (season {season.index}: {season.name})")

        if progress:
            progress.set(100, f"Indexed {processed}/{total} episodes for '{show_slug}'")
    finally:
        s.close()
