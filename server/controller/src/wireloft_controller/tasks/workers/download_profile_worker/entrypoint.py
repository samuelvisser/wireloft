from __future__ import annotations

from typing import Optional

from backend.app import db_session
from wireloft_motherboard.scheduler.registry import task, on_cron, on_event
from .service import run_download_profile_worker


@task(
    key="download_profile_worker",
    title="Implement Download Profiles",
    description="This worker makes sure download profiles actually work by downloading the episodes they request",
    allowed_resource_types=("download_profile",),
    default_max_retries=5,
    tracks_progress=True,
)
@on_cron(
    cron="settings:download_settings.verify_downloads_interval_min",  # Interval in minutes from settings
    resource_type="download_profile",
    resource_id=0,  # 0 = all download profiles
    coalesce=True,
    run_on_startup=True,
)
@on_event(
    event_name="episode.published_countdown",
    resource_type="episode",
)
@on_event(
    event_name="episode.published",
    resource_type="episode",
)
@on_event(
    event_name="show.added",
    resource_type="show",
)
async def download_profile_worker(*, resource_id: Optional[int] = None, slug: Optional[str] = None, progress=None) -> None:
    """
    Downloads the episodes of a download profile.
    """
    with db_session() as s:
        await run_download_profile_worker(s, resource_id=resource_id, show_slug=slug, progress=progress)