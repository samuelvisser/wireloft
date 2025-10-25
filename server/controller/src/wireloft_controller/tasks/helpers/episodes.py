import re
from datetime import datetime, timezone, timedelta
from itertools import dropwhile
from typing import Dict, Tuple, Optional, Sequence, List, Any

from pydantic import AwareDatetime

from backend.api.endpoints.dailywire.episodes.service import get_episodes_list_by_season
from backend.db.models import Episode as DbEpisode, Season, Show, Episode
from dailywire_api.dw_api.client import MiddlewareClient, ByShowSeason, ByNextPage
from dailywire_api.records import DwEpisodeRecord as DwEpisode, DwEpisodeRecord, DwSeasonRecord
from wireloft_config import get_settings
from wireloft_controller.tasks.helpers.progress import update_progress

type EpisodeMapList = Dict[int, List[DwEpisodeRecord]]
type EpisodeMapTuple = Dict[int, List[Tuple[str, DwEpisodeRecord]]]


def _get_ep_num_from_title(title: str) -> Optional[int]:
    match = re.search(r'Ep\.\s*(\d+)', title)
    if match:
        return int(match.group(1))
    return None


def get_episode_identifier_map_date_based(episode_map: EpisodeMapList, *,
                                          throw_if_truncated: bool = False) -> EpisodeMapTuple:
    map_ep_id: EpisodeMapTuple = {}
    identifiers: set[str] = set()

    for season_id, eps in episode_map.items():
        out: List[Tuple[str, DwEpisodeRecord]] = []
        for ep in eps:
            identifier: str = date_to_yyyyddmm(ep.published_date)

            if identifier in identifiers:
                identifier = "ep." + ep.published_date.strftime("%Y%m%d %H%M")

            identifiers.add(identifier)
            out.append((identifier, ep))

        if throw_if_truncated and len(out) != len(episode_map[season_id]):
            raise ValueError(f"Encountered non-unique episode date identifiers in season {season_id}, aborting")

        map_ep_id[season_id] = out

    return map_ep_id


def get_episode_identifier_map_numbered(episode_map: EpisodeMapList, *,
                                        throw_if_truncated: bool = False) -> Tuple[int, int, EpisodeMapTuple]:
    # Original season order
    season_ids = list(episode_map.keys())

    # Pre-seed to *preserve* original season order in the returned dict
    map_ep_id: EpisodeMapTuple = {sid: [] for sid in season_ids}

    identifiers: set[str] = set()
    ep_extra_num: Dict[int, int] = {}
    last_ep_num: int = 0
    last_aux_num: int = 0

    # Process seasons oldest -> newest
    for season_id, eps in reversed(episode_map.items()):
        out: List[Tuple[str, DwEpisodeRecord]] = []

        # Process episodes oldest -> newest
        for ep in reversed(eps):
            ep_num = _get_ep_num_from_title(ep.title)
            identifier = None

            if ep_num and last_ep_num < ep_num:
                candidate = f"ep.{ep_num}"
                if candidate not in identifiers:
                    last_ep_num = ep_num
                    identifier = candidate
            elif ep_num and last_ep_num == ep_num:
                last_extra_num = ep_extra_num.get(ep_num, 0)
                candidate = f"ep.{ep_num}.extra.{last_extra_num + 1}"
                if candidate not in identifiers:
                    ep_extra_num[ep_num] = last_extra_num + 1
                    identifier = candidate

            if identifier is None:
                last_aux_num += 1
                identifier = f"aux.{last_aux_num}"

            identifiers.add(identifier)
            out.append((identifier, ep))

        if throw_if_truncated and len(out) != len(episode_map[season_id]):
            raise ValueError(f"Encountered non-unique episode numbered identifiers in season {season_id}, aborting")

        # Flip back to newest -> oldest for the result. NOTE: reverse returns None, do not attach directly to map
        out.reverse()
        map_ep_id[season_id] = out

    return last_ep_num, last_aux_num, map_ep_id


# def map_all_episodes(show_slug: str, seasons: Sequence[Season], *,
#                      membership_level: str,
#                      access_token: Optional[str],
#                      ) -> EpisodeMapList:


def get_dw_episodes_by_seasons(show: Show, *,
                               seasons: Sequence[Season] = None,
                               access_token: Optional[str] = None,
                               progress=None) -> EpisodeMapList:
    return _get_dw_episodes(show, seasons=seasons, access_token=access_token, latest_final_episode=None, progress=progress)


def get_dw_episodes_since_last(client: MiddlewareClient, *,
                               show: Show,
                               access_token: Optional[str] = None,
                               latest_final_episode: Optional[Episode],
                               progress=None) -> EpisodeMapList:
    dwShow = client.get_show_page(show.slug, membership_plan=show.membership_level)
    return _get_dw_episodes(show, seasons=dwShow.seasons, access_token=access_token, latest_final_episode=latest_final_episode, progress=progress)


def _get_dw_episodes(show: Show, *,
                     seasons: List[Season | DwSeasonRecord] = None,
                     access_token: Optional[str] = None,
                     latest_final_episode: Optional[Episode],
                     progress: Optional[Any]) -> EpisodeMapList:
    """Get all episodes published since the episode passed, or all if it is empty"""

    ep_map: EpisodeMapList = {}
    season_count = len(seasons)

    update_progress(progress, 1, f"Scanning episodes for '{show.slug}'...")

    # For the first season assume 40 episodes; for each next season assume it has as many as the previous had
    actual_counts: list[int] = []
    estimated_counts: list[int] = [40] * season_count  # initial guess for first season; will be overwritten as we discover

    # Fetch episodes for this season
    client = MiddlewareClient(access_token=access_token)

    if latest_final_episode is not None:
        latest_dw_id = latest_final_episode.season.dw_id
        seasons = list(dropwhile(lambda s: s.dw_id != latest_dw_id, seasons))

    for i, season in enumerate(seasons):
        # Ensure our estimate for remaining episodes reflects the last known actual (or initial 40 for the very first)
        prev_est = actual_counts[i - 1] if i > 0 else 40
        for j in range(i, season_count):
            if j >= len(actual_counts):
                estimated_counts[j] = prev_est

        episode_list: list[DwEpisodeRecord] = []

        bySeason: ByShowSeason
        if latest_final_episode is not None:
            bySeason = ByShowSeason(
                season_dw_id=latest_final_episode.season.dw_id,
                membership_plan=show.membership_level,
                last_episode_dw_id=latest_final_episode.dw_id,
                page_size=50,
            )
        else:
            bySeason = ByShowSeason(
                season_dw_id=season.dw_id,
                membership_plan=show.membership_level,
                page_size=50,
            )

        items, next_page_url, has_next = client.get_episodes_paginated(show.slug, bySeason)
        if not has_next:
            return items
        while has_next:
            episode_list.extend(items)
            items, next_page_url, has_next = client.get_episodes_paginated(show.slug, ByNextPage(next_page_url=next_page_url))

        # Dailywire tends to return duplicate episodes, so we remove duplicates here
        eps = list(dict.fromkeys(episode_list))
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

    return ep_map


def is_published_final(episode: DwEpisode | DbEpisode):
    if not episode.publish_status == "PUBLISHED":
        return False

    ep_dur_min = int(episode.duration / 60)
    return date_is_min_ago(episode.published_date, get_settings().final_ep_published_delay_minutes + ep_dur_min)


def date_is_min_ago(date, minutes: int) -> bool:
    if not date:
        return False
    now = datetime.now(timezone.utc)
    return (now - date) >= timedelta(minutes=minutes)


def date_to_yyyyddmm(date: datetime | AwareDatetime) -> str:
    return date.strftime("%Y%m%d")
