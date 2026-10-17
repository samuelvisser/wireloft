"""Argument-based interface for complete downloads from already-resolved URLs.

URL discovery, format selection, destination naming and metadata preparation
belong to the caller. This module only transfers, processes and publishes files.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from tempfile import gettempdir
from typing import Literal

from .capacity import DownloadResources, resources as default_resources
from .coordinator import DownloadExecution, execute_download_plan
from .lifecycle import DownloadSnapshot, DownloadTracker
from .plan import ResolvedDownloadSource, SidecarSpec, build_download_plan

Transfer = Literal["file", "hls", "hls_bundle"]
StorageMode = Literal["direct", "temporary"]


def download_media(
    url: str,
    destination: str | Path,
    *,
    transfer: Transfer = "file",
    format_label: str | None = None,
    extension: str | None = None,
    download_mode: StorageMode = "temporary",
    temporary_root: str | Path | None = None,
    ffmpeg_path: str = "ffmpeg",
    audio_only: bool = False,
    remux_to_mp4: bool = False,
    convert_video_to_m4a: bool = False,
    expected_bytes: int | None = None,
    sidecars: tuple[SidecarSpec, ...] = (),
    hls_renditions: tuple[tuple[int, str], ...] = (),
    metadata_tags: Mapping[str, str] | tuple[tuple[str, str], ...] = (),
    artwork_asset_id: str | None = None,
    tracker: DownloadTracker | None = None,
    progress: Callable[[DownloadSnapshot], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
    resources: DownloadResources = default_resources,
    on_destination_reserved: Callable[[str], None] | None = None,
    on_media_transfer_complete: Callable[[], None] | None = None,
) -> DownloadExecution:
    """Execute one complete download using explicit, provider-independent options.

    No alternate URLs are discovered and no application state is accessed.
    Relative HLS segment references are fetched as part of transferring the
    supplied playlist. Remote sidecars and local post-processing are included.

    The result owns a recovery journal. The caller must call
    execution.cleanup_workspace() after persisting success, or
    execution.rollback() followed by cleanup_workspace() if persistence fails.

    An externally supplied tracker remains caller-owned, allowing application
    preparation stages to appear in the same operation history. For standalone
    use, omit it to have this function manage progress and cancellation.
    """
    if transfer not in ("file", "hls", "hls_bundle"):
        raise ValueError("Transfer must be file, hls or hls_bundle")
    if transfer == "hls_bundle":
        if not hls_renditions:
            raise ValueError("HLS bundle downloads require preselected rendition URLs")
        heights = [height for height, _url in hls_renditions]
        urls = [item for _height, item in hls_renditions]
        if (any(type(height) is not int or height <= 0 for height in heights)
                or len(set(heights)) != len(heights)
                or len(set(urls)) != len(urls)
                or any(not item.startswith(("https://", "http://")) for item in urls)):
            raise ValueError("HLS bundle rendition heights and HTTP(S) URLs must be unique and valid")
    elif hls_renditions:
        raise ValueError("HLS renditions only apply to bundle downloads")
    if not url.startswith(("https://", "http://")):
        raise ValueError("A resolved HTTP(S) media URL is required")
    destination = str(destination)
    output_extension = (extension or Path(destination).suffix.lstrip(".")).lower()
    if not output_extension or not output_extension.isalnum():
        raise ValueError("A valid output extension is required")
    if Path(destination).suffix.lower() != f".{output_extension.lower()}":
        raise ValueError("Output extension must match destination suffix")
    if tracker is not None and (progress is not None or should_cancel is not None):
        raise ValueError("Pass callbacks when constructing the supplied tracker")
    tags = tuple(metadata_tags.items()) if isinstance(metadata_tags, Mapping) else tuple(metadata_tags)
    source = ResolvedDownloadSource(
        url=url,
        format_downloaded=format_label or transfer,
        use_hls=transfer == "hls",
        remux_to_mp4=remux_to_mp4,
        extension=output_extension,
        audio_only=audio_only,
        hls_bundle=transfer == "hls_bundle",
        expected_bytes=expected_bytes,
        convert_video_to_m4a=convert_video_to_m4a,
        hls_renditions=tuple(hls_renditions),
    )
    owns_tracker = tracker is None
    if tracker is None:
        tracker = DownloadTracker(progress, should_cancel)
    plan = build_download_plan(
        source=source,
        requested_destination=destination,
        download_mode=download_mode,
        temporary_root=str(temporary_root) if temporary_root is not None else gettempdir(),
        ffmpeg_path=ffmpeg_path,
        assets=tuple(sidecars),
        metadata_tags=tags,
        artwork_asset_id=artwork_asset_id,
        attempt_id=tracker.attempt_id,
    )

    def execute() -> DownloadExecution:
        return execute_download_plan(
            plan, tracker=tracker, resources=resources,
            on_destination_reserved=on_destination_reserved,
            on_media_transfer_complete=on_media_transfer_complete,
        )

    if not owns_tracker:
        return execute()
    with tracker:
        execution = execute()
        try:
            tracker.finish()
        except BaseException:
            try:
                execution.rollback()
            finally:
                execution.cleanup_workspace()
            raise
        return execution
