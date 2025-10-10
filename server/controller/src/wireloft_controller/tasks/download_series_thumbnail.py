from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import requests

from backend.db.core import get_session
from backend.db.models import DownloadProfileSeries
from ..registry import task


def _ensure_dir_from_template(output_template: str) -> Path:
    # The output_template ends with something like ".../file.ext"; take its directory
    p = Path(output_template)
    # If template contains placeholders, directory still resolves correctly
    dir_path = p.parent
    os.makedirs(dir_path, exist_ok=True)
    return dir_path


def _pick_thumbnail_url(show) -> Optional[str]:
    # Try in preference order
    for attr in ("thumbnail_landscape_path", "thumbnail_portrait_path", "thumbnail_square_path"):
        val = getattr(show, attr, None)
        if val:
            return val
    return None


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
    s = get_session()
    try:
        dps = s.get(DownloadProfileSeries, resource_id)
        if dps is None:
            raise ValueError(f"DownloadProfileSeries id={resource_id} not found")
        # Resolve target directory from media profile template
        target_dir = _ensure_dir_from_template(dps.media_profile.output_template)
        show = dps.show
        url = _pick_thumbnail_url(show)
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
    finally:
        s.close()
