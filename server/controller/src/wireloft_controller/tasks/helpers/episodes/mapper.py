from __future__ import annotations

from wireloft_controller.tasks.types.general import RecordOrder

type EpisodeWithIdentifier = Tuple[str, DwEpisodeRecord]
type EpisodeMapTuple = OrderedDict[int, List[EpisodeWithIdentifier]]
type SinceEpisodeTuple = Tuple[IdentifierMaxValues, Episode]

from typing import Tuple, Optional, Sequence, List, Any, OrderedDict

from backend.db.models import Show, Episode, Season
from backend.types.show_types import EpisodeIdentifier
from dailywire_api.dw_api.client import MiddlewareClient, ByShowSeason, ByNextPage
from dailywire_api.records import DwEpisodeRecord
from wireloft_controller.tasks.helpers.episodes.identifier import IdentifierMaxValues, identify_episodes_in_season
from wireloft_controller.tasks.helpers.progress import update_progress, ProgressBounds, CollectionListProgressTracker


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
                         bounds=progress_bounds,
                         progress=progress,
                         order=order)


def get_dw_episodes_since_ep(client: MiddlewareClient, *,
                             show: Show,
                             membership_plan: str,
                             seasons: Sequence[Season],
                             since_episode: Episode,
                             prev_max_values: IdentifierMaxValues,
                             progress: Optional[Any] = None,
                             progress_bounds: ProgressBounds = ProgressBounds(1, 100),
                             order: RecordOrder) -> Tuple[EpisodeMapTuple, IdentifierMaxValues]:
    """
    Fetch episodes strictly *after* the given final episode, across *all* remote seasons that follow it.

    Returns a mapping in descending order
    """
    index = next((i for i, s in enumerate(seasons) if s.dw_id == since_episode.season.dw_id), -1) + 1
    seasons_to_scan = seasons[: index]

    return _scan_seasons(client,
                         show=show,
                         membership_plan=membership_plan,
                         seasons=seasons_to_scan,
                         since_episode_tuple=(prev_max_values, since_episode),
                         bounds=progress_bounds,
                         progress=progress,
                         order=order)


def _scan_seasons(client: MiddlewareClient, *,
                  show: Show,
                  membership_plan: str,
                  seasons: Sequence[Season],
                  since_episode_tuple: Optional[SinceEpisodeTuple] = None,
                  bounds: ProgressBounds,
                  progress: Optional[Any],
                  order: RecordOrder) -> Tuple[EpisodeMapTuple, IdentifierMaxValues]:
    """
    Core scanner.
    """
    ep_map: EpisodeMapTuple = OrderedDict()
    current_values: IdentifierMaxValues = since_episode_tuple[0] if since_episode_tuple is not None else {}
    identifiers: set[str] = set()

    seasons_asc = sorted(seasons, key=lambda s: s.index)
    season_count = len(seasons_asc)

    update_progress(progress, bounds.min_pct, f"Scanning episodes for '{show.slug}'...")

    tracker = CollectionListProgressTracker(progress_sink=progress, bounds=bounds, collection_count=season_count)

    for idx, season in enumerate(seasons_asc):
        # Fetch all episodes for this season
        eps = __fetch_all_episodes_paginated(client, show.slug, ByShowSeason(
            season_dw_id=season.dw_id,
            membership_plan=membership_plan,
            page_size=50,
            order_by="CreatedAt_ASC"
        ))
        eps = list(dict.fromkeys(eps))  # remove duplicates

        # Remove episodes before since episode
        if since_episode_tuple is not None:
            index = next((i for i, rec in enumerate(eps) if rec.dw_id == since_episode_tuple[1].dw_id), None)
            if index is not None:
                eps: list[DwEpisodeRecord] = eps[index + 1:]

        identifier: EpisodeIdentifier = EpisodeIdentifier(show.episode_identifier)
        eps_with_id, current_values, identifiers = identify_episodes_in_season(identifier, eps, current_values, identifiers)

        if len(eps_with_id) != len(eps):
            raise ValueError(f"Encountered non-unique episode numbered identifiers in season \"{season.name}\", aborting")

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
