from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

import requests

from backend.db.models import SeriesDownloadProfile
from task_manager.scheduler.registry import task
from ._helpers import ensure_dir_from_template, pick_thumbnail_url


@task(
    key="download_series_thumbnail",
    title="Download series thumbnail",
    description="Downloads a series thumbnail image to the media profile output directory for the given download profile.",
    allowed_resource_types=("download_profile_series",),
    default_max_retries=5,
    tracks_progress=False,
)
async def run_download_series_thumbnail(s: Session, *, resource_id: int, progress):  # progress provided by executor
    """Given a DownloadProfileSeries id, download the show's thumbnail into the media output dir.

    The saved file will be named 'series_thumbnail.jpg' in the target directory.
    """
    dps: Optional[SeriesDownloadProfile] = s.get(SeriesDownloadProfile, resource_id)
    if dps is None:
        raise ValueError(f"DownloadProfileSeries id={resource_id} not found")

    # Resolve target directory from media profile template
    target_dir = ensure_dir_from_template(dps.local_media_profile.output_template)
    show = dps.show
    url = pick_thumbnail_url(show)
    if not url:
        raise ValueError(f"Show id={show.id} has no thumbnail path set")

    # Require absolute URL to download
    if not (url.startswith("http://") or url.startswith("https://")):
        raise ValueError(f"Thumbnail path for show id={show.id} is not an absolute URL: {url}")

    # Download
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()

    # Determine extension if possible
    ext = ".jpg"
    ct = resp.headers.get("Content-Type", "").lower()
    if "png" in ct:
        ext = ".png"
    elif "jpeg" in ct or "jpg" in ct:
        ext = ".jpg"
    fname = target_dir / f"series_thumbnail{ext}"
    with open(fname, "wb") as f:
        f.write(resp.content)
