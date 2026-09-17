from __future__ import annotations

from collections.abc import Callable

from fastapi import Path

from config.settings.submodels import ThumbnailMode
from task_manager.tasks.helpers.downloads import engine


def wants_thumbnail_embed(mode: ThumbnailMode) -> bool:
    return mode in {ThumbnailMode.EMBED, ThumbnailMode.EMBED_AND_SIDECAR}


def wants_thumbnail_sidecar(mode: ThumbnailMode) -> bool:
    return mode in {ThumbnailMode.SIDECAR, ThumbnailMode.EMBED_AND_SIDECAR}


def prepare_thumbnail(
    plan: engine.DownloadPlan,
    workspace: Path,
    *,
    cancellation,
    on_processing_started: Callable[[], None] | None = None,
) -> Path | None:
    from task_manager.tasks.helpers.downloads.engine import ensure_not_cancelled
    from dailywire_downloader import probe
    from dailywire_downloader import download_file

    if plan.thumbnail_mode is ThumbnailMode.NO_THUMBNAIL or not plan.thumbnail_url:
        return None

    if on_processing_started is not None:
        on_processing_started()

    ensure_not_cancelled(cancellation)
    info = probe(plan.thumbnail_url)
    extension = info.suggested_extension
    if extension not in {"jpg", "jpeg", "png", "webp"}:
        extension = "jpg"

    workspace.mkdir(parents=True, exist_ok=True)
    destination = workspace / f"thumbnail.{extension}"
    download_file(
        plan.thumbnail_url,
        str(destination),
        should_cancel=cancellation,
    )
    return destination


def select_thumbnail_url(media) -> str | None:
    """Choose the best artwork source for embedding or a per-media sidecar."""
    for attribute in (
        "thumbnail_square_path",
        "thumbnail_portrait_path",
        "thumbnail_landscape_path",
        "background_image_path",
    ):
        value = getattr(media, attribute, None)
        if isinstance(value, str) and value.startswith(("http://", "https://")):
            return value
    return None
