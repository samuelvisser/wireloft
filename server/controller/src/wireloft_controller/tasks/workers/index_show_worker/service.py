from __future__ import annotations

from time import sleep
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models import Show
from backend.types.dailywire_user_info import WlDwMembershipLevel
from backend.types.show_types import EpisodeIdentifier
from dailywire_authorisation import DeviceAuthClient
from backend.api.endpoints.dailywire.episodes.service import get_episodes_from_season_list

from wireloft_controller.tasks.helpers.episodes import EpisodeMapList, EpisodeMapTuple, \
    get_episode_identifier_map_numbered, get_episode_identifier_map_date_based
from ._helpers import count_total_episodes, index_one_season, get_seasons_sorted_desc
from ...helpers.progress import update_progress


async def run_index_show_worker(s: Session, *, resource_id: Optional[int] = None, show_slug: Optional[str] = None, progress=None) -> None:
    """
    Task to index every published episode currently available for a show.

    Typically, run only right after a new show is added to WireLoft
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
    seasons = get_seasons_sorted_desc(s, show_slug)
    if not seasons:
        update_progress(progress, 100, "No seasons in database")
        return

    # Map all episodes with progress guessing (95% of progress reserved for scanning)
    ep_map: EpisodeMapList = {}
    season_count = len(seasons)

    update_progress(progress, 1, f"Scanning episodes for '{show_slug}'...")

    # For the first season assume 40 episodes; for each next season assume it has as many as the previous had
    actual_counts: list[int] = []
    estimated_counts: list[int] = [40] * season_count  # initial guess for first season; will be overwritten as we discover

    for i, season in enumerate(seasons):
        # Ensure our estimate for remaining episodes reflects the last known actual (or initial 40 for the very first)
        prev_est = actual_counts[i - 1] if i > 0 else 40
        for j in range(i, season_count):
            if j >= len(actual_counts):
                estimated_counts[j] = prev_est

        # Fetch episodes for this season
        eps = get_episodes_from_season_list(show.slug, season.dw_id,
                                            membership_plan=membership_level,
                                            access_token=access_token)
        ep_map[season.id] = eps
        count = len(eps)
        # Record actual and update future estimates
        if i < len(estimated_counts):
            estimated_counts[i] = count
        actual_counts.append(count)
        for j in range(i + 1, season_count):
            if j >= len(actual_counts):
                estimated_counts[j] = count

        # Compute guessed progress for mapping (0..95)
        est_total = max(1, sum(estimated_counts))
        done = sum(actual_counts)
        pct_scan = int((done / est_total) * 95)
        pct_scan = max(1, min(95, pct_scan))

        update_progress(progress, pct_scan, f"Scanning seasons: mapped {done} episodes (season {season.index}: {season.name})")

    # Add identifiers
    ep_id_map: EpisodeMapTuple
    if show.episode_identifier == EpisodeIdentifier.DATE_BASED.value:
        ep_id_map = get_episode_identifier_map_date_based(ep_map, throw_if_truncated=True)
    else:
        latest_ep_num, latest_aux_num, ep_id_map = get_episode_identifier_map_numbered(ep_map, throw_if_truncated=True)
        show.set_meta(key="latest_ep_num", value=str(latest_ep_num))
        show.set_meta(key="latest_aux_num", value=str(latest_aux_num))
        s.flush()

    total = count_total_episodes(ep_map)
    update_progress(progress, 95, f"Found {total} episodes in '{show_slug}'")

    # Iterate seasons and index episodes
    current_index = total
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
            print(f"Exception: {e}")
            raise e

        # Update progress roughly based on completed seasons
        processed = total - current_index
        frac = max(0.0, min(1.0, processed / total))  if total > 0 else 1.0
        scaled_pct = 95 + min(4, int(frac * 5))
        update_progress(progress, scaled_pct, f"Indexed {processed}/{total} episodes (season {season.index}: {season.name})")

    update_progress(progress, 100, f"Indexed all episodes: done")