from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models import Show
from backend.types.dailywire_user_info import WlDwMembershipLevel
from dailywire_api.dw_api.client import MiddlewareClient
from dailywire_authorisation import DeviceAuthClient

from ...helpers.episodes.mapper import get_dw_episodes_by_seasons, count_total_episodes
from ...helpers.episodes.save import save_dw_episodes_per_season_desc
from ...helpers.progress import update_progress, ProgressBounds
from ...types.general import RecordOrder


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
    membership_plan: str = show.membership_level
    access_token: Optional[str] = None
    if membership_plan is not WlDwMembershipLevel.FREE.value:
        tokens = DeviceAuthClient().get_token()
        if not tokens:
            if membership_plan is not WlDwMembershipLevel.WL_ANY.value:
                raise ValueError("No valid access token in token store")
            membership_plan = WlDwMembershipLevel.FREE.value
        else:
            access_token = tokens.access_token

    # Get seasons
    seasons = show.seasons
    if not seasons:
        update_progress(progress, 100, "No seasons in database")
        return

    # Progress bounds
    x = max(1, min(int(len(seasons)), 5))
    upper = int(65 + (x - 1) * (95 - 65) / (5 - 1))

    # Map all episodes
    client = MiddlewareClient(access_token=access_token)
    ep_map_desc, identifier_max_values = get_dw_episodes_by_seasons(client,
                                                                    show=show,
                                                                    membership_plan=membership_plan,
                                                                    seasons=seasons,
                                                                    progress=progress,
                                                                    progress_bounds=ProgressBounds(1, upper),
                                                                    order=RecordOrder.DESC)

    # Save identifier max values
    for k, v in identifier_max_values.items():
        show.set_meta(key=k, value=str(v))
        s.flush()

    # Count total episodes
    total = count_total_episodes(ep_map_desc)
    if total == 0:
        update_progress(progress, 100, "No episodes found from dw")
        return
    update_progress(progress, upper, f"Found {total} episodes in '{show_slug}'")

    # Iterate seasons and index episodes
    current_index = total
    for i, season in enumerate(seasons):
        # index this season in its own transaction scope
        try:
            current_index = save_dw_episodes_per_season_desc(s,
                                                             show=show,
                                                             season=season,
                                                             episodes=ep_map_desc[season.id],
                                                             start_index=current_index)
        except Exception as e:
            # rollback of the season has already occurred inside save_dw_episodes_per_season
            # Re-raise to allow scheduler to retry; caller expects retry to be scheduled
            print(f"Exception: {e}")
            raise e

        # Update progress roughly based on completed seasons
        processed = total - current_index
        frac = max(0.0, min(1.0, processed / total)) if total > 0 else 1.0
        scaled_pct = upper + min(99 - upper, int(frac * (99 - upper)))
        update_progress(progress, scaled_pct, f"Indexed {processed}/{total} episodes (season {season.index}: {season.name})")

    update_progress(progress, 100, f"Indexed all episodes: done")
