from __future__ import annotations

from wireloft_controller.app import db_session
from wireloft_controller.tasks.registry import task
from .service import run_download_series_thumbnail


@task(
    key="download_series_thumbnail",
    title="Download series thumbnail",
    description="Downloads a series thumbnail image to the media profile output directory for the given download profile.",
    allowed_resource_types=("download_profile_series",),
    default_max_retries=5,
    tracks_progress=False,
)
async def download_series_thumbnail(*, resource_id: int, progress):  # progress provided by executor
    """Given a DownloadProfileSeries id, download the show's thumbnail into the media output dir.

    The saved file will be named 'series_thumbnail.jpg' in the target directory.
    """
    with db_session():
        await run_download_series_thumbnail(resource_id=resource_id, progress=progress)