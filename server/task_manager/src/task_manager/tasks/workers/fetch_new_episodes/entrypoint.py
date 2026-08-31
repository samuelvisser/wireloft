from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, select

from backend.db.models import Episode, Show
from config import get_settings
from controller.db_utils import db_session
from task_manager.scheduler.registry import task, on_cron, on_event
from .service import run_fetch_new_episodes


SYNC_LOG_META_KEY = "episode_sync_log"
SYNC_LOG_LIMIT = 10


@on_event(
    event_name="app.startup",
    resource_type="show",
)
@on_event(
    event_name="show.added",
    resource_type="show",
)
@on_event(
    event_name="show.sync_requested",
    resource_type="show",
)
@on_cron(
    cron=get_settings().new_episode_schedule.find_episodes_cron,
    resource_type="show",
    resource_id=0,
    coalesce=True,
)
@task(
    key="fetch_new_episodes",
    title="Find new episodes in all shows",
    description="Finds new episodes in all shows.",
    allowed_resource_types=("show",),
    default_max_retries=5,
    tracks_progress=False,
)
async def fetch_new_episodes(
    *,
    resource_id: Optional[int] = None,
    slug: Optional[str] = None,
    manual_request_id: Optional[str] = None,
    dry_run: bool = False,
    progress=None,
) -> None:
    """
    Finds new episodes in all shows.

    This worker searches for new episodes across all shows. It retrieves
    new episodes using the provided parameters and updates the database.

    Parameters:
    resource_id : Optional[int]
        The ID of a specific show if the task needs to focus on one.
    slug : Optional[str]
        The slug of a specific show if the task needs to focus on one.
    manual_request_id : Optional[str]
        Correlation ID set only when a user manually requested this sync.
    dry_run : bool
        When True, run the full detection flow but persist nothing to the
        database: computed episode identifiers are printed and all changes are
        rolled back. Intended for testing.
    progress : Any
        A progress tracker object.

    Raises:
        Any raised exceptions during the execution of the database session
        or async tasks.
    """
    with db_session() as s:
        tracked_shows = _get_tracked_shows(s, resource_id=resource_id, slug=slug)

        if dry_run:
            await run_fetch_new_episodes(s, show_id=resource_id, show_slug=slug, dry_run=True, progress=progress)
            return

        for tracked_show in tracked_shows:
            show_id = tracked_show.id
            before = _episode_count(s, show_id)
            try:
                await run_fetch_new_episodes(s, show_id=show_id, dry_run=False, progress=progress)
            except Exception:
                s.rollback()
                show = s.get(Show, show_id)
                if show is not None:
                    _append_sync_log(
                        show,
                        synced_at=datetime.now(timezone.utc).isoformat(),
                        episodes_found=0,
                        status="failed",
                        manual_request_id=manual_request_id,
                        will_retry=_will_retry(progress),
                    )
                    s.commit()
                raise

            after = _episode_count(s, show_id)
            show = s.get(Show, show_id)
            if show is not None:
                _append_sync_log(
                    show,
                    synced_at=datetime.now(timezone.utc).isoformat(),
                    episodes_found=max(0, after - before),
                    status="completed",
                    manual_request_id=manual_request_id,
                )
                s.commit()


def _get_tracked_shows(s, *, resource_id: Optional[int], slug: Optional[str]) -> list[Show]:
    if slug:
        show = s.execute(select(Show).where(Show.slug == slug)).scalar_one_or_none()
        return [show] if show is not None else []
    if resource_id not in (None, 0):
        show = s.get(Show, resource_id)
        return [show] if show is not None else []
    return list(s.execute(select(Show)).scalars().all())


def _episode_count(s, show_id: int) -> int:
    return int(
        s.execute(
            select(func.count(Episode.id)).where(Episode.show_id == show_id)
        ).scalar_one()
    )


def _will_retry(progress) -> bool:
    run = getattr(progress, "run", None)
    attempt_count = int(getattr(run, "attempt_count", 0) or 0)
    max_retries = int(getattr(run, "max_retries", 0) or 0)
    return attempt_count <= max_retries


def _append_sync_log(
    show: Show,
    *,
    synced_at: str,
    episodes_found: int,
    status: str,
    manual_request_id: Optional[str] = None,
    will_retry: Optional[bool] = None,
) -> None:
    raw = show.get_meta(SYNC_LOG_META_KEY)
    try:
        history = json.loads(raw) if raw else []
    except (TypeError, ValueError):
        history = []
    if not isinstance(history, list):
        history = []

    entry = {
        "synced_at": synced_at,
        "episodes_found": episodes_found,
        "status": status,
    }
    if manual_request_id is not None:
        entry["manual_request_id"] = manual_request_id
    if will_retry is not None:
        entry["will_retry"] = will_retry

    history.insert(0, entry)
    show.set_meta(SYNC_LOG_META_KEY, json.dumps(history[:SYNC_LOG_LIMIT]))
