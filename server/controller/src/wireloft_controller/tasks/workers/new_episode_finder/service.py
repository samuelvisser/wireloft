from asyncio.log import logger
from typing import Optional, Sequence
from sqlalchemy.orm import Session
from sqlalchemy import select

from backend.db.models import Show, Episode
from backend.types.dailywire_user_info import WlDwMembershipLevel
from dailywire_api.dw_api.client import MiddlewareClient, ByShowSeason
from dailywire_authorisation import DeviceAuthClient
from ._helpers import get_shows


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
        if show.membership_level is not WlDwMembershipLevel.FREE.value and access_token is None:
            logger.warning(f"No valid access token in token store for show {show.slug}: required for membership level {show.membership_level}")
            continue

        latest_final_episode: Optional[Episode] = s.execute(
            select(Episode)
            .where(Episode.show_id == show.id)
            .where(Episode.dw_id.isnot(None))
            .order_by(Episode.index.desc())
            .limit(1)
        ).scalar_one_or_none()

        if latest_final_episode is None:
            logger.warning(f"No episodes found for show {show.slug}")
            continue

        # TODO handle DailyWire having new season
        season_dw_id = latest_final_episode.season.dw_id
        client.get_episodes_paginated(show.slug, ByShowSeason(
            season_dw_id,
            membership_plan=show.membership_level,
            last_episode_dw_id=latest_final_episode.dw_id,
            page_size=5
        ))