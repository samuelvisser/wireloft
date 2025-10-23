from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models import Show
from backend.types.dailywire_user_info import WlDwMembershipLevel
from backend.types.show_types import EpisodeIdentifier
from dailywire_authorisation import DeviceAuthClient

from wireloft_controller.tasks.helpers.episodes import EpisodeMapList, EpisodeMapTuple, \
    map_all_episodes, get_episode_identifier_map_numbered, get_episode_identifier_map_date_based
from ._helpers import count_total_episodes, index_one_season, get_seasons_sorted_desc


async def run_index_show_worker(s: Session, *, resource_id: Optional[int] = None, show_slug: Optional[str] = None, progress=None) -> None:
    """
    Controller task that implements the multi-step indexing flow:
      1) Count total episodes via API.
      2) Load seasons from DB and sort by index desc.
      3) For each season, fetch episodes in pages of 10 (newest->oldest) and upsert
         into DB with a global descending index across the entire show.
      4) If any step fails within a season, rollback that season and re-raise to
         let the scheduler handle retries.
    """
    print("Starting index_show_worker")

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

        show.set_meta(key="latest_ep_num", value=str(latest_ep_num))
        show.set_meta(key="latest_aux_num", value=str(latest_aux_num))
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
