from asyncio.log import logger
from itertools import dropwhile, islice
from typing import Optional, Sequence
from sqlalchemy.orm import Session
from sqlalchemy import select

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


async def run_fetch_new_episodes(s: Session, *, show_id: Optional[int] = None, show_slug: Optional[str] = None, dry_run: bool = False, progress=None) -> None:
    print("Starting fetch_new_episodes" + (" (dry run: nothing will be saved)" if dry_run else ""))

    shows: Sequence[Show] = get_shows(s, show_id=show_id, show_slug=show_slug)

    # Get the desired membership level and access token
    access_token: Optional[str] = None
    tokens = DeviceAuthClient().get_token()
    if tokens:
        access_token = tokens.access_token
    client = MiddlewareClient(access_token=access_token)

    for show in shows:
        # Get the membership plan
        membership_plan: str = show.membership_level

        if membership_plan != WlDwMembershipLevel.FREE.value and access_token is None:
            if membership_plan != WlDwMembershipLevel.WL_ANY.value:
                logger.warning(f"No valid access token in token store for show {show.slug}: required for membership level {show.membership_level}")
                continue
        if membership_plan == WlDwMembershipLevel.WL_ANY.value:
            membership_plan = WlDwMembershipLevel.FREE.value

        # Get the last episode that is fully published
        stmt = (
            select(Episode)
            .where(Episode.show_id == show.id)
            .where(Episode.publish_status == EpisodePublishStatus.PUBLISHED_FINAL.value)
            .order_by(Episode.index.desc())
            .limit(1)
        )
        latest_final_episode: Optional[Episode] = s.execute(stmt).scalar_one_or_none()

        # Fetch remote seasons
        last_known_season: Optional[Season] = latest_final_episode.season if latest_final_episode is not None else None
        dw_show = client.get_show_page(show.slug, membership_plan=membership_plan)
        all_dw_seasons: list[DwSeasonRecord] = dw_show.seasons

        if last_known_season is not None:
            relevant_dw_seasons = list(dropwhile(lambda season: season.slug != latest_final_episode.season.slug, all_dw_seasons))
            new_dw_seasons: list[DwSeasonRecord] = list(islice(relevant_dw_seasons, 1, None))
        else:
            new_dw_seasons = all_dw_seasons

        # Add any new seasons to the db
        for new_dw_season in new_dw_seasons:
            if not any(season.slug == new_dw_season.slug for season in show.seasons):
                create_season_by_dw_season(s, show=show, dw_season=new_dw_season)
                s.flush()
                s.refresh(show, attribute_names=['seasons'])
        if not dry_run:
            s.commit()

        # Get prev max values
        prev_max_values: IdentifierMaxValues = {
            m.key: int(m.value)
            for m in show.meta_items if m.key.startswith("ep_id")
        }

        # Progress bounds
        seasons = show.seasons
        x = max(1, min(int(len(seasons)), 5))
        upper = int(65 + (x - 1) * (95 - 65) / (5 - 1))

        # Build slug→dw_id mapping from fresh API data
        dw_id_by_slug = {s.slug: s.dw_id for s in all_dw_seasons}

        # Find new episodes
        ep_map_asc, identifier_max_values = get_dw_episodes_since_ep(client,
                                                                     show=show,
                                                                     membership_plan=membership_plan,
                                                                     seasons=show.seasons,
                                                                     dw_id_by_slug=dw_id_by_slug,
                                                                     since_episode=latest_final_episode,
                                                                     prev_max_values=prev_max_values,
                                                                     progress=progress,
                                                                     progress_bounds=ProgressBounds(1, upper),
                                                                     order=RecordOrder.ASC)

        # Dry run: report what would happen and discard every in-session change
        # (the freshly created seasons included), persisting nothing.
        if dry_run:
            _print_dry_run_report(show, ep_map_asc, identifier_max_values)
            s.rollback()
            update_progress(progress, 100, f"Dry run complete for '{show.slug}' (nothing saved)")
            continue

        # Save identifier max values
        for k, v in identifier_max_values.items():
            show.set_meta(key=k, value=str(v))
            s.flush()

        # Count total episodes
        total = count_total_episodes(ep_map_asc)
        upper = upper + 1
        if total == 0:
            _queue_monitor_requests(s, monitor_requests.values())
            s.commit()
            update_progress(
                progress,
                100,
                _completion_message(0, len(monitor_requests)),
            )
            continue
        update_progress(progress, upper, f"Found {total} episodes in '{show.slug}'")


        # Save new episodes to db
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
                    episodes=ep_map_asc[season_id],
                    start_index=current_index,
                    client=client,
                    require_member_exclusive=require_member_exclusive,
                )
            except Exception as e:
                # rollback of the season has already occurred inside save_dw_episodes_per_season
                # Re raise to allow scheduler to retry; caller expects retry to be scheduled
                print(f"Exception: {e}")
                raise e

            # Announce the episodes whose status was resolved from the detail endpoint
            # (the live/recent ones) and keep monitoring any that are still non-final.
            _announce_new_episodes(s, show=show, saved_episodes=saved_episodes, monitor_requests=monitor_requests)

            # Update progress roughly based on completed seasons
            processed = current_index - 1
            frac = max(0.0, min(1.0, processed / total)) if total > 0 else 1.0
            scaled_pct = upper + min(99 - upper + 1, int(frac * (99 - upper)))
            update_progress(progress, scaled_pct,f"Indexed {processed}/{total} episodes (season {season.index}: {season.name})")

        _queue_monitor_requests(s, monitor_requests.values())
        s.commit()
        update_progress(progress, 100, _completion_message(total, len(monitor_requests)))

    print("fetch_new_episodes finished")


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
    for k, v in sorted(identifier_max_values.items()):
        print(f"  {k} = {v}")
    print("=== END DRY RUN ===\n")
