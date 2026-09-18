from __future__ import annotations

import logging
import re
from typing import Dict, List, Optional, Tuple, TYPE_CHECKING, assert_never

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.types.download_profile_types import EpIdType
from backend.types.episode_types import EpisodeExtraType
from backend.types.season_types import SeasonType
from backend.types.show_types import EpisodeIdentifier
from backend.utils.episode import EpisodeIdentifierInfo
from dailywire_api.records import DwEpisodeRecord
from ..general import datetime_to_string

if TYPE_CHECKING:
    from backend.db.models import Episode, Season


logger = logging.getLogger(__name__)

type IdentifierMaxValues = Dict[str, int]
type EpisodeWithIdentifier = Tuple[str, DwEpisodeRecord]

# Any non-zero Daily Wire segment is source-backed episode-extra content.
# Standalone auxiliary allocation is reserved for records without a usable
# source number, duplicate source slots, or records in an extra season.
_OFFICIAL_TRAILER_RE = re.compile(r"\bofficial\s+trailer\b", re.IGNORECASE)


def is_episode_trailer(ep: DwEpisodeRecord) -> bool:
    """Return trailer semantics, preferring The Daily Wire's authoritative flag."""
    if ep.is_trailer is not None:
        return bool(ep.is_trailer)
    return bool(_OFFICIAL_TRAILER_RE.search(ep.title or ""))


def identify_episodes_in_season(
    episode_identifier: EpisodeIdentifier,
    season_eps: List[DwEpisodeRecord],
    current_values: IdentifierMaxValues | None = None,
    season: Optional["Season"] = None,
    *,
    occupied_identifiers: set[str] | None = None,
) -> Tuple[List[EpisodeWithIdentifier], IdentifierMaxValues]:
    """Assign canonical identifiers without using episode-number high-water marks.

    The Daily Wire's complete episode number is authoritative for normal episodes
    and attached episode extras. WireLoft only allocates its own show-global
    counters for standalone trailers and auxiliary content.
    """
    values = dict(current_values or {})
    occupied = occupied_identifiers if occupied_identifiers is not None else set()
    occupied_source_slots = _occupied_source_slots(occupied)
    for episode_type, counter_key in (
        (EpIdType.AUX, "ep_id.latest_aux_num"),
        (EpIdType.TRAILER, "ep_id.latest_trailer_num"),
    ):
        occupied_max = _max_generated_identifier(occupied, episode_type)
        if counter_key in values or occupied_max:
            values[counter_key] = max(
                int(values.get(counter_key, 0)),
                occupied_max,
            )

    match episode_identifier:
        case EpisodeIdentifier.DATE_BASED:
            return _get_episode_identifier_map_date_based(
                season_eps,
                values,
                occupied,
                occupied_source_slots,
                season=season,
            )
        case EpisodeIdentifier.NUMBERED:
            return _get_episode_identifier_map_numbered(
                season_eps,
                values,
                occupied,
                occupied_source_slots,
                season=season,
            )
        case EpisodeIdentifier.SEASONAL:
            if season is None:
                raise ValueError("Seasonal identification requires the local season")
            return _get_episode_identifier_map_seasonal(
                season_eps,
                values,
                occupied,
                occupied_source_slots,
                season=season,
            )
        case _:
            assert_never(episode_identifier)


def _identifier_info(identifier: str) -> EpisodeIdentifierInfo | None:
    try:
        return EpisodeIdentifierInfo.from_identifier(identifier)
    except ValueError:
        return None


def _occupied_source_slots(occupied: set[str]) -> set[str]:
    slots: set[str] = set()
    for identifier in occupied:
        info = _identifier_info(identifier)
        if info is not None and info.source_slot is not None:
            slots.add(info.source_slot)
    return slots


def _max_generated_identifier(occupied: set[str], episode_type: EpIdType) -> int:
    maximum = 0
    for identifier in occupied:
        info = _identifier_info(identifier)
        if info is None or info.type != episode_type or info.episode_number is None:
            continue
        try:
            maximum = max(maximum, int(info.episode_number))
        except ValueError:
            continue
    return maximum


def _reserve_generated_identifier(
    episode_type: EpIdType,
    values: IdentifierMaxValues,
    occupied: set[str],
) -> str:
    counter_key = (
        "ep_id.latest_trailer_num"
        if episode_type is EpIdType.TRAILER
        else "ep_id.latest_aux_num"
    )
    if counter_key in values:
        current = int(values[counter_key])
    else:
        current = _max_generated_identifier(occupied, episode_type)
    while True:
        current += 1
        identifier = f"{episode_type}.{current}"
        if identifier not in occupied:
            values[counter_key] = current
            occupied.add(identifier)
            return identifier


def _reserve_direct_or_aux(
    candidate: str,
    *,
    ep: DwEpisodeRecord,
    values: IdentifierMaxValues,
    occupied: set[str],
    occupied_source_slots: set[str],
) -> str:
    info = EpisodeIdentifierInfo.from_identifier(candidate)
    source_slot = info.source_slot
    if candidate not in occupied and (
        source_slot is None or source_slot not in occupied_source_slots
    ):
        occupied.add(candidate)
        if source_slot is not None:
            occupied_source_slots.add(source_slot)
        return candidate

    logger.warning(
        "The Daily Wire source slot %s for episode %s is already occupied; "
        "classifying the duplicate as auxiliary content",
        source_slot or candidate,
        ep.slug,
    )
    return _reserve_generated_identifier(EpIdType.AUX, values, occupied)


def _is_extra_season(season: Optional["Season"]) -> bool:
    return bool(season is not None and season.season_type == SeasonType.EXTRA.value)


def _normal_season_number(season: "Season") -> int:
    number = int(season.season_number)
    if number < 1:
        raise ValueError(
            f"Normal season {season.slug!r} has invalid media season number {number}"
        )
    return number


def _standalone_identifier(
    ep: DwEpisodeRecord,
    *,
    values: IdentifierMaxValues,
    occupied: set[str],
) -> str:
    return _reserve_generated_identifier(
        EpIdType.TRAILER if is_episode_trailer(ep) else EpIdType.AUX,
        values,
        occupied,
    )


def direct_identifier_for_episode(
    identifier_type: EpisodeIdentifier,
    season: "Season",
    ep: DwEpisodeRecord,
) -> str | None:
    """Return the canonical source-backed identifier, or None for standalone content."""
    if _is_extra_season(season):
        return None

    if identifier_type is EpisodeIdentifier.DATE_BASED:
        if is_episode_trailer(ep):
            return None
        return f"{EpIdType.EP}.{datetime_to_string(ep.published_date)}"

    ep_num = ep.ep_number
    if ep_num is None:
        return None

    segment = ep.ep_segment
    trailer = is_episode_trailer(ep)
    if segment == 0:
        if trailer:
            return None
        if identifier_type is EpisodeIdentifier.NUMBERED:
            return f"{EpIdType.EP}.{ep_num}"
        if identifier_type is EpisodeIdentifier.SEASONAL:
            season_number = _normal_season_number(season)
            return f"{EpIdType.EP}.S{season_number:02d}E{ep_num:02d}"

    if segment > 0:
        extra_type = EpisodeExtraType.TRAILER if trailer else EpisodeExtraType.OTHER
        if identifier_type is EpisodeIdentifier.NUMBERED:
            return f"{EpIdType.EP_EXTRA}.{extra_type}.{ep_num}.{segment}"
        if identifier_type is EpisodeIdentifier.SEASONAL:
            season_number = _normal_season_number(season)
            return (
                f"{EpIdType.EP_EXTRA}.{extra_type}."
                f"S{season_number:02d}E{ep_num:02d}.{segment}"
            )

    return None


def _get_episode_identifier_map_numbered(
    season_eps: List[DwEpisodeRecord],
    current_values: IdentifierMaxValues,
    occupied: set[str],
    occupied_source_slots: set[str],
    *,
    season: Optional["Season"],
) -> Tuple[List[EpisodeWithIdentifier], IdentifierMaxValues]:
    mapped: list[EpisodeWithIdentifier] = []

    for ep in season_eps:
        ep_num = ep.ep_number
        segment = ep.ep_segment
        trailer = is_episode_trailer(ep)

        if _is_extra_season(season) or ep_num is None:
            identifier = _standalone_identifier(
                ep,
                values=current_values,
                occupied=occupied,
            )
        elif segment == 0:
            if trailer:
                identifier = _reserve_generated_identifier(
                    EpIdType.TRAILER,
                    current_values,
                    occupied,
                )
            else:
                identifier = _reserve_direct_or_aux(
                    f"{EpIdType.EP}.{ep_num}",
                    ep=ep,
                    values=current_values,
                    occupied=occupied,
                    occupied_source_slots=occupied_source_slots,
                )
        elif segment > 0:
            extra_type = (
                EpisodeExtraType.TRAILER
                if trailer
                else EpisodeExtraType.OTHER
            )
            identifier = _reserve_direct_or_aux(
                f"{EpIdType.EP_EXTRA}.{extra_type}.{ep_num}.{segment}",
                ep=ep,
                values=current_values,
                occupied=occupied,
                occupied_source_slots=occupied_source_slots,
            )
        else:
            identifier = _standalone_identifier(
                ep,
                values=current_values,
                occupied=occupied,
            )

        mapped.append((identifier, ep))

    return mapped, current_values


def _get_episode_identifier_map_seasonal(
    season_eps: List[DwEpisodeRecord],
    current_values: IdentifierMaxValues,
    occupied: set[str],
    occupied_source_slots: set[str],
    *,
    season: "Season",
) -> Tuple[List[EpisodeWithIdentifier], IdentifierMaxValues]:
    mapped: list[EpisodeWithIdentifier] = []
    season_number = (
        0 if _is_extra_season(season) else _normal_season_number(season)
    )

    for ep in season_eps:
        ep_num = ep.ep_number
        segment = ep.ep_segment
        trailer = is_episode_trailer(ep)

        if _is_extra_season(season) or ep_num is None:
            identifier = _standalone_identifier(
                ep,
                values=current_values,
                occupied=occupied,
            )
        elif segment == 0:
            if trailer:
                identifier = _reserve_generated_identifier(
                    EpIdType.TRAILER,
                    current_values,
                    occupied,
                )
            else:
                identifier = _reserve_direct_or_aux(
                    f"{EpIdType.EP}.S{season_number:02d}E{ep_num:02d}",
                    ep=ep,
                    values=current_values,
                    occupied=occupied,
                    occupied_source_slots=occupied_source_slots,
                )
        elif segment > 0:
            extra_type = (
                EpisodeExtraType.TRAILER
                if trailer
                else EpisodeExtraType.OTHER
            )
            identifier = _reserve_direct_or_aux(
                (
                    f"{EpIdType.EP_EXTRA}.{extra_type}."
                    f"S{season_number:02d}E{ep_num:02d}.{segment}"
                ),
                ep=ep,
                values=current_values,
                occupied=occupied,
                occupied_source_slots=occupied_source_slots,
            )
        else:
            identifier = _standalone_identifier(
                ep,
                values=current_values,
                occupied=occupied,
            )

        mapped.append((identifier, ep))

    return mapped, current_values


def _get_episode_identifier_map_date_based(
    season_eps: List[DwEpisodeRecord],
    current_values: IdentifierMaxValues,
    occupied: set[str],
    occupied_source_slots: set[str],
    *,
    season: Optional["Season"],
) -> Tuple[List[EpisodeWithIdentifier], IdentifierMaxValues]:
    mapped: list[EpisodeWithIdentifier] = []
    last_ep_date = int(current_values.get("ep_id.latest_ep_date", 0))

    for ep in season_eps:
        if _is_extra_season(season) or is_episode_trailer(ep):
            identifier = _standalone_identifier(
                ep,
                values=current_values,
                occupied=occupied,
            )
        else:
            ep_date = int(ep.published_date.timestamp())
            candidate = f"{EpIdType.EP}.{datetime_to_string(ep.published_date)}"
            if last_ep_date < ep_date and candidate not in occupied:
                last_ep_date = ep_date
                occupied.add(candidate)
                identifier = candidate
            else:
                identifier = _reserve_generated_identifier(
                    EpIdType.AUX,
                    current_values,
                    occupied,
                )
        mapped.append((identifier, ep))

    current_values["ep_id.latest_ep_date"] = last_ep_date
    return mapped, current_values


def _generated_type_for_record(
    identifier_type: EpisodeIdentifier,
    season: "Season",
    dw_episode: DwEpisodeRecord,
) -> EpIdType | None:
    if _is_extra_season(season):
        return EpIdType.TRAILER if is_episode_trailer(dw_episode) else EpIdType.AUX

    if identifier_type is EpisodeIdentifier.DATE_BASED:
        return EpIdType.TRAILER if is_episode_trailer(dw_episode) else None

    if dw_episode.ep_number is None:
        return EpIdType.TRAILER if is_episode_trailer(dw_episode) else EpIdType.AUX

    segment = dw_episode.ep_segment
    if identifier_type in {EpisodeIdentifier.NUMBERED, EpisodeIdentifier.SEASONAL}:
        if segment == 0 and is_episode_trailer(dw_episode):
            return EpIdType.TRAILER
        return None

    return None


def reconcile_episode_identifier_from_dailywire(
    s: Session,
    episode: "Episode",
    dw_episode: DwEpisodeRecord,
) -> bool:
    """Recompute one identifier from authoritative Daily Wire metadata."""
    from backend.db.models import Episode

    episode.dw_episode_number = dw_episode.episode_number or None

    identifier_type = EpisodeIdentifier(episode.show.episode_identifier)
    season = episode.season
    if season is None:
        return False

    occupied = set(
        s.scalars(
            select(Episode.episode_identifier).where(
                Episode.show_id == episode.show_id,
                Episode.id != episode.id,
            )
        )
    )
    values: IdentifierMaxValues = {
        item.key: int(item.value)
        for item in episode.show.meta_items
        if item.key in {
            "ep_id.latest_aux_num",
            "ep_id.latest_trailer_num",
            "ep_id.latest_ep_date",
        }
    }

    generated_type = _generated_type_for_record(
        identifier_type,
        season,
        dw_episode,
    )
    current_info = _identifier_info(episode.episode_identifier)

    if generated_type is not None and current_info is not None and current_info.type == generated_type:
        return False

    [mapped], updated_values = identify_episodes_in_season(
        identifier_type,
        [dw_episode],
        values,
        season=season,
        occupied_identifiers=occupied,
    )
    desired, _ = mapped

    desired_info = _identifier_info(desired)
    if (
        generated_type is None
        and current_info is not None
        and current_info.type == EpIdType.AUX
        and desired_info is not None
        and desired_info.type == EpIdType.AUX
    ):
        # A direct Daily Wire source slot is occupied by another record. The
        # episode was already quarantined into the show-global AUX namespace, so
        # keep that stable AUX identity rather than allocating a fresh counter.
        return False

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
            "Cannot reconcile episode %s identifier %s -> %s; identifier is already "
            "used by episode %s",
            episode.id,
            episode.episode_identifier,
            desired,
            collision,
        )
        return False

    old_identifier = episode.episode_identifier
    episode.episode_identifier = desired
    for key in ("ep_id.latest_aux_num", "ep_id.latest_trailer_num", "ep_id.latest_ep_date"):
        if key in updated_values:
            episode.show.set_meta(key, str(updated_values[key]))

    s.flush()
    logger.info(
        "Reconciled episode %s identifier %s -> %s from refreshed Daily Wire metadata",
        episode.id,
        old_identifier,
        desired,
    )
    return True
