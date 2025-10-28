from __future__ import annotations

type IdentifierMaxValues = Dict[str, int]

import re

from typing import Dict, Tuple, Optional, List, assert_never

from backend.types.show_types import EpisodeIdentifier
from dailywire_api.records import DwEpisodeRecord
from .mapper import EpisodeWithIdentifier
from ..general import datetime_to_string


def identify_episodes_in_season(episode_identifier: EpisodeIdentifier,
                                season_eps: List[DwEpisodeRecord],
                                current_values: IdentifierMaxValues | None = None,
                                previous_identifiers: set[str] | None = None) -> Tuple[List[EpisodeWithIdentifier], IdentifierMaxValues, set[str]]:
    # Set defaults
    if current_values is None:
        current_values = {}
    if previous_identifiers is None:
        previous_identifiers = set()

    # Handle each type of episode identifier
    match episode_identifier:
        case episode_identifier.DATE_BASED:
            return _get_episode_identifier_map_date_based(season_eps, current_values, previous_identifiers)
        case episode_identifier.NUMBERED:
            return _get_episode_identifier_map_numbered(season_eps, current_values, previous_identifiers)
        case episode_identifier.SEASONAL:
            return _get_episode_identifier_map_seasonal(season_eps, current_values, previous_identifiers)
        case _:
            # If a new member is added and not handled above,
            # type checkers flag this, and at runtime we fail loudly.
            assert_never(episode_identifier)


def _get_episode_identifier_map_date_based(season_eps: List[DwEpisodeRecord],
                                           current_values: IdentifierMaxValues,
                                           previous_identifiers: set[str]) -> Tuple[List[EpisodeWithIdentifier], IdentifierMaxValues, set[str]]:
    ep_id_list: List[EpisodeWithIdentifier] = []
    identifiers: set[str] = previous_identifiers
    last_trailer_num: int = current_values.get("ep_id.latest_trailer_num", 0)
    last_aux_num: int = current_values.get("ep_id.latest_aux_num", 0)

    for ep in season_eps:
        identifier = None

        # Check for known types
        if __is_trailer(ep.title):
            trailer_num = last_trailer_num + 1
            candidate = f"trailer.{trailer_num}"
            if candidate not in identifiers:
                last_trailer_num = trailer_num
                identifier = candidate
        else:
            candidate = "ep." + datetime_to_string(ep.published_date)
            if candidate not in identifiers:
                identifier = candidate

        # In case an episode with the same date was published, we assign an aux type
        if identifier is None:
            last_aux_num += 1
            identifier = f"aux.{last_aux_num}"

        identifiers.add(identifier)
        ep_id_list.append((identifier, ep))

    current_values = {
        "ep_id.latest_trailer_num": last_trailer_num,
        "ep_id.latest_aux_num": last_aux_num,
    }
    return ep_id_list, current_values, identifiers


def _get_episode_identifier_map_numbered(season_eps: List[DwEpisodeRecord],
                                         current_values: IdentifierMaxValues,
                                         previous_identifiers: set[str]) -> Tuple[List[EpisodeWithIdentifier], IdentifierMaxValues, set[str]]:
    # Prepare variables
    ep_id_list: List[EpisodeWithIdentifier] = []
    identifiers: set[str] = previous_identifiers
    ep_extra_num: Dict[int, int] = {}
    last_ep_num: int = current_values.get("ep_id.latest_ep_num", 0)
    last_trailer_num: int = current_values.get("ep_id.latest_trailer_num", 0)
    last_aux_num: int = current_values.get("ep_id.latest_aux_num", 0)

    # Process episodes oldest -> newest
    for ep in season_eps:
        ep_num = __get_ep_num_from_title(ep.title)
        identifier = None

        # Check for episodes or episode extras
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

        # Check for trailers
        if identifier is None and __is_trailer(ep.title):
            trailer_num = last_trailer_num + 1
            candidate = f"trailer.{trailer_num}"
            if candidate not in identifiers:
                last_trailer_num = trailer_num
                identifier = candidate

        # Assign aux type if no identifier was found
        if identifier is None:
            last_aux_num += 1
            identifier = f"aux.{last_aux_num}"

        identifiers.add(identifier)
        ep_id_list.append((identifier, ep))

    current_values = {
        "ep_id.latest_ep_num": last_ep_num,
        "ep_id.latest_trailer_num": last_trailer_num,
        "ep_id.latest_aux_num": last_aux_num,
    }
    return ep_id_list, current_values, identifiers


def __get_ep_num_from_title(title: str) -> Optional[int]:
    match = re.search(r'Ep\.\s*(\d+)', title)
    if match:
        return int(match.group(1))
    return None

def __is_trailer(title: str) -> bool:
    return bool(re.search(r'official trailer', title, re.IGNORECASE))


def _get_episode_identifier_map_seasonal(season_eps: List[DwEpisodeRecord],
                                         current_values: IdentifierMaxValues,
                                         previous_identifiers: set[str]) -> Tuple[List[EpisodeWithIdentifier], IdentifierMaxValues, set[str]]:
    # Prepare variables
    ep_id_list: List[EpisodeWithIdentifier] = []
    identifiers: set[str] = previous_identifiers
    season_num: int = current_values.get("ep_id.latest_season_num", 0) + 1
    last_trailer_num: int = current_values.get("ep_id.latest_trailer_num", 0)
    last_aux_num: int = current_values.get("ep_id.latest_aux_num", 0)

    # Process episodes oldest -> newest
    last_ep_num: int = 0
    for ep in season_eps:
        identifier = None

        # Check for known types
        if last_ep_num == 0 and __is_trailer(ep.title):
            trailer_num = last_trailer_num + 1
            candidate = f"trailer.{trailer_num}"
            if candidate not in identifiers:
                last_trailer_num = trailer_num
                identifier = candidate
        else:
            ep_num = last_ep_num + 1
            candidate = f"ep.S{season_num:02d}E{ep_num:02d}"
            if candidate not in identifiers:
                last_ep_num = ep_num
                identifier = candidate

        # Assign aux type if no identifier was found
        if identifier is None:
            last_aux_num += 1
            identifier = f"aux.{last_aux_num}"

        identifiers.add(identifier)
        ep_id_list.append((identifier, ep))

    current_values = {
        "ep_id.latest_season_num": season_num,
        "ep_id.latest_trailer_num": last_trailer_num,
        "ep_id.latest_aux_num": last_aux_num,
    }
    return ep_id_list, current_values, identifiers