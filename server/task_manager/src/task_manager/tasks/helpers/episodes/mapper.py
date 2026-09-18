from __future__ import annotations

import re
from typing import Any, List, Optional, OrderedDict, Sequence, Tuple

from backend.db.models import Episode, Season, Show
from backend.types.show_types import EpisodeIdentifier
from dailywire_api.dw_api.client import (
    ByNextPage,
    ByShowSeason,
    MiddlewareAPIError,
    MiddlewareClient,
)
from dailywire_api.records import DwEpisodeRecord
from task_manager.tasks.helpers.episodes.identifier import (
    EpisodeWithIdentifier,
    IdentifierMaxValues,
    direct_identifier_for_episode,
    identify_episodes_in_season,
)
from task_manager.tasks.helpers.progress import (
    CollectionListProgressTracker,
    ProgressBounds,
    update_progress,
)
from task_manager.tasks.types.general import RecordOrder


type EpisodeMapTuple = OrderedDict[int, List[EpisodeWithIdentifier]]

_TRAILER_TITLE_RE = re.compile(r"\btrailer\b", re.IGNORECASE)


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
    occupied_identifiers: set[str] | None = None,
) -> Tuple[EpisodeMapTuple, IdentifierMaxValues]:
    """Fetch and identify all episodes for the given local seasons."""
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
        occupied_identifiers=occupied_identifiers,
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
    occupied_identifiers: set[str] | None = None,
) -> Tuple[EpisodeMapTuple, IdentifierMaxValues]:
    """Fetch episodes after the settled cursor, including vacated replacements."""
    if since_episode is not None:
        index = next(
            (
                i
                for i, season in enumerate(seasons)
                if season.slug == since_episode.season.slug
            ),
            -1,
        ) + 1
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
        occupied_identifiers=occupied_identifiers,
    )


def _is_vacated_replacement(
    identifier_type: EpisodeIdentifier,
    season: Season,
    episode: DwEpisodeRecord,
    vacated_identifiers: set[str],
) -> bool:
    desired = direct_identifier_for_episode(identifier_type, season, episode)
    return desired is not None and desired in vacated_identifiers


def _resolve_trailer_candidates(
    client: MiddlewareClient,
    *,
    episodes: list[DwEpisodeRecord],
    require_member_exclusive: bool,
) -> list[DwEpisodeRecord]:
    """Resolve possible trailers so indexing can use The Daily Wire's isTrailer."""
    resolved: list[DwEpisodeRecord] = []
    for episode in episodes:
        if (
            episode.is_trailer is not None
            or not _TRAILER_TITLE_RE.search(episode.title or "")
        ):
            resolved.append(episode)
            continue

        try:
            detail = client.get_episode_details(
                episode.slug,
                require_member_exclusive=require_member_exclusive,
            )
        except MiddlewareAPIError as exc:
            if exc.status_code != 404:
                raise
            resolved.append(episode)
        else:
            resolved.append(detail)
    return resolved


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
    occupied_identifiers: set[str] | None = None,
) -> Tuple[EpisodeMapTuple, IdentifierMaxValues]:
    ep_map: EpisodeMapTuple = OrderedDict()
    current_values: IdentifierMaxValues = dict(prev_max_values) if prev_max_values else {}
    known_episode_slugs = known_episode_slugs or set()
    prefetched_by_season = prefetched_by_season or {}
    available_vacated_identifiers = set(vacated_identifiers or ())
    # Identifier allocation mutates this set while scanning multiple seasons.
    # Keep that mutation local so the caller's persisted-identifier snapshot can
    # be reused for the authoritative post-detail identifier pass.
    occupied = set(occupied_identifiers or ())

    seasons_asc = sorted(seasons, key=lambda season: season.index)
    season_count = len(seasons_asc)
    update_progress(progress, bounds.min_pct, f"Scanning episodes for '{show.slug}'...")
    tracker = CollectionListProgressTracker(
        progress_sink=progress,
        bounds=bounds,
        collection_count=season_count,
    )

    identifier_type = EpisodeIdentifier(show.episode_identifier)
    require_member_exclusive = membership_plan != "FREE"

    for idx, season in enumerate(seasons_asc):
        eps = list(
            prefetched_by_season.get(season.id)
            or fetch_all_episodes_paginated(
                client,
                show.slug,
                ByShowSeason(
                    season_dw_id=dw_id_by_slug[season.slug],
                    membership_plan=membership_plan,
                    page_size=50,
                    order_by="CreatedAt_ASC",
                ),
            )
        )
        eps = list(dict.fromkeys(eps))
        eps.sort(key=lambda rec: (rec.published_date, rec.ep_number or 0, rec.ep_segment))
        eps = _resolve_trailer_candidates(
            client,
            episodes=eps,
            require_member_exclusive=require_member_exclusive,
        )

        if since_episode is not None:
            cursor_index = next(
                (i for i, rec in enumerate(eps) if rec.slug == since_episode.slug),
                None,
            )
            if cursor_index is not None:
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
                eps = before_cursor + eps[cursor_index + 1 :]

        if known_episode_slugs:
            eps = [rec for rec in eps if rec.slug not in known_episode_slugs]

        eps_with_id, current_values = identify_episodes_in_season(
            identifier_type,
            eps,
            current_values,
            season=season,
            occupied_identifiers=occupied,
        )
        for identifier, _episode in eps_with_id:
            available_vacated_identifiers.discard(identifier)

        if order == RecordOrder.DESC:
            eps_with_id.reverse()
        ep_map[season.id] = eps_with_id

        tracker.record_collection_actual(idx, len(eps))
        tracker.update(
            f"Mapped {sum(tracker.actual)} episodes so far "
            f"(season {season.index}: {season.name})"
        )

    ep_map_final = (
        OrderedDict(reversed(list(ep_map.items())))
        if order == RecordOrder.DESC
        else ep_map
    )
    update_progress(
        progress,
        bounds.max_pct,
        f"Finished scanning {season_count} season(s) for '{show.slug}'.",
    )
    return ep_map_final, current_values


def fetch_all_episodes_paginated(
    client: MiddlewareClient,
    show_slug: str,
    by: ByShowSeason,
) -> List[DwEpisodeRecord]:
    """Fetch one entire Daily Wire season, following nextPageUrl until absent."""
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
