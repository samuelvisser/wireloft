from __future__ import annotations

from typing import Optional

from wireloft_controller.app import db_session
from wireloft_controller.tasks.registry import task

from .service import run_index_show_worker


@task(
    key="index_show_worker",
    title="Index show episodes",
    description="Counts and indexes all episodes for a show, assigning descending episode indices (newest..oldest) and rolling back the current season on failure.",
    allowed_resource_types=("show",),
    default_max_retries=5,
    tracks_progress=True,
)
async def index_show_worker(*, resource_id: Optional[int] = None, show_slug: Optional[str] = None, progress=None) -> None:
    """
    Controller task that implements the multi-step indexing flow:
      1) Count total episodes via API.
      2) Load seasons from DB and sort by index desc.
      3) For each season, fetch episodes in pages of 10 (newest->oldest) and upsert
         into DB with a global descending index across the entire show.
      4) If any step fails within a season, rollback that season and re-raise to
         let the scheduler handle retries.
    """
    with db_session() as s:
        await run_index_show_worker(s, resource_id=resource_id, show_slug=show_slug, progress=progress)