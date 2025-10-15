from __future__ import annotations

from typing import Optional

from dailywire_api.dw_api.client import MiddlewareClient, ByShowSeason, ByNextPage
from dailywire_api.records import EpisodeRecord, ShowRecord
from dailywire_api.records.EpisodeDetailRecord import EpisodeDetailRecord


def get_episodes_from_show_list(
    show_slug: str,
    *,
    membership_plan: Optional[str] = None,
) -> list[EpisodeRecord]:
    """Fetch every single episode for a show from the Daily Wire API."""
    client = MiddlewareClient()

    show_record = client.get_show_page(slug=show_slug, membership_plan=membership_plan)

    # Get all episodes for all seasons, reverse to make sure the newest episodes are first in the list
    episode_list: list[EpisodeRecord] = []
    for season in reversed(show_record.seasons):
        episode_list.extend(get_episodes_from_season_list(show_slug, season.id, client=client, membership_plan=membership_plan))

    return episode_list


def get_episodes_from_season_list(
        show_slug: str,
        season_id: str,
        *,
        client: Optional[MiddlewareClient] = None,
        access_token: Optional[str] = None,
        membership_plan: Optional[str] = None,
        page_size: int = 50,
) -> list[EpisodeRecord]:
    """Fetch every episode for a season from the Daily Wire API."""
    if client is None:
        client = MiddlewareClient(access_token=access_token)

    episode_list: list[EpisodeRecord] = []

    items, next_page_url, has_next = client.get_episodes_paginated(show_slug, ByShowSeason(
        season_id=season_id,
        membership_plan=membership_plan,
        page_size=page_size,
    ))
    if not has_next:
        return items
    while has_next:
        episode_list.extend(items)
        items, next_page_url, has_next = client.get_episodes_paginated(show_slug, ByNextPage(next_page_url=next_page_url))

    return episode_list

def get_episode_details(episode_slug: str):
    client = MiddlewareClient()
    return client.get_episode_details(episode_slug)