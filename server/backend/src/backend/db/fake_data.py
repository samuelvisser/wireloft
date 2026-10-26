"""Development/demo data for ``backend-api db seed``.

Run it on a migrated database: the initial seed already created the default
Local Media Profiles, so the demo shows only add shows, seasons and episodes.
"""
from __future__ import annotations

import datetime as dt
from typing import Any

from backend.types.dailywire_user_info import WlDwMembershipLevel
from backend.types.episode_types import EpisodePublishStatus
from backend.types.media_types import MediaType
from backend.types.show_types import EpisodeIdentifier, ShowType
from backend.utils.helpers import slugify


def _published(show_index: int, episode_index: int) -> dt.datetime:
    """A stable, distinct publication instant per demo episode."""
    start = dt.datetime(2025, 1, 1, 12, tzinfo=dt.timezone.utc)
    return start + dt.timedelta(days=episode_index, minutes=show_index)


def _show(slug: str, title: str, author: str) -> dict[str, Any]:
    return {
        "uuid": f"demo-show-{slug}",
        "slug": slug,
        "title": title,
        "description": None,
        "sharing_url": f"https://www.dailywire.com/show/{slug}",
        "membership_level": WlDwMembershipLevel.FREE.value,
        "type": ShowType.PODCAST.value,
        "episode_identifier": EpisodeIdentifier.DATE_BASED.value,
        "author_name": author,
        "author_slug": slugify(author),
    }


shows: list[dict[str, Any]] = [
    _show("the-ben-shapiro-show", "The Ben Shapiro Show", "Ben Shapiro"),
    _show("the-matt-walsh-show", "The Matt Walsh Show", "Matt Walsh"),
    _show("ben-after-dark", "Ben After Dark", "Ben Shapiro"),
]

# Number of demo episodes per show, by show slug.
episode_counts: dict[str, int] = {
    "the-ben-shapiro-show": 30,
    "the-matt-walsh-show": 20,
    "ben-after-dark": 7,
}


def episodes_for(show: dict[str, Any], show_index: int) -> list[dict[str, Any]]:
    """Demo episodes of one show, oldest first, without show and season ids."""
    episodes = []
    for index in range(1, episode_counts[show["slug"]] + 1):
        published = _published(show_index, index)
        episodes.append({
            "uuid": f"demo-episode-{show['slug']}-{index}",
            "type": MediaType.EPISODE.value,
            "index": index,
            "episode_identifier": f"ep.{published:%Y-%m-%dT%H:%M:%S.%f}",
            "slug": f"{show['slug']}-{index}",
            "publish_status": EpisodePublishStatus.PUBLISHED_FINAL.value,
            "metadata_is_final": True,
            "sharing_url": f"{show['sharing_url']}/episode-{index}",
            "published_date": published,
            "title": f"{show['title']} — Episode {index}",
            "description": "Lorem ipsum dolor sit amet, consectetur adipiscing elit.",
        })
    return episodes
