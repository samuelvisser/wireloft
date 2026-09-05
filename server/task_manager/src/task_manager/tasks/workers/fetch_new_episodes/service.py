from __future__ import annotations

from asyncio.log import logger
from dataclasses import dataclass
from typing import Any, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models import Show, Episode, Season
from backend.types.dailywire_user_info import WlDwMembershipLevel
from backend.types.episode_types import EpisodePublishStatus
from dailywire_api.dw_api.client import MiddlewareClient
from dailywire_api.records import DwSeasonRecord
from dailywire_authorisation import DeviceAuthClient
from task_manager.events.transactional import queue_event
from ._helpers import get_shows, get_season_from_list_by_id, get_latest_ep_index
from ...helpers.episodes.events import queue_episode_status_events
from ...helpers.episodes.identifier import IdentifierMaxValues
from ...helpers.episodes.mapper import get_dw_episodes_since_ep, count_total_episodes
from ...helpers.progress import ProgressBounds, update_progress
from ...helpers.seasons import create_season_by_dw_season
from ...helpers.episodes.save import save_dw_episodes_per_season_asc, SavedEpisode
from ...types.general import RecordOrder
from ..monitor_episode_worker.scheduling import MONITOR_REQUESTED_EVENT


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
            return (
                f"Episode scan finished for {only.show_title}: "
                f"{only.episodes_found} new "
                f"{'episode' if only.episodes_found == 1 else 'episodes'} found"
            )

        return (
            f"Episode scan finished for {self.shows_scanned} shows: "
            f"{self.episodes_found} new "
            f"{'episode' if self.episodes_found == 1 else 'episodes'} found"
        )

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
    """Find and persist new episodes for the selected shows."""
    print("Starting fetch_new_episodes" + (" (dry run: nothing will be saved)" if dry_run else ""))

    shows: Sequence[Show] = get_shows(s, show_id=show_id, show_slug=show_slug)

    access_token: Optional[str] = None
    tokens = DeviceAuthClient().get_token()
    if tokens:
        access_token = tokens.access_token
    client = MiddlewareClient(access_token=access_token)

    completed: list[ShowEpisodeScanResult] = []
    for show in shows:
        current_show_id = show.id
        current_show_slug = show.slug
        current_show_title = show.title

        try:
            episodes_found = await _fetch_show(
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
            show_id=current_show_id,
            show_slug=current_show_slug,
            show_title=current_show_title,
            episodes_found=0 if dry_run else episodes_found,
        ))

    print("fetch_new_episodes finished")
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
    """Run the complete episode discovery flow for one show and return the indexed count."""
    membership_plan: str = show.membership_level

    if membership_plan != WlDwMembershipLevel.FREE.value and access_token is None:
        if membership_plan != WlDwMembershipLevel.WL_ANY.value:
            logger.warning(
                f"No valid access token in token store for show {show.slug}: "
                f"required for membership level {show.membership_level}"
            )
            return 0
    if membership_plan == WlDwMembershipLevel.WL_ANY.value:
        membership_plan = WlDwMembershipLevel.FREE.value

    require_member_exclusive = membership_plan != WlDwMembershipLevel.FREE.value

    stmt = (
        select(Episode)
        .where(Episode.show_id == show.id)
        .where(Episode.publish_status == EpisodePublishStatus.PUBLISHED_FINAL.value)
        .order_by(Episode.index.desc())
        .limit(1)
    )
    latest_final_episode: Optional[Episode] = s.execute(stmt).scalar_one_or_none()

    known_episode_slugs: set[str] = set(
        s.execute(select(Episode.slug).where(Episode.show_id == show.id)).scalars()
    )

    non_final_stmt = (
        select(Episode)
        .where(Episode.show_id == show.id)
        .where(Episode.publish_status != EpisodePublishStatus.PUBLISHED_FINAL.value)
    )
    monitor_requests: dict[str, dict] = {
        ep.episode_identifier: _monitor_request_for_db_episode(show, ep)
        for ep in s.execute(non_final_stmt).scalars()
    }

    dw_show = client.get_show_page(show.slug, membership_plan=membership_plan)
    all_dw_seasons: list[DwSeasonRecord] = dw_show.seasons

    # Add newly discovered seasons in Daily Wire's returned order. Season ordering
    # normalization belongs to show creation/update, not this worker.
    for new_dw_season in all_dw_seasons:
        if not any(season.slug == new_dw_season.slug for season in show.seasons):
            create_season_by_dw_season(s, show=show, dw_season=new_dw_season)
            s.flush()
            s.refresh(show, attribute_names=["seasons"])
    if not dry_run:
        s.commit()

    prev_max_values: IdentifierMaxValues = {
        item.key: int(item.value)
        for item in show.meta_items
        if item.key.startswith("ep_id")
    }

    seasons = show.seasons
    x = max(1, min(int(len(seasons)), 5))
    upper = int(65 + (x - 1) * (95 - 65) / (5 - 1))

    dw_id_by_slug = {dw_season.slug: dw_season.dw_id for dw_season in all_dw_seasons}

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
    )

    if dry_run:
        _print_dry_run_report(show, ep_map_asc, identifier_max_values)
        s.rollback()
        update_progress(progress, 100, f"Dry run complete for '{show.slug}' (nothing saved)")
        return 0

    # Keep identifier metadata pending until the first episode write/commit. The
    # season saver resolves Daily Wire detail requests before that first flush, so
    # this worker never owns SQLite's writer lock while waiting on remote I/O.
    for key, value in identifier_max_values.items():
        show.set_meta(key=key, value=str(value))

    total = count_total_episodes(ep_map_asc)
    upper += 1
    if total == 0:
        _queue_monitor_requests(s, monitor_requests.values())
        _queue_show_indexed(s, show=show, indexed_count=0)
        s.commit()
        update_progress(
            progress,
            100,
            _completion_message(0, len(monitor_requests)),
        )
        return 0

    update_progress(progress, upper, f"Found {total} episodes in '{show.slug}'")

    latest_episode_index = get_latest_ep_index(s, show=show)
    if latest_episode_index is None:
        latest_episode_index = 0

    current_index = latest_episode_index + 1
    for season_id, ep_list in ep_map_asc.items():
        season: Optional[Season] = get_season_from_list_by_id(show.seasons, season_id)
        if season is None:
            logger.warning(f"No season found for show {show.slug} with id {season_id}")
            continue

        try:
            current_index, saved_episodes = save_dw_episodes_per_season_asc(
                s,
                show=show,
                season=season,
                episodes=ep_list,
                start_index=current_index,
                client=client,
                require_member_exclusive=require_member_exclusive,
            )
        except Exception as exc:
            # The season helper already rolled back its failed unit of work. Let
            # the task executor handle retry policy for the complete worker run.
            print(f"Exception: {exc}")
            raise

        _announce_new_episodes(
            s,
            show=show,
            saved_episodes=saved_episodes,
            monitor_requests=monitor_requests,
        )

        processed = current_index - 1 - latest_episode_index
        frac = max(0.0, min(1.0, processed / total)) if total > 0 else 1.0
        scaled_pct = upper + min(99 - upper + 1, int(frac * (99 - upper)))
        update_progress(
            progress,
            scaled_pct,
            f"Indexed {processed}/{total} episodes (season {season.index}: {season.name})",
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
    monitor_requests: dict,
) -> None:
    """Emit status-lifecycle events for freshly indexed live/recent episodes.

    Only episodes whose status was resolved from the detail endpoint are announced;
    the bulk final back catalog is saved silently, as before. Any episode that is
    still non-final is (re)scheduled for monitoring, now with a real ``resource_id``.
    """
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

        if saved.status is not EpisodePublishStatus.PUBLISHED_FINAL:
            monitor_requests[saved.episode.episode_identifier] = (
                _monitor_request_for_db_episode(show, saved.episode)
            )


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
    """Announce a completed index only after its database commit succeeds."""
    queue_event(s, SHOW_INDEXED_EVENT, {
        "resource_id": show.id,
        "id": show.id,
        "slug": show.slug,
        "indexed_count": indexed_count,
    })


def _completion_message(indexed_count: int, monitor_count: int) -> str:
    if monitor_count:
        return (
            f"Indexed {indexed_count} episode(s); "
            f"ensured {monitor_count} non-final episode monitor(s)"
        )
    return f"Indexed {indexed_count} episode(s); no non-final episodes found"


def _print_dry_run_report(show: Show, ep_map_asc, identifier_max_values: IdentifierMaxValues) -> None:
    """Print the episodes and identifiers a real run would have saved."""
    total = count_total_episodes(ep_map_asc)
    print(f"\n=== DRY RUN: '{show.slug}' — {total} new episode(s), nothing saved ===")
    for season_id, ep_list in ep_map_asc.items():
        season = get_season_from_list_by_id(show.seasons, season_id)
        season_label = f"season {season.index}: {season.name}" if season is not None else f"season id {season_id}"
        print(f"\n[{season_label}] {len(ep_list)} episode(s):")
        for ep_id, ep in ep_list:
            print(f"  {ep_id:<32} {ep.title}")
    print("\nResulting identifier_max_values (not saved):")
    for key, value in sorted(identifier_max_values.items()):
        print(f"  {key} = {value}")
    print("=== END DRY RUN ===\n")
