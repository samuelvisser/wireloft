from __future__ import annotations

from collections import Counter
import re
from typing import Tuple, Optional, Sequence, List, Any, OrderedDict

from backend.db.models import Show, Episode, Season
from backend.types.show_types import EpisodeIdentifier
from dailywire_api.dw_api.client import MiddlewareClient, ByShowSeason, ByNextPage
from dailywire_api.records import DwEpisodeRecord
from task_manager.tasks.helpers.episodes.identifier import EpisodeWithIdentifier, IdentifierMaxValues, identify_episodes_in_season
from task_manager.tasks.helpers.progress import update_progress, ProgressBounds, CollectionListProgressTracker
from task_manager.tasks.types.general import RecordOrder
from ..general import datetime_to_string


type EpisodeMapTuple = OrderedDict[int, List[EpisodeWithIdentifier]]


def count_total_episodes(episodes_map: EpisodeMapTuple) -> int:
    return sum(len(eps) for eps in episodes_map.values())


def get_dw_episodes_by_seasons(
    client: MiddlewareClient,
    *,
    show: Show,
    membership_plan: str,
    seasons: Sequence[Season],
    dw_id_by_slug: dict[str, str],
    progress: Optional[Any] = None,
    progress_bounds: ProgressBounds = ProgressBounds(1, 100),
    order: RecordOrder,
    prefetched_by_season: dict[int, list[DwEpisodeRecord]] | None = None,
    vacated_identifiers: set[str] | None = None,
) -> Tuple[EpisodeMapTuple, IdentifierMaxValues]:
    """
    Fetch all episodes for the given *local* seasons.

    Returns a mapping in descending order
    """
    return _scan_seasons(
        client,
        show=show,
        membership_plan=membership_plan,
        seasons=seasons,
        dw_id_by_slug=dw_id_by_slug,
        bounds=progress_bounds,
        progress=progress,
        order=order,
        prefetched_by_season=prefetched_by_season,
        vacated_identifiers=vacated_identifiers,
    )


def get_dw_episodes_since_ep(
    client: MiddlewareClient,
    *,
    show: Show,
    membership_plan: str,
    seasons: Sequence[Season],
    dw_id_by_slug: dict[str, str],
    since_episode: Optional[Episode],
    prev_max_values: IdentifierMaxValues,
    known_episode_slugs: Optional[set[str]] = None,
    progress: Optional[Any] = None,
    progress_bounds: ProgressBounds = ProgressBounds(1, 100),
    order: RecordOrder,
    prefetched_by_season: dict[int, list[DwEpisodeRecord]] | None = None,
    vacated_identifiers: set[str] | None = None,
) -> Tuple[EpisodeMapTuple, IdentifierMaxValues]:
    """
    Fetch episodes strictly *after* the given final episode, across *all* remote seasons that follow it.

    Returns a mapping in descending order
    """
    if since_episode is not None:
        index = next((i for i, season in enumerate(seasons) if season.slug == since_episode.season.slug), -1) + 1
        seasons_to_scan = seasons[:index]
    else:
        seasons_to_scan = seasons

    return _scan_seasons(
        client,
        show=show,
        membership_plan=membership_plan,
        seasons=seasons_to_scan,
        dw_id_by_slug=dw_id_by_slug,
        since_episode=since_episode,
        prev_max_values=prev_max_values,
        known_episode_slugs=known_episode_slugs,
        bounds=progress_bounds,
        progress=progress,
        order=order,
        prefetched_by_season=prefetched_by_season,
        vacated_identifiers=vacated_identifiers,
    )


def _canonical_main_identifier(
    identifier_type: EpisodeIdentifier,
    season: Season,
    episode: DwEpisodeRecord,
) -> str | None:
    """Return the canonical main identifier a remote record can safely reclaim."""
    if re.search(r"official trailer", episode.title, re.IGNORECASE):
        return None

    if identifier_type is EpisodeIdentifier.DATE_BASED:
        return f"ep.{datetime_to_string(episode.published_date)}"
    if (
        identifier_type is EpisodeIdentifier.NUMBERED
        and episode.ep_number is not None
        and episode.ep_segment == 0
    ):
        return f"ep.{episode.ep_number}"
    if (
        identifier_type is EpisodeIdentifier.SEASONAL
        and episode.ep_number is not None
        and episode.ep_segment == 0
    ):
        return f"ep.S{season.index:02d}E{episode.ep_number:02d}"
    return None


def _is_vacated_replacement(
    identifier_type: EpisodeIdentifier,
    season: Season,
    episode: DwEpisodeRecord,
    vacated_identifiers: set[str],
) -> bool:
    desired = _canonical_main_identifier(identifier_type, season, episode)
    return desired is not None and desired in vacated_identifiers


def _advance_reclaimed_counter(
    *,
    identifier_type: EpisodeIdentifier,
    episode: DwEpisodeRecord,
    season: Season,
    current_values: IdentifierMaxValues,
) -> IdentifierMaxValues:
    """Advance a rolled-back high-water mark without ever rewinding a newer one."""
    values = dict(current_values)
    if identifier_type is EpisodeIdentifier.DATE_BASED:
        timestamp = int(episode.published_date.timestamp())
        values["ep_id.latest_ep_date"] = max(
            values.get("ep_id.latest_ep_date", 0),
            timestamp,
        )
        return values

    if episode.ep_number is None:
        return values

    if identifier_type is EpisodeIdentifier.NUMBERED:
        previous = values.get("ep_id.latest_ep_num", 0)
        values["ep_id.latest_ep_num"] = max(previous, episode.ep_number)
        if episode.ep_number > previous:
            values["ep_id.latest_ep_extra_num"] = 0
        return values

    if identifier_type is EpisodeIdentifier.SEASONAL:
        key = f"ep_id.latest_season_{season.index}_ep"
        previous = values.get(key, 0)
        values[key] = max(previous, episode.ep_number)
        if episode.ep_number > previous:
            values["ep_id.latest_ep_extra_num"] = 0
        return values

    return values


def _identify_with_vacated_reclaims(
    *,
    identifier_type: EpisodeIdentifier,
    episodes: list[DwEpisodeRecord],
    current_values: IdentifierMaxValues,
    season: Season,
    vacated_identifiers: set[str],
) -> tuple[list[EpisodeWithIdentifier], IdentifierMaxValues]:
    """Identify records while allowing unambiguous reclamation of quarantined main ids.

    Normal identifier allocation is intentionally monotonic. A replacement for an
    older quarantined episode is the exception: if its canonical main identifier is
    currently free and recorded as vacated, it may reclaim that identifier without
    rewinding a newer high-water counter. Multiple candidates for one vacated id are
    deliberately treated as ambiguous and fall back to normal allocation.
    """
    desired_identifiers = [
        _canonical_main_identifier(identifier_type, season, episode)
        for episode in episodes
    ]
    candidate_counts = Counter(
        identifier
        for identifier in desired_identifiers
        if identifier is not None and identifier in vacated_identifiers
    )

    identified: list[EpisodeWithIdentifier] = []
    for episode, desired in zip(episodes, desired_identifiers, strict=True):
        if (
            desired is not None
            and desired in vacated_identifiers
            and candidate_counts[desired] == 1
        ):
            identified.append((desired, episode))
            current_values = _advance_reclaimed_counter(
                identifier_type=identifier_type,
                episode=episode,
                season=season,
                current_values=current_values,
            )
            vacated_identifiers.remove(desired)
            continue

        mapped, current_values = identify_episodes_in_season(
            identifier_type,
            [episode],
            current_values,
            season=season,
        )
        identified.extend(mapped)
    return identified, current_values


def _scan_seasons(
    client: MiddlewareClient,
    *,
    show: Show,
    membership_plan: str,
    seasons: Sequence[Season],
    dw_id_by_slug: dict[str, str],
    since_episode: Optional[Episode] = None,
    prev_max_values: Optional[IdentifierMaxValues] = None,
    known_episode_slugs: Optional[set[str]] = None,
    bounds: ProgressBounds,
    progress: Optional[Any],
    order: RecordOrder,
    prefetched_by_season: dict[int, list[DwEpisodeRecord]] | None = None,
    vacated_identifiers: set[str] | None = None,
) -> Tuple[EpisodeMapTuple, IdentifierMaxValues]:
    ep_map: EpisodeMapTuple = OrderedDict()
    current_values: IdentifierMaxValues = dict(prev_max_values) if prev_max_values else {}
    known_episode_slugs = known_episode_slugs or set()
    prefetched_by_season = prefetched_by_season or {}
    available_vacated_identifiers = set(vacated_identifiers or ())

    seasons_asc = sorted(seasons, key=lambda season: season.index)
    season_count = len(seasons_asc)
    update_progress(progress, bounds.min_pct, f"Scanning episodes for '{show.slug}'...")
    tracker = CollectionListProgressTracker(progress_sink=progress, bounds=bounds, collection_count=season_count)

    for idx, season in enumerate(seasons_asc):
        eps = list(prefetched_by_season.get(season.id) or fetch_all_episodes_paginated(
            client,
            show.slug,
            ByShowSeason(
                season_dw_id=dw_id_by_slug[season.slug],
                membership_plan=membership_plan,
                page_size=50,
                order_by="CreatedAt_ASC",
            ),
        ))
        eps = list(dict.fromkeys(eps))
        eps.sort(key=lambda rec: (rec.published_date, rec.ep_number or 0, rec.ep_segment))
        identifier_type = EpisodeIdentifier(show.episode_identifier)

        if since_episode is not None:
            cursor_index = next((i for i, rec in enumerate(eps) if rec.slug == since_episode.slug), None)
            if cursor_index is not None:
                # Normally incremental discovery only needs records after the last
                # settled cursor. A replacement for a quarantined older episode is
                # the deliberate exception: keep those pre-cursor records so the
                # vacated canonical identifier can be reclaimed.
                before_cursor = [
                    rec
                    for rec in eps[:cursor_index]
                    if _is_vacated_replacement(
                        identifier_type,
                        season,
                        rec,
                        available_vacated_identifiers,
                    )
                ]
                eps = before_cursor + eps[cursor_index + 1:]

        if known_episode_slugs:
            eps = [rec for rec in eps if rec.slug not in known_episode_slugs]

        eps_with_id, current_values = _identify_with_vacated_reclaims(
            identifier_type=identifier_type,
            episodes=eps,
            current_values=current_values,
            season=season,
            vacated_identifiers=available_vacated_identifiers,
        )
        if order == RecordOrder.DESC:
            eps_with_id.reverse()
        ep_map[season.id] = eps_with_id

        tracker.record_collection_actual(idx, len(eps))
        tracker.update(f"Mapped {sum(tracker.actual)} episodes so far (season {season.index}: {season.name})")

    ep_map_final = OrderedDict(reversed(list(ep_map.items()))) if order == RecordOrder.DESC else ep_map
    update_progress(progress, bounds.max_pct, f"Finished scanning {season_count} season(s) for '{show.slug}'.")
    return ep_map_final, current_values


def fetch_all_episodes_paginated(
    client: MiddlewareClient,
    show_slug: str,
    by: ByShowSeason,
) -> List[DwEpisodeRecord]:
    """Fetch one entire Daily Wire season while preserving request pagination."""
    items, next_page_url, has_next = client.get_episodes_paginated(show_slug, by)
    all_items: List[DwEpisodeRecord] = list(items) if items else []
    while has_next and next_page_url:
        items, next_page_url, has_next = client.get_episodes_paginated(
            show_slug,
            ByNextPage(next_page_url=next_page_url),
        )
        if items:
            all_items.extend(items)
    return all_items
