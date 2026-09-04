from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, select

from backend.db.models import Episode, Show
from config import get_settings
from controller.db_utils import db_session
from task_manager.scheduler.registry import task, on_cron, on_event
from task_manager.scheduler.results import TaskResult
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
    tracks_progress=True,
)
async def fetch_new_episodes(
    *,
    resource_id: Optional[int] = None,
    slug: Optional[str] = None,
    dry_run: bool = False,
    progress=None,
) -> TaskResult:
    """Find new episodes and return structured facts about the completed scan."""
    with db_session() as s:
        tracked_shows = _get_tracked_shows(s, resource_id=resource_id, slug=slug)

        if dry_run:
            await run_fetch_new_episodes(
                s,
                show_id=resource_id,
                show_slug=slug,
                dry_run=True,
                progress=progress,
            )
            return TaskResult(
                summary="Dry-run episode scan completed",
                data={"shows_scanned": len(tracked_shows), "episodes_found": 0},
            )

        total_found = 0
        completed_shows: list[dict[str, object]] = []
        for tracked_show in tracked_shows:
            show_id = tracked_show.id
            before = _episode_count(s, show_id)
            try:
                await run_fetch_new_episodes(
                    s,
                    show_id=show_id,
                    dry_run=False,
                    progress=progress,
                )
            except Exception:
                s.rollback()
                show = s.get(Show, show_id)
                if show is not None:
                    _append_sync_log(
                        show,
                        synced_at=datetime.now(timezone.utc).isoformat(),
                        episodes_found=0,
                        status="failed",
                        will_retry=_will_retry(progress),
                    )
                    s.commit()
                raise

            after = _episode_count(s, show_id)
            found = max(0, after - before)
            total_found += found
            show = s.get(Show, show_id)
            if show is not None:
                _append_sync_log(
                    show,
                    synced_at=datetime.now(timezone.utc).isoformat(),
                    episodes_found=found,
                    status="completed",
                )
                completed_shows.append({
                    "show_id": show.id,
                    "show_slug": show.slug,
                    "show_title": show.title,
                    "episodes_found": found,
                })
                s.commit()

        if len(completed_shows) == 1:
            only = completed_shows[0]
            found = int(only["episodes_found"])
            summary = (
                f"Episode scan finished for {only['show_title']}: "
                f"{found} new {'episode' if found == 1 else 'episodes'} found"
            )
        else:
            summary = (
                f"Episode scan finished for {len(completed_shows)} shows: "
                f"{total_found} new {'episode' if total_found == 1 else 'episodes'} found"
            )

        return TaskResult(
            summary=summary,
            data={
                "episodes_found": total_found,
                "shows_scanned": len(completed_shows),
                "shows": completed_shows,
            },
        )


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
    if run is None:
        return False
    attempt_count = int(getattr(run, "attempt_count", 0) or 0)
    max_retries = int(getattr(run, "max_retries", 0) or 0)
    return attempt_count <= max_retries


def _append_sync_log(
    show: Show,
    *,
    synced_at: str,
    episodes_found: int,
    status: str,
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
    if will_retry is not None:
        entry["will_retry"] = will_retry

    history.insert(0, entry)
    show.set_meta(SYNC_LOG_META_KEY, json.dumps(history[:SYNC_LOG_LIMIT]))
