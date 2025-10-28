from asyncio.log import logger
from itertools import dropwhile, islice
from typing import Optional, Sequence
from sqlalchemy.orm import Session
from sqlalchemy import select

from backend.db.models import Show, Episode
from backend.types.dailywire_user_info import WlDwMembershipLevel
from backend.types.episode_types import EpisodePublishStatus
from dailywire_api.dw_api.client import MiddlewareClient
from dailywire_api.records import DwSeasonRecord
from dailywire_authorisation import DeviceAuthClient
from ._helpers import get_shows
from ...helpers.episodes.identifier import IdentifierMaxValues
from ...helpers.episodes.mapper import get_dw_episodes_since_ep
from ...helpers.seasons import create_season_by_dw_season


async def run_new_episode_finder(s: Session, *, resource_id: Optional[int] = None, show_slug: Optional[str] = None, progress=None) -> None:
    print("Starting new_episode_finder")

    shows: Sequence[Show] = get_shows(s, resource_id=resource_id, show_slug=show_slug)


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
        if latest_final_episode is None:
            logger.warning(f"No published episodes found for show {show.slug}")
            continue

        # Fetch remote seasons
        dw_show = client.get_show_page(show.slug, membership_plan=membership_plan)
        all_dw_seasons: list[DwSeasonRecord] = dw_show.seasons
        relevant_dw_seasons = list(dropwhile(lambda season: season.dw_id != latest_final_episode.season.dw_id, all_dw_seasons))
        new_dw_seasons: list[DwSeasonRecord] = list(islice(relevant_dw_seasons, 1, None))

        # Add any new seasons to the db
        for new_dw_season in new_dw_seasons:
            if not any(s.dw_id == new_dw_season.dw_id for s in show.seasons):
                create_season_by_dw_season(s, show=show, dw_season=new_dw_season)
                s.flush()
                s.refresh(show, attribute_names=['seasons'])
        s.commit()

        # Get prev max values
        metadata = show.meta_items
        prev_max_values: IdentifierMaxValues = {
            m.key: int(m.value)
            for m in show.meta_items if m.key.startswith("ep_id")
        }

        print(prev_max_values)


        # Find new episodes
        # new_episodes: list[DwEpisodeRecord] = get_dw_episodes_since_last(client, show, latest_final_episode, latest_season)
