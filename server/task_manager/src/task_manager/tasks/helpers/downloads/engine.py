from __future__ import annotations

import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from backend.types.local_media_profile_types import PreferredFormat
from config.settings.submodels import DownloadMode
from dailywire_downloader import (
    DownloadCancelled,
    DownloadError,
    DownloadProgress,
    DownloadResult,
    MediaKind,
    MediaUnavailableError,
    VideoRendition,
    download_file,
    download_hls,
    probe,
    remux_to_mp4,
)

from .download_files import remove_download_artifacts
from .download_paths import (
    TemporaryDownloadWorkspace,
    create_temporary_download_workspace,
    publish_temporary_download,
    reserve_unique_download_path,
)


FORMAT_HEIGHTS: dict[str, int] = {
    PreferredFormat.FORMAT_4K.value: 2160,
    PreferredFormat.FORMAT_1080P.value: 1080,
    PreferredFormat.FORMAT_720P.value: 720,
}


@dataclass(frozen=True)
class ResolvedDownloadSource:
    """A probed media source ready for transfer without further format decisions."""

    url: str
    format_downloaded: str
    use_hls: bool
    remux_to_mp4: bool
    extension: str


@dataclass(frozen=True)
class DownloadPlan:
    """Storage-independent instructions for producing one published artifact."""

    source: ResolvedDownloadSource
    requested_destination: str
    download_mode: DownloadMode
    temporary_root: str
    ffmpeg_path: str


@dataclass
class DownloadExecution:
    """Successful execution result plus temporary publication state to finalize."""

    result: DownloadResult
    source: ResolvedDownloadSource
    workspace: TemporaryDownloadWorkspace | None = None

    @property
    def format_downloaded(self) -> str:
        return self.source.format_downloaded

    def cleanup_workspace(self) -> None:
        if self.workspace is not None:
            self.workspace.cleanup()


class TaskProgressWriter:
    """Translate downloader progress into generic TaskRun reporting."""

    def __init__(self, task_progress=None):
        self._task_progress = task_progress
        self._last_pct = -1

    def set_selected_format(self, selected_format: str) -> None:
        if self._task_progress is None:
            return
        self._task_progress.set(
            max(0, self._last_pct),
            meta={"selected_format": selected_format},
        )

    def __call__(self, progress: DownloadProgress) -> None:
        fraction = progress.fraction
        if fraction is None:
            return
        pct = max(0, min(99, int(fraction * 100)))
        if pct == self._last_pct:
            return
        self._last_pct = pct
        if self._task_progress is not None:
            self._task_progress.set(pct)


def ensure_not_cancelled(cancellation) -> None:
    if cancellation is not None and callable(cancellation) and cancellation():
        raise DownloadCancelled("Download was canceled")


def select_rendition(
    renditions: Sequence[VideoRendition],
    requested_height: int,
) -> VideoRendition:
    """Pick the best available rendition without transcoding."""
    with_height = [rendition for rendition in renditions if rendition.height]
    if not with_height:
        raise MediaUnavailableError(
            "Master playlist offers no video renditions with a resolution"
        )

    at_least = [
        rendition for rendition in with_height if rendition.height >= requested_height
    ]
    if at_least:
        return min(
            at_least,
            key=lambda rendition: (
                rendition.height,
                -(rendition.bandwidth or 0),
            ),
        )
    return max(
        with_height,
        key=lambda rendition: (
            rendition.height,
            rendition.bandwidth or 0,
        ),
    )


def resolve_download_source(
    url: str,
    *,
    preferred_format: str,
    audio_only: bool,
    remux_video_to_mp4: bool,
    cancellation=None,
) -> ResolvedDownloadSource:
    """Probe a source and reduce it to the exact URL and format to download."""
    ensure_not_cancelled(cancellation)
    info = probe(url)
    ensure_not_cancelled(cancellation)

    if audio_only:
        if info.kind is MediaKind.HLS_MASTER:
            raise DownloadError("Audio URL unexpectedly returned an HLS master playlist")
        source_url = url
        format_downloaded = "audio"
        use_hls = info.kind is MediaKind.HLS_MEDIA
    elif info.kind is MediaKind.HLS_MASTER:
        requested_height = FORMAT_HEIGHTS.get(preferred_format)
        if requested_height is None:
            raise DownloadError(f"Unsupported preferred format '{preferred_format}'")
        rendition = select_rendition(info.renditions, requested_height)
        source_url = rendition.url
        format_downloaded = rendition.resolution or "video"
        use_hls = True
    elif info.kind is MediaKind.HLS_MEDIA:
        source_url = url
        format_downloaded = "video"
        use_hls = True
    else:
        source_url = url
        format_downloaded = "video"
        use_hls = False

    remux = not audio_only and use_hls and remux_video_to_mp4
    return ResolvedDownloadSource(
        url=source_url,
        format_downloaded=format_downloaded,
        use_hls=use_hls,
        remux_to_mp4=remux,
        extension="mp4" if remux else info.suggested_extension,
    )


def execute_download_plan(
    plan: DownloadPlan,
    *,
    task_progress: TaskProgressWriter,
    cancellation=None,
    on_direct_destination_reserved: Callable[[str], None] | None = None,
) -> DownloadExecution:
    """Execute one resolved download using the selected storage mode.

    Temporary-mode workspaces are returned on success so the caller can keep the
    crash-recovery marker until its artifact database transaction commits. Failed
    transfers clean up their own unpublished or partially published filesystem state.
    """
    task_progress.set_selected_format(plan.source.format_downloaded)
    ensure_not_cancelled(cancellation)

    if plan.download_mode is DownloadMode.TEMPORARY:
        return _execute_temporary_plan(
            plan,
            task_progress=task_progress,
            cancellation=cancellation,
        )
    return _execute_direct_plan(
        plan,
        task_progress=task_progress,
        cancellation=cancellation,
        on_destination_reserved=on_direct_destination_reserved,
    )


def _execute_temporary_plan(
    plan: DownloadPlan,
    *,
    task_progress: TaskProgressWriter,
    cancellation,
) -> DownloadExecution:
    workspace = create_temporary_download_workspace(
        plan.temporary_root,
        plan.requested_destination,
    )
    published_destination: str | None = None
    keep_workspace = False
    try:
        result = _perform_download(
            plan.source,
            str(workspace.path),
            ffmpeg_path=plan.ffmpeg_path,
            task_progress=task_progress,
            cancellation=cancellation,
        )
        ensure_not_cancelled(cancellation)
        destination = publish_temporary_download(
            workspace.path,
            plan.requested_destination,
        )
        published_destination = str(destination)
        keep_workspace = True
        return DownloadExecution(
            result=DownloadResult(
                path=published_destination,
                bytes_downloaded=result.bytes_downloaded,
                segments_downloaded=result.segments_downloaded,
            ),
            source=plan.source,
            workspace=workspace,
        )
    except BaseException:
        if published_destination is not None:
            remove_download_artifacts(published_destination)
        raise
    finally:
        if not keep_workspace:
            workspace.cleanup()


def _execute_direct_plan(
    plan: DownloadPlan,
    *,
    task_progress: TaskProgressWriter,
    cancellation,
    on_destination_reserved: Callable[[str], None] | None,
) -> DownloadExecution:
    reservation = reserve_unique_download_path(plan.requested_destination)
    destination = str(reservation.path)
    try:
        if on_destination_reserved is not None:
            on_destination_reserved(destination)
        result = _perform_download(
            plan.source,
            destination,
            ffmpeg_path=plan.ffmpeg_path,
            task_progress=task_progress,
            cancellation=cancellation,
        )
        return DownloadExecution(result=result, source=plan.source)
    except BaseException:
        remove_download_artifacts(destination)
        raise
    finally:
        reservation.release_if_unclaimed()


def _perform_download(
    source: ResolvedDownloadSource,
    destination: str,
    *,
    ffmpeg_path: str,
    task_progress: TaskProgressWriter,
    cancellation,
) -> DownloadResult:
    if source.remux_to_mp4:
        return _download_and_remux_to_mp4(
            source.url,
            destination,
            ffmpeg_path=ffmpeg_path,
            task_progress=task_progress,
            cancellation=cancellation,
        )
    if source.use_hls:
        return download_hls(
            source.url,
            destination,
            progress=task_progress,
            should_cancel=cancellation,
        )
    return download_file(
        source.url,
        destination,
        progress=task_progress,
        should_cancel=cancellation,
    )


def _download_and_remux_to_mp4(
    source_url: str,
    destination: str,
    *,
    ffmpeg_path: str,
    task_progress: TaskProgressWriter,
    cancellation,
) -> DownloadResult:
    raw_path = destination + ".rawts"
    try:
        downloaded = download_hls(
            source_url,
            raw_path,
            progress=task_progress,
            should_cancel=cancellation,
        )
        ensure_not_cancelled(cancellation)
        remux_to_mp4(
            raw_path,
            destination,
            ffmpeg_path=ffmpeg_path,
            should_cancel=cancellation,
        )
    finally:
        try:
            os.remove(raw_path)
        except OSError:
            pass

    return DownloadResult(
        path=destination,
        bytes_downloaded=downloaded.bytes_downloaded,
        segments_downloaded=downloaded.segments_downloaded,
    )
