from __future__ import annotations

import logging
import re
from typing import Dict, Tuple, List, Optional, TYPE_CHECKING, assert_never

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.types.download_profile_types import EpIdType
from backend.types.show_types import EpisodeIdentifier
from dailywire_api.records import DwEpisodeRecord
from ..general import datetime_to_string

if TYPE_CHECKING:
    from backend.db.models import Episode, Season


logger = logging.getLogger(__name__)

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


def _extra_ordinals_in_use(
        s: Session,
        *,
        show_id: int,
        prefix: str,
        exclude_episode_id: int,
) -> set[int]:
    """Return persisted WireLoft extra ordinals for one logical episode."""
    from backend.db.models import Episode

    ordinals: set[int] = set()
    for identifier in s.scalars(
        select(Episode.episode_identifier).where(
            Episode.show_id == show_id,
            Episode.id != exclude_episode_id,
            Episode.episode_identifier.startswith(prefix),
        )
    ):
        try:
            ordinals.add(int(identifier.rsplit(".", 1)[1]))
        except (TypeError, ValueError):
            continue
    return ordinals


def _first_available_extra_ordinal(
        s: Session,
        *,
        show_id: int,
        prefix: str,
        exclude_episode_id: int,
) -> int:
    used = _extra_ordinals_in_use(
        s,
        show_id=show_id,
        prefix=prefix,
        exclude_episode_id=exclude_episode_id,
    )
    ordinal = 1
    while ordinal in used:
        ordinal += 1
    return ordinal


def _current_extra_ordinal(identifier: str, prefix: str) -> int | None:
    if not identifier.startswith(prefix):
        return None
    try:
        return int(identifier.rsplit(".", 1)[1])
    except (TypeError, ValueError):
        return None


def _corrected_extra_ordinal(
        s: Session,
        *,
        episode: "Episode",
        prefix: str,
        remote_segment: int,
) -> int:
    """Choose a stable WireLoft ordinal for a corrected Daily Wire extra.

    Daily Wire's fractional segment is a category/variant marker (for example
    ``.10``), not WireLoft's sequential display ordinal. Preserve an existing
    valid extra ordinal whenever possible. The one useful direct correction is a
    literal ``.1`` segment: if Daily Wire repairs an item to the first extra after
    a bogus first-extra row disappears, that row can safely compact from ``.2``
    to ``.1``. Rows that were previously AUX use the first currently free ordinal.
    """
    current = _current_extra_ordinal(episode.episode_identifier, prefix)
    if current is not None:
        if remote_segment == 1:
            return 1
        return current
    return _first_available_extra_ordinal(
        s,
        show_id=episode.show_id,
        prefix=prefix,
        exclude_episode_id=episode.id,
    )


def _max_extra_ordinal(
        s: Session,
        *,
        show_id: int,
        prefix: str,
) -> int:
    from backend.db.models import Episode

    maximum = 0
    for identifier in s.scalars(
        select(Episode.episode_identifier).where(
            Episode.show_id == show_id,
            Episode.episode_identifier.startswith(prefix),
        )
    ):
        try:
            maximum = max(maximum, int(identifier.rsplit(".", 1)[1]))
        except (TypeError, ValueError):
            continue
    return maximum


def reconcile_episode_identifier_from_dailywire(
        s: Session,
        episode: "Episode",
        dw_episode: DwEpisodeRecord,
) -> bool:
    """Correct a persisted identifier after Daily Wire fixes episode metadata.

    Initial indexing is intentionally monotonic, so a later correction such as
    ``2500.1`` becoming ``2500.0`` cannot be repaired by replaying the normal
    allocator with its latest counters. Metadata refresh has an authoritative
    record for this exact row, so it can reconcile main episodes and episode
    extras directly from the corrected remote number/segment.
    """
    from backend.db.models import Episode

    if __is_trailer(dw_episode.title):
        return False

    show = episode.show
    identifier_type = EpisodeIdentifier(show.episode_identifier)
    desired: str | None = None
    counter_key: str | None = None
    counter_value: int | None = None
    ep_num = dw_episode.ep_number
    segment = dw_episode.ep_segment

    if identifier_type is EpisodeIdentifier.DATE_BASED:
        desired = f"{EpIdType.EP}.{datetime_to_string(dw_episode.published_date)}"
        counter_key = "ep_id.latest_ep_date"
        counter_value = int(dw_episode.published_date.timestamp())
    elif identifier_type is EpisodeIdentifier.NUMBERED:
        if ep_num is None:
            return False
        if segment == 0:
            desired = f"{EpIdType.EP}.{ep_num}"
        elif 0 < segment < _SHOW_AUX_SEGMENT_START:
            prefix = f"{EpIdType.EP_EXTRA}.{ep_num}."
            ordinal = _corrected_extra_ordinal(
                s,
                episode=episode,
                prefix=prefix,
                remote_segment=segment,
            )
            desired = f"{prefix}{ordinal}"
        else:
            return False
        counter_key = "ep_id.latest_ep_num"
        counter_value = ep_num
    elif identifier_type is EpisodeIdentifier.SEASONAL:
        if ep_num is None:
            return False
        episode_code = f"S{episode.season.index:02d}E{ep_num:02d}"
        if segment == 0:
            desired = f"{EpIdType.EP}.{episode_code}"
        elif 0 < segment < _SHOW_AUX_SEGMENT_START:
            prefix = f"{EpIdType.EP_EXTRA}.{episode_code}."
            ordinal = _corrected_extra_ordinal(
                s,
                episode=episode,
                prefix=prefix,
                remote_segment=segment,
            )
            desired = f"{prefix}{ordinal}"
        else:
            return False
        counter_key = f"ep_id.latest_season_{episode.season.index}_ep"
        counter_value = ep_num
    else:
        assert_never(identifier_type)

    if desired == episode.episode_identifier:
        return False

    collision = s.scalar(
        select(Episode.id)
        .where(
            Episode.show_id == episode.show_id,
            Episode.episode_identifier == desired,
            Episode.id != episode.id,
        )
        .limit(1)
    )
    if collision is not None:
        logger.warning(
            "Cannot reconcile episode %s identifier %s -> %s; identifier is already used by episode %s",
            episode.id,
            episode.episode_identifier,
            desired,
            collision,
        )
        return False

    old_identifier = episode.episode_identifier
    episode.episode_identifier = desired

    if counter_key is not None and counter_value is not None:
        existing_counter = int(show.get_meta(counter_key) or 0)
        show.set_meta(counter_key, str(max(existing_counter, counter_value)))

    if (
        identifier_type is EpisodeIdentifier.NUMBERED
        and ep_num is not None
        and int(show.get_meta("ep_id.latest_ep_num") or 0) == ep_num
    ):
        # Recompute after this row has adopted its corrected identifier. This
        # repairs a polluted allocator after a bad extra/main classification.
        s.flush()
        prefix = f"{EpIdType.EP_EXTRA}.{ep_num}."
        show.set_meta(
            "ep_id.latest_ep_extra_num",
            str(_max_extra_ordinal(s, show_id=episode.show_id, prefix=prefix)),
        )

    s.flush()
    logger.info(
        "Reconciled episode %s identifier %s -> %s from refreshed Daily Wire metadata",
        episode.id,
        old_identifier,
        desired,
    )
    return True
