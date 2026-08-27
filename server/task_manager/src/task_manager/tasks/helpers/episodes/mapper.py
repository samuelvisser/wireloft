from __future__ import annotations

from task_manager.tasks.types.general import RecordOrder

type EpisodeMapTuple = OrderedDict[int, List[EpisodeWithIdentifier]]

from typing import Tuple, Optional, Sequence, List, Any, OrderedDict

from backend.db.models import Show, Episode, Season
from backend.types.show_types import EpisodeIdentifier
from dailywire_api.dw_api.client import MiddlewareClient, ByShowSeason, ByNextPage
from dailywire_api.records import DwEpisodeRecord
from task_manager.tasks.helpers.episodes.identifier import EpisodeWithIdentifier, IdentifierMaxValues, identify_episodes_in_season
from task_manager.tasks.helpers.progress import update_progress, ProgressBounds, CollectionListProgressTracker


def count_total_episodes(episodes_map: EpisodeMapTuple) -> int:
    """
    Count all episodes by counting the items in the map.
    """
    count = 0
    for _, eps in episodes_map.items():
        count += len(eps)

    return count


def get_dw_episodes_by_seasons(client: MiddlewareClient, *,
                               show: Show,
                               membership_plan: str,
                               seasons: Sequence[Season],
                               dw_id_by_slug: dict[str, str],
                               progress: Optional[Any] = None,
                               progress_bounds: ProgressBounds = ProgressBounds(1, 100),
                               order: RecordOrder) -> Tuple[EpisodeMapTuple, IdentifierMaxValues]:
    """
    Fetch all episodes for the given *local* seasons.

    Returns a mapping in descending order
    """
    return _scan_seasons(client,
                         show=show,
                         membership_plan=membership_plan,
                         seasons=seasons,
                         dw_id_by_slug=dw_id_by_slug,
                         bounds=progress_bounds,
                         progress=progress,
                         order=order)


def get_dw_episodes_since_ep(client: MiddlewareClient, *,
                             show: Show,
                             membership_plan: str,
                             seasons: Sequence[Season],
                             dw_id_by_slug: dict[str, str],
                             since_episode: Optional[Episode],
                             prev_max_values: IdentifierMaxValues,
                             known_episode_slugs: Optional[set[str]] = None,
                             progress: Optional[Any] = None,
                             progress_bounds: ProgressBounds = ProgressBounds(1, 100),
                             order: RecordOrder) -> Tuple[EpisodeMapTuple, IdentifierMaxValues]:
    """
    Fetch episodes strictly *after* the given final episode, across *all* remote seasons that follow it.

    ``known_episode_slugs`` holds the slugs of episodes that are already indexed in the
    database. Those are excluded from the result so an already-identified episode is
    never assigned a fresh identifier (which, with the identifier max values already
    advanced past it, would wrongly re-identify it as auxiliary content).

    Returns a mapping in descending order
    """
    if since_episode is not None:
        index = next((i for i, s in enumerate(seasons) if s.slug == since_episode.season.slug), -1) + 1
        seasons_to_scan = seasons[: index]
    else:
        seasons_to_scan = seasons

    return _scan_seasons(client,
                         show=show,
                         membership_plan=membership_plan,
                         seasons=seasons_to_scan,
                         dw_id_by_slug=dw_id_by_slug,
                         since_episode=since_episode,
                         prev_max_values=prev_max_values,
                         known_episode_slugs=known_episode_slugs,
                         bounds=progress_bounds,
                         progress=progress,
                         order=order)


def _scan_seasons(client: MiddlewareClient, *,
                  show: Show,
                  membership_plan: str,
                  seasons: Sequence[Season],
                  dw_id_by_slug: dict[str, str],
                  since_episode: Optional[Episode] = None,
                  prev_max_values: Optional[IdentifierMaxValues] = None,
                  known_episode_slugs: Optional[set[str]] = None,
                  bounds: ProgressBounds,
                  progress: Optional[Any],
                  order: RecordOrder) -> Tuple[EpisodeMapTuple, IdentifierMaxValues]:
    """
    Core scanner.
    """
    ep_map: EpisodeMapTuple = OrderedDict()
    current_values: IdentifierMaxValues = dict(prev_max_values) if prev_max_values else {}
    known_episode_slugs = known_episode_slugs or set()

    seasons_asc = sorted(seasons, key=lambda s: s.index)
    season_count = len(seasons_asc)

    update_progress(progress, bounds.min_pct, f"Scanning episodes for '{show.slug}'...")

    tracker = CollectionListProgressTracker(progress_sink=progress, bounds=bounds, collection_count=season_count)

    for idx, season in enumerate(seasons_asc):
        # Fetch all episodes for this season
        eps = __fetch_all_episodes_paginated(client, show.slug, ByShowSeason(
            season_dw_id=dw_id_by_slug[season.slug],
            membership_plan=membership_plan,
            page_size=50,
            order_by="CreatedAt_ASC"
        ))
        eps = list(dict.fromkeys(eps))  # remove duplicates

        # The API doesn't reliably honor CreatedAt_ASC, so enforce oldest -> newest ourselves.
        eps.sort(key=lambda rec: (rec.published_date, rec.ep_number or 0, rec.ep_segment))

        # Remove episodes before since episode
        if since_episode is not None:
            index = next((i for i, rec in enumerate(eps) if rec.slug == since_episode.slug), None)
            if index is not None:
                eps: list[DwEpisodeRecord] = eps[index + 1:]

        # Episodes already indexed in the database keep the identifier they were
        # given back then; re-identifying them here (with the max values already
        # advanced past them) would wrongly classify them as auxiliary content.
        if known_episode_slugs:
            eps = [rec for rec in eps if rec.slug not in known_episode_slugs]

        identifier: EpisodeIdentifier = EpisodeIdentifier(show.episode_identifier)
        eps_with_id, current_values = identify_episodes_in_season(identifier, eps, current_values, season=season)

        if order == RecordOrder.DESC:
            eps_with_id.reverse()
        ep_map[season.id] = eps_with_id

        # progress accounting and user-facing message
        tracker.record_collection_actual(idx, len(eps))
        tracker.update(f"Mapped {sum(tracker.actual)} episodes so far (season {season.index}: {season.name})")

    if order == RecordOrder.DESC:
        ep_map_final = OrderedDict(reversed(list(ep_map.items())))
    else:
        ep_map_final = ep_map

    # Ensure we land at the top bound if any work was done.
    update_progress(progress, bounds.max_pct, f"Finished scanning {season_count} season(s) for '{show.slug}'.")

    return ep_map_final, current_values


def __fetch_all_episodes_paginated(
        client: MiddlewareClient,
        show_slug: str,
        by: ByShowSeason,
) -> List[DwEpisodeRecord]:
    """Straight-line pagination loop with no early returns."""
    items, next_page_url, has_next = client.get_episodes_paginated(show_slug, by)

    all_items: List[DwEpisodeRecord] = list(items) if items else []

    # When has_next is True, we must follow next_page_url until exhausted
    while has_next and next_page_url:
        items, next_page_url, has_next = client.get_episodes_paginated(show_slug, ByNextPage(next_page_url=next_page_url))
        if items:
            all_items.extend(items)

    return all_items
