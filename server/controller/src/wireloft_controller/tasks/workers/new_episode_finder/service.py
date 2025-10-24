from asyncio.log import logger
from typing import Optional, Sequence
from sqlalchemy.orm import Session
from sqlalchemy import select

from backend.db.models import Show, Episode
from backend.types.dailywire_user_info import WlDwMembershipLevel
from backend.types.episode_types import EpisodePublishStatus
from dailywire_api.dw_api.client import MiddlewareClient
from dailywire_api.records import DwEpisodeRecord
from dailywire_authorisation import DeviceAuthClient
from ._helpers import get_shows, get_dw_episodes_since_last
from ...helpers.seasons import create_season_by_dw_season
from ...helpers.shows import get_latest_dw_season


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

        # Get last episode that is fully published
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

        latest_season = get_latest_dw_season(client, show)

        # If the season is unknown, add it to the db
        if len(show.seasons) == 0 or latest_season.dw_id != show.seasons[0].dw_id:
            create_season_by_dw_season(s, show=show, dw_season=latest_season)
            s.commit()

        # Find new episodes
        new_episodes: list[DwEpisodeRecord] = get_dw_episodes_since_last(client, show, latest_final_episode, latest_season)
