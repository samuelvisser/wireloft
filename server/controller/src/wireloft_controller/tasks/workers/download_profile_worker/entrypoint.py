from __future__ import annotations

from typing import Optional

from backend.app import db_session
from wireloft_scheduler.registry import task
from .service import run_download_profile_worker


@task(
    key="download_profile_worker",
    title="Implement Download Profiles",
    description="This worker makes sure download profiles actually work by downloading the episodes they request",
    allowed_resource_types=("download_profile",),
    default_max_retries=5,
    tracks_progress=True,
)
async def download_profile_worker(*, resource_id: Optional[int] = None, slug: Optional[str] = None, progress=None) -> None:
    """
    Downloads the episodes of a download profile.
    """
    with db_session() as s:
        await run_download_profile_worker(s, resource_id=resource_id, show_slug=slug, progress=progress)