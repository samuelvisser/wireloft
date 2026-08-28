from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models import Episode, Show
from backend.types.dailywire_user_info import WlDwMembershipLevel
from dailywire_api.dw_api.client import MiddlewareAPIError, MiddlewareClient
from dailywire_authorisation import DeviceAuthClient
from task_manager.events.transactional import queue_event
from task_manager.tasks.helpers.progress import update_progress

logger = logging.getLogger(__name__)


async def run_check_no_show_today_episodes(
        s: Session, *, show_id: Optional[int] = None, show_slug: Optional[str] = None, progress=None
) -> None:
    """Delete a "No Show Today" placeholder once Daily Wire has removed it.

    Unlike a real episode (kept locally even after Daily Wire pulls it, in
    case that's worth investigating), a "No Show Today" entry has no content
    of its own: once its own episode-details endpoint no longer knows about
    it, there is nothing left worth keeping a local record of.
    """
    stmt = select(Episode).where(Episode.is_no_show_today.is_(True))
    if show_id is not None:
        stmt = stmt.where(Episode.show_id == show_id)
    elif show_slug is not None:
        stmt = stmt.where(Episode.show.has(slug=show_slug))
    candidates: list[Episode] = list(s.execute(stmt).scalars())

    if not candidates:
        update_progress(progress, 100, "No 'No Show Today' episodes to check")
        print("check_no_show_today_episodes completed: nothing to check")
        return

    access_token: Optional[str] = None
    tokens = DeviceAuthClient().get_token()
    if tokens:
        access_token = tokens.access_token
    client = MiddlewareClient(access_token=access_token)

    total = len(candidates)
    checked = 0
    removed = 0
    for episode in candidates:
        show: Show = episode.show
        membership_plan = show.membership_level

        if membership_plan != WlDwMembershipLevel.FREE.value and access_token is None:
            if membership_plan != WlDwMembershipLevel.WL_ANY.value:
                logger.warning(
                    "No valid access token in token store for show %s: required for membership level %s",
                    show.slug, membership_plan,
                )
                checked += 1
                continue

        require_member_exclusive = membership_plan not in (
            WlDwMembershipLevel.FREE.value, WlDwMembershipLevel.WL_ANY.value,
        )

        try:
            client.get_episode_details(episode.slug, require_member_exclusive=require_member_exclusive)
        except MiddlewareAPIError as e:
            if e.status_code == 404:
                queue_event(s, "episode.deleted", {
                    "resource_id": episode.id,
                    "id": episode.id,
                    "slug": episode.slug,
                    "show_id": episode.show_id,
                })
                s.delete(episode)
                s.commit()
                removed += 1
            else:
                logger.warning("Could not check 'No Show Today' episode '%s': %s", episode.slug, e)

        checked += 1
        update_progress(
            progress,
            int(checked / total * 100),
            f"Checked {checked}/{total} 'No Show Today' episode(s); removed {removed}",
        )

    message = f"Checked {checked} 'No Show Today' episode(s); removed {removed}"
    update_progress(progress, 100, message)
    print(f"check_no_show_today_episodes completed: {message}")
