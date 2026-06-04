from asyncio.log import logger
from itertools import dropwhile, islice
from typing import Optional, Sequence
from sqlalchemy.orm import Session
from sqlalchemy import select

from backend.api.endpoints.tasks.service import trigger_now
from backend.db.models import Show, Episode, Season
from backend.types.dailywire_user_info import WlDwMembershipLevel
from backend.types.episode_types import EpisodePublishStatus
from dailywire_api.dw_api.client import MiddlewareClient
from dailywire_api.records import DwSeasonRecord
from dailywire_authorisation import DeviceAuthClient
from ._helpers import get_shows, get_season_from_list_by_id, contains_non_final_episode, get_latest_ep_index
from ...helpers.episodes.identifier import IdentifierMaxValues
from ...helpers.episodes.mapper import get_dw_episodes_since_ep, count_total_episodes
from ...helpers.progress import ProgressBounds, update_progress
from ...helpers.seasons import create_season_by_dw_season
from ...helpers.episodes.save import save_dw_episodes_per_season_asc
from ...types.general import RecordOrder


async def run_fetch_new_episodes(s: Session, *, show_id: Optional[int] = None, show_slug: Optional[str] = None, progress=None) -> None:
    print("Starting fetch_new_episodes")

    shows: Sequence[Show] = get_shows(s, show_id=show_id, show_slug=show_slug)

    # Get the desired membership level and access token
    access_token: Optional[str] = None
    tokens = DeviceAuthClient().get_token()
    if tokens:
        access_token = tokens.access_token
    client = MiddlewareClient(access_token=access_token)

    for show in shows:
        # Get the membership plan
        membership_plan: str = show.membership_level

        if membership_plan is not WlDwMembershipLevel.FREE.value and access_token is None:
            if membership_plan is not WlDwMembershipLevel.WL_ANY.value:
                logger.warning(f"No valid access token in token store for show {show.slug}: required for membership level {show.membership_level}")
                continue
        if membership_plan is WlDwMembershipLevel.WL_ANY.value:
            membership_plan = WlDwMembershipLevel.FREE.value

        # Get the last episode that is fully published
        stmt = (
            select(Episode)
            .where(Episode.show_id == show.id)
            .where(Episode.publish_status == EpisodePublishStatus.PUBLISHED_FINAL.value)
            .order_by(Episode.index.desc())
            .limit(1)
        )
        latest_final_episode: Optional[Episode] = s.execute(stmt).scalar_one_or_none()

        # Fetch remote seasons
        last_known_season: Optional[Season] = latest_final_episode.season if latest_final_episode is not None else None
        dw_show = client.get_show_page(show.slug, membership_plan=membership_plan)
        all_dw_seasons: list[DwSeasonRecord] = dw_show.seasons

        if last_known_season is not None:
            relevant_dw_seasons = list(dropwhile(lambda season: season.slug != latest_final_episode.season.slug, all_dw_seasons))
            new_dw_seasons: list[DwSeasonRecord] = list(islice(relevant_dw_seasons, 1, None))
        else:
            new_dw_seasons = all_dw_seasons

        # Add any new seasons to the db
        for new_dw_season in new_dw_seasons:
            if not any(s.slug == new_dw_season.slug for s in show.seasons):
                create_season_by_dw_season(s, show=show, dw_season=new_dw_season)
                s.flush()
                s.refresh(show, attribute_names=['seasons'])
        s.commit()

        # Get prev max values
        prev_max_values: IdentifierMaxValues = {
            m.key: int(m.value)
            for m in show.meta_items if m.key.startswith("ep_id")
        }

        # Progress bounds
        seasons = show.seasons
        x = max(1, min(int(len(seasons)), 5))
        upper = int(65 + (x - 1) * (95 - 65) / (5 - 1))

        # Build slug→dw_id mapping from fresh API data
        dw_id_by_slug = {s.slug: s.dw_id for s in all_dw_seasons}

        # Find new episodes
        ep_map_asc, identifier_max_values = get_dw_episodes_since_ep(client,
                                                                     show=show,
                                                                     membership_plan=membership_plan,
                                                                     seasons=show.seasons,
                                                                     dw_id_by_slug=dw_id_by_slug,
                                                                     since_episode=latest_final_episode,
                                                                     prev_max_values=prev_max_values,
                                                                     progress=progress,
                                                                     progress_bounds=ProgressBounds(1, upper),
                                                                     order=RecordOrder.ASC)

        # Save identifier max values
        for k, v in identifier_max_values.items():
            show.set_meta(key=k, value=str(v))
            s.flush()

        # Count total episodes
        total = count_total_episodes(ep_map_asc)
        upper = upper + 1
        if total == 0:
            update_progress(progress, 100, "No episodes found from dw")
            continue
        update_progress(progress, upper, f"Found {total} episodes in '{show.slug}'")


        # Save new episodes to db
        latest_episode_index = get_latest_ep_index(s, show=show)
        if latest_episode_index is None:
            latest_episode_index = 0

        current_index = latest_episode_index + 1
        for season_id, ep_list in ep_map_asc.items():
            season: Optional[Season] = get_season_from_list_by_id(show.seasons, season_id)
            if season is None:
                logger.warning(f"No season found for show {show.slug} with id {season_id}")
                continue

            try:
                current_index = save_dw_episodes_per_season_asc(s,
                                                                show=show,
                                                                season=season,
                                                                episodes=ep_map_asc[season_id],
                                                                start_index=current_index)
            except Exception as e:
                # rollback of the season has already occurred inside save_dw_episodes_per_season
                # Re raise to allow scheduler to retry; caller expects retry to be scheduled
                print(f"Exception: {e}")
                raise e

            # Update progress roughly based on completed seasons
            processed = current_index - 1
            frac = max(0.0, min(1.0, processed / total)) if total > 0 else 1.0
            scaled_pct = upper + min(99 - upper + 1, int(frac * (99 - upper)))
            update_progress(progress, scaled_pct,f"Indexed {processed}/{total} episodes (season {season.index}: {season.name})")

        update_progress(progress, 100, f"Indexed all episodes")

        # Start tracking a currently live episode if it exists
        # if contains_non_final_episode(ep_map_asc):
        #     update_progress(progress, 100, f"Non-final episode found, triggering monitor worker")
        #     trigger_now(definition_key="monitor_episode_worker", resource_type="episode", resource_id=None, show_slug=show.slug)
        # else:
        #     update_progress(progress, 100, f"No non-final episodes found, done")

    print("fetch_new_episodes finished")