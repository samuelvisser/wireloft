from __future__ import annotations

import re
from typing import Dict, Tuple, List, Optional, TYPE_CHECKING, assert_never

from backend.types.download_profile_types import EpIdType
from backend.types.show_types import EpisodeIdentifier
from dailywire_api.records import DwEpisodeRecord
from ..general import datetime_to_string

if TYPE_CHECKING:
    from backend.db.models import Season


type IdentifierMaxValues = Dict[str, int]
type EpisodeWithIdentifier = Tuple[str, DwEpisodeRecord]

# If The Daily Wire returns an episode segment at or above this value, it's not actually an episode segment but rather show auxiliary content
_SHOW_AUX_SEGMENT_START = 20


def identify_episodes_in_season(episode_identifier: EpisodeIdentifier,
                                season_eps: List[DwEpisodeRecord],
                                current_values: IdentifierMaxValues | None = None,
                                season: Optional["Season"] = None) -> Tuple[List[EpisodeWithIdentifier], IdentifierMaxValues]:
    # Set defaults
    if current_values is None:
        current_values = {}

    # Handle each type of episode identifier
    match episode_identifier:
        case episode_identifier.DATE_BASED:
            return _get_episode_identifier_map_date_based(season_eps, current_values)
        case episode_identifier.NUMBERED:
            return _get_episode_identifier_map_numbered(season_eps, current_values)
        case episode_identifier.SEASONAL:
            return _get_episode_identifier_map_seasonal(season_eps, current_values, season)
        case _:
            # If a new member is added and not handled above,
            # type checkers flag this, and at runtime we fail loudly.
            assert_never(episode_identifier)


def _get_episode_identifier_map_date_based(season_eps: List[DwEpisodeRecord],
                                           current_values: IdentifierMaxValues) -> Tuple[List[EpisodeWithIdentifier], IdentifierMaxValues]:
    ep_id_list: List[EpisodeWithIdentifier] = []
    last_trailer_num: int = current_values.get("ep_id.latest_trailer_num", 0)
    last_aux_num: int = current_values.get("ep_id.latest_aux_num", 0)
    # Date saved by epoch seconds
    last_ep_date: int = current_values.get("ep_id.latest_ep_date", 0)

    for ep in season_eps:
        identifier = None

        # Check for known types
        if __is_trailer(ep.title):
            last_trailer_num += 1
            identifier = f"{EpIdType.TRAILER}.{last_trailer_num}"
        else:
            ep_date = int(ep.published_date.timestamp())
            if last_ep_date < ep_date:
                last_ep_date = ep_date
                identifier = f"{EpIdType.EP}." + datetime_to_string(ep.published_date)

        # In case an episode with the same (or earlier) date was published, we assign an aux type
        if identifier is None:
            last_aux_num += 1
            identifier = f"{EpIdType.AUX}.{last_aux_num}"

        ep_id_list.append((identifier, ep))

    current_values = {
        "ep_id.latest_trailer_num": last_trailer_num,
        "ep_id.latest_aux_num": last_aux_num,
        "ep_id.latest_ep_date": last_ep_date,
    }
    return ep_id_list, current_values


def _get_episode_identifier_map_numbered(season_eps: List[DwEpisodeRecord],
                                         current_values: IdentifierMaxValues) -> Tuple[List[EpisodeWithIdentifier], IdentifierMaxValues]:
    # Prepare variables
    ep_id_list: List[EpisodeWithIdentifier] = []
    last_ep_num: int = current_values.get("ep_id.latest_ep_num", 0)
    last_ep_extra_num: int = current_values.get("ep_id.latest_ep_extra_num", 0)
    last_trailer_num: int = current_values.get("ep_id.latest_trailer_num", 0)
    last_aux_num: int = current_values.get("ep_id.latest_aux_num", 0)

    # Process episodes oldest -> newest
    for ep in season_eps:
        identifier = None
        ep_num = ep.ep_number
        segment = ep.ep_segment

        # Trailer based on episode title
        if __is_trailer(ep.title):
            last_trailer_num += 1
            identifier = f"{EpIdType.TRAILER}.{last_trailer_num}"

        # Can only be a valid regular episode if its number is higher than latest known episode number
        if identifier is None and ep_num is not None and last_ep_num <= ep_num:
            if ep_num != last_ep_num and segment == 0:
                last_ep_num = ep_num
                last_ep_extra_num = 0
                identifier = f"{EpIdType.EP}.{ep_num}"
            elif 0 < segment < _SHOW_AUX_SEGMENT_START:
                if ep_num != last_ep_num:
                    last_ep_num = ep_num
                    last_ep_extra_num = 0
                last_ep_extra_num += 1
                identifier = f"{EpIdType.EP_EXTRA}.{ep_num}.{last_ep_extra_num}"

        # Everything else (segment .20+ or a missing number) is unrelated show auxiliary content.
        if identifier is None:
            last_aux_num += 1
            identifier = f"{EpIdType.AUX}.{last_aux_num}"

        ep_id_list.append((identifier, ep))

    current_values = {
        "ep_id.latest_trailer_num": last_trailer_num,
        "ep_id.latest_aux_num": last_aux_num,
        "ep_id.latest_ep_num": last_ep_num,
        "ep_id.latest_ep_extra_num": last_ep_extra_num,
    }
    return ep_id_list, current_values


def __is_trailer(title: str) -> bool:
    return bool(re.search(r'official trailer', title, re.IGNORECASE))


def _get_episode_identifier_map_seasonal(season_eps: List[DwEpisodeRecord],
                                         current_values: IdentifierMaxValues,
                                         season: Optional["Season"]) -> Tuple[List[EpisodeWithIdentifier], IdentifierMaxValues]:
    if season is None:
        raise ValueError("Seasonal identification requires the local season the episodes belong to")

    # Prepare variables
    ep_id_list: List[EpisodeWithIdentifier] = []
    season_num: int = season.index
    last_season_ep_key = f"ep_id.latest_season_{season_num}_ep"

    last_season_ep_num: int = current_values.get(last_season_ep_key, 0)
    last_ep_extra_num: int = current_values.get("ep_id.latest_ep_extra_num", 0)
    last_trailer_num: int = current_values.get("ep_id.latest_trailer_num", 0)
    last_aux_num: int = current_values.get("ep_id.latest_aux_num", 0)

    # Process episodes oldest -> newest
    for ep in season_eps:
        identifier = None
        ep_num = ep.ep_number
        segment = ep.ep_segment

        # Trailer based on episode title
        if __is_trailer(ep.title):
            last_trailer_num += 1
            identifier = f"{EpIdType.TRAILER}.{last_trailer_num}"

        if identifier is None and ep_num is not None and last_season_ep_num <= ep_num:
            if ep_num != last_season_ep_num and segment == 0:
                last_season_ep_num = ep_num
                last_ep_extra_num = 0
                identifier = f"{EpIdType.EP}.S{season_num:02d}E{ep_num:02d}"
            elif 0 < segment < _SHOW_AUX_SEGMENT_START:
                if ep_num != last_season_ep_num:
                    last_season_ep_num = ep_num
                    last_ep_extra_num = 0
                last_ep_extra_num += 1
                identifier = f"{EpIdType.EP_EXTRA}.S{season_num:02d}E{ep_num:02d}.{last_ep_extra_num}"

        # Assign aux type if no identifier was found
        if identifier is None:
            last_aux_num += 1
            identifier = f"{EpIdType.AUX}.{last_aux_num}"

        ep_id_list.append((identifier, ep))

    # Preserve the other seasons' per-season counters that already live in
    # current_values; only update this season's counter and the shared counters.
    current_values = {
        **current_values,
        last_season_ep_key: last_season_ep_num,
        "ep_id.latest_ep_extra_num": last_ep_extra_num,
        "ep_id.latest_trailer_num": last_trailer_num,
        "ep_id.latest_aux_num": last_aux_num,
    }
    return ep_id_list, current_values
