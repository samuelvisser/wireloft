import re
from datetime import datetime, timezone, timedelta
from typing import Dict, Tuple, Optional, Sequence, List

from pydantic import AwareDatetime

from backend.api.endpoints.dailywire.episodes.service import get_episodes_from_season_list
from backend.db.models import Episode as DbEpisode, Season
from dailywire_api.records import DwEpisodeRecord as DwEpisode, DwEpisodeRecord
from wireloft_config import get_settings

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