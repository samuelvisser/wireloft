from __future__ import annotations

from asyncio.log import logger
from dataclasses import dataclass
from typing import Any, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models import Episode, Season, Show
from backend.types.dailywire_user_info import WlDwMembershipLevel
from backend.types.episode_types import EpisodePublishStatus
from dailywire_api.dw_api.client import ByShowSeason, MiddlewareClient
from dailywire_api.records import DwEpisodeRecord, DwSeasonRecord
from dailywire_authorisation import DeviceAuthClient
from task_manager.events.transactional import queue_event
from ._helpers import get_latest_ep_index, get_season_from_list_by_id, get_shows
from ...helpers.episodes.events import queue_episode_status_events
from ...helpers.episodes.identifier import IdentifierMaxValues
from ...helpers.episodes.mapper import (
    count_total_episodes,
    fetch_all_episodes_paginated,
    get_dw_episodes_since_ep,
)
from ...helpers.episodes.quarantine import vacated_canonical_identifiers_for_show
from ...helpers.episodes.same_episode import (
    PENDING_EPISODE_STATUSES,
    reconcile_single_pending_episode_slug,
)
from ...helpers.episodes.save import (
    ResolvedEpisode,
    SavedEpisode,
    resolve_dw_episodes,
    save_resolved_episodes_per_season_asc,
)
from ...helpers.progress import ProgressBounds, update_progress
from ...helpers.seasons import create_season_by_dw_season
from ...types.general import RecordOrder
from ..monitor_pending_episode.scheduling import MONITOR_REQUESTED_EVENT


SHOW_INDEXED_EVENT = "show.indexed"


@dataclass(frozen=True)
class ShowEpisodeScanResult:
    show_id: int
    show_slug: str
    show_title: str
    episodes_found: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "show_id": self.show_id,
            "show_slug": self.show_slug,
            "show_title": self.show_title,
            "episodes_found": self.episodes_found,
        }


@dataclass(frozen=True)
class FetchNewEpisodesResult:
    shows: tuple[ShowEpisodeScanResult, ...]
    dry_run: bool = False

    @property
    def episodes_found(self) -> int:
        return sum(show.episodes_found for show in self.shows)

    @property
    def shows_scanned(self) -> int:
        return len(self.shows)

    def summary(self) -> str:
        if self.dry_run:
            return "Dry-run episode scan completed"
        if self.shows_scanned == 1:
            only = self.shows[0]
            return f"Episode scan finished for {only.show_title}: {only.episodes_found} new {'episode' if only.episodes_found == 1 else 'episodes'} found"
        return f"Episode scan finished for {self.shows_scanned} shows: {self.episodes_found} new {'episode' if self.episodes_found == 1 else 'episodes'} found"

    def as_data(self) -> dict[str, Any]:
        return {
            "episodes_found": self.episodes_found,
            "shows_scanned": self.shows_scanned,
            "shows": [show.as_dict() for show in self.shows],
        }


async def run_fetch_new_episodes(
    s: Session,
    *,
    show_id: Optional[int] = None,
    show_slug: Optional[str] = None,
    dry_run: bool = False,
    progress=None,
) -> FetchNewEpisodesResult:
    shows: Sequence[Show] = get_shows(s, show_id=show_id, show_slug=show_slug)
    show_ids = [show.id for show in shows]

    # Token refresh can itself require the internet. Do not retain the SELECT
    # transaction used to find the shows while waiting for OAuth/DNS/HTTP.
    s.rollback()
    tokens = DeviceAuthClient().get_token()
    access_token = tokens.access_token if tokens else None
    client = MiddlewareClient(access_token=access_token)
    completed: list[ShowEpisodeScanResult] = []
    for current_show_id in show_ids:
        show = s.get(Show, current_show_id)
        if show is None:
            continue
        try:
            found = await _fetch_show(
                s,
                show=show,
                client=client,
                access_token=access_token,
                dry_run=dry_run,
                progress=progress,
            )
        except Exception:
            s.rollback()
            raise
        completed.append(ShowEpisodeScanResult(
            show_id=show.id,
            show_slug=show.slug,
            show_title=show.title,
            episodes_found=0 if dry_run else found,
        ))
    return FetchNewEpisodesResult(shows=tuple(completed), dry_run=dry_run)


async def _fetch_show(
    s: Session,
    *,
    show: Show,
    client: MiddlewareClient,
    access_token: str | None,
    dry_run: bool,
    progress=None,
) -> int:
    show_id = show.id
    show_slug = show.slug
    membership_plan = show.membership_level
    if membership_plan != WlDwMembershipLevel.FREE.value and access_token is None:
        if membership_plan != WlDwMembershipLevel.WL_ANY.value:
            logger.warning("No valid access token for show %s", show_slug)
            return 0
    if membership_plan == WlDwMembershipLevel.WL_ANY.value:
        membership_plan = WlDwMembershipLevel.FREE.value
    require_member_exclusive = membership_plan != WlDwMembershipLevel.FREE.value

    latest_final_episode = s.execute(
        select(Episode)
        .where(
            Episode.show_id == show_id,
            Episode.publish_status == EpisodePublishStatus.PUBLISHED_FINAL.value,
        )
        .order_by(Episode.index.desc())
        .limit(1)
    ).scalar_one_or_none()
    latest_final_episode_id = latest_final_episode.id if latest_final_episode is not None else None

    monitor_requests: dict[int, dict] = {
        episode.id: _monitor_request_for_db_episode(show, episode)
        for episode in s.scalars(select(Episode).where(
            Episode.show_id == show_id,
            Episode.publish_status.in_(PENDING_EPISODE_STATUSES),
        ))
    }

    # The local snapshot is complete. Release its transaction before the first
    # Daily Wire request so an outage cannot pin a DB connection per worker.
    s.rollback()
    dw_show = client.get_show_page(show_slug, membership_plan=membership_plan)
    all_dw_seasons: list[DwSeasonRecord] = dw_show.seasons

    show = s.get(Show, show_id)
    if show is None:
        raise ValueError(f"Show {show_id} was removed while it was being indexed")
    for remote_season in all_dw_seasons:
        if not any(season.slug == remote_season.slug for season in show.seasons):
            create_season_by_dw_season(s, show=show, dw_season=remote_season)
            s.flush()
            s.refresh(show, attribute_names=["seasons"])
    if not dry_run:
        # Newly discovered seasons are independent local facts and must exist before
        # the network-only prefetch phase. Committing also releases the connection.
        s.commit()

    dw_id_by_slug = {season.slug: season.dw_id for season in all_dw_seasons}
    season_requests = [
        (season.id, season.slug, dw_id_by_slug.get(season.slug))
        for season in show.seasons
    ]
    if not dry_run:
        s.rollback()

    # Fetch complete remote season snapshots without touching the ORM. This is the
    # largest I/O phase of discovery and may span several requests per season.
    prefetched: dict[int, list[DwEpisodeRecord]] = {}
    for season_id, _season_slug, remote_id in season_requests:
        if remote_id is None:
            continue
        prefetched[season_id] = fetch_all_episodes_paginated(
            client,
            show_slug,
            ByShowSeason(
                season_dw_id=remote_id,
                membership_plan=membership_plan,
                page_size=50,
                order_by="CreatedAt_ASC",
            ),
        )

    if not dry_run:
        show = s.get(Show, show_id)
        if show is None:
            raise ValueError(f"Show {show_id} was removed while it was being indexed")
        latest_final_episode = (
            s.get(Episode, latest_final_episode_id)
            if latest_final_episode_id is not None
            else None
        )

    for season_id, records in prefetched.items():
        season = get_season_from_list_by_id(show.seasons, season_id)
        if season is None:
            continue
        if reconcile_single_pending_episode_slug(
            s,
            show=show,
            season=season,
            remote_records=records,
        ) is not None:
            # Refresh requests with the newly adopted slug while keeping immutable id identity.
            for episode in s.scalars(select(Episode).where(
                Episode.show_id == show_id,
                Episode.publish_status.in_(PENDING_EPISODE_STATUSES),
            )):
                monitor_requests[episode.id] = _monitor_request_for_db_episode(show, episode)

    known_episode_slugs = set(s.scalars(select(Episode.slug).where(Episode.show_id == show_id)))
    prev_max_values: IdentifierMaxValues = {
        item.key: int(item.value)
        for item in show.meta_items
        if item.key.startswith("ep_id")
    }
    season_count = max(1, min(len(show.seasons), 5))
    upper = int(65 + (season_count - 1) * (95 - 65) / 4) if season_count > 1 else 65

    ep_map_asc, identifier_max_values = get_dw_episodes_since_ep(
        client,
        show=show,
        membership_plan=membership_plan,
        seasons=show.seasons,
        dw_id_by_slug=dw_id_by_slug,
        since_episode=latest_final_episode,
        prev_max_values=prev_max_values,
        known_episode_slugs=known_episode_slugs,
        progress=progress,
        progress_bounds=ProgressBounds(1, upper),
        order=RecordOrder.ASC,
        prefetched_by_season=prefetched,
        vacated_identifiers=vacated_canonical_identifiers_for_show(s, show_id),
    )

    if dry_run:
        _print_dry_run_report(show, ep_map_asc, identifier_max_values)
        s.rollback()
        update_progress(progress, 100, f"Dry run complete for '{show_slug}' (nothing saved)")
        return 0

    total = count_total_episodes(ep_map_asc)
    if total == 0:
        for key, value in identifier_max_values.items():
            show.set_meta(key=key, value=str(value))
        _queue_monitor_requests(s, monitor_requests.values())
        _queue_show_indexed(s, show=show, indexed_count=0)
        s.commit()
        update_progress(progress, 100, _completion_message(0, len(monitor_requests)))
        return 0

    # Slug reconciliation is now complete. Persist it before resolving individual
    # episode details, then perform all remaining remote/HLS work with no DB
    # connection checked out.
    s.commit()
    always_resolve_details = latest_final_episode_id is not None
    resolved_by_season: dict[int, list[ResolvedEpisode]] = {}
    for season_id, ep_list in ep_map_asc.items():
        resolved_by_season[season_id] = resolve_dw_episodes(
            episodes=ep_list,
            client=client,
            require_member_exclusive=require_member_exclusive,
            always_resolve_details=always_resolve_details,
        )

    show = s.get(Show, show_id)
    if show is None:
        raise ValueError(f"Show {show_id} was removed while it was being indexed")
    for key, value in identifier_max_values.items():
        show.set_meta(key=key, value=str(value))

    latest_episode_index = get_latest_ep_index(s, show=show) or 0
    current_index = latest_episode_index + 1
    for season_id, resolved_episodes in resolved_by_season.items():
        season = get_season_from_list_by_id(show.seasons, season_id)
        if season is None:
            continue
        current_index, saved_episodes = save_resolved_episodes_per_season_asc(
            s,
            show=show,
            season=season,
            episodes=resolved_episodes,
            start_index=current_index,
        )
        _announce_new_episodes(
            s,
            show=show,
            saved_episodes=saved_episodes,
            monitor_requests=monitor_requests,
        )

    _queue_monitor_requests(s, monitor_requests.values())
    _queue_show_indexed(s, show=show, indexed_count=total)
    s.commit()
    update_progress(progress, 100, _completion_message(total, len(monitor_requests)))
    return total


def _announce_new_episodes(
    s: Session,
    *,
    show: Show,
    saved_episodes: list[SavedEpisode],
    monitor_requests: dict[int, dict],
) -> None:
    for saved in saved_episodes:
        if not saved.detail_resolved:
            continue
        queue_episode_status_events(
            s,
            episode=saved.episode,
            show=show,
            old_status=None,
            new_status=saved.status,
            was_created=True,
        )
        if saved.status.value in PENDING_EPISODE_STATUSES:
            monitor_requests[saved.episode.id] = _monitor_request_for_db_episode(show, saved.episode)


def _monitor_request_for_db_episode(show: Show, episode: Episode) -> dict:
    return {
        "resource_id": episode.id,
        "slug": episode.slug,
        "show_id": show.id,
        "show_slug": show.slug,
        "season_id": episode.season_id,
        "episode_identifier": episode.episode_identifier,
        "episode_index": episode.index,
        "status": episode.publish_status,
    }


def _queue_monitor_requests(s: Session, requests) -> None:
    for request in requests:
        queue_event(s, MONITOR_REQUESTED_EVENT, request)


def _queue_show_indexed(s: Session, *, show: Show, indexed_count: int) -> None:
    queue_event(s, SHOW_INDEXED_EVENT, {
        "resource_id": show.id,
        "id": show.id,
        "slug": show.slug,
        "indexed_count": indexed_count,
    })


def _completion_message(indexed_count: int, monitor_count: int) -> str:
    if monitor_count:
        return f"Indexed {indexed_count} episode(s); ensured {monitor_count} pending episode monitor(s)"
    return f"Indexed {indexed_count} episode(s); no pending episodes found"


def _print_dry_run_report(show: Show, ep_map_asc, identifier_max_values: IdentifierMaxValues) -> None:
    total = count_total_episodes(ep_map_asc)
    print(f"\n=== DRY RUN: '{show.slug}' — {total} new episode(s), nothing saved ===")
    for season_id, ep_list in ep_map_asc.items():
        season = get_season_from_list_by_id(show.seasons, season_id)
        season_label = f"season {season.index}: {season.name}" if season is not None else f"season id {season_id}"
        for ep_id, ep in ep_list:
            print(f"  [{season_label}] {ep_id:<32} {ep.title}")
    print("Resulting identifier_max_values:")
    for key, value in sorted(identifier_max_values.items()):
        print(f"  {key} = {value}")
