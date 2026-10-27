from __future__ import annotations

from collections.abc import Sequence
from .downloader import probe
from .errors import DownloadCancelled, DownloadError, MediaUnavailableError
from .models import MediaKind, VideoRendition
from .plan import ResolvedDownloadSource

FORMAT_HEIGHTS = {"format_4k": 2160, "format_1080p": 1080, "format_720p": 720}


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
    video_fallback_for_audio: bool = False,
    cancellation=None,
) -> ResolvedDownloadSource:
    """Probe a source and reduce it to the exact URL and format to download."""
    ensure_not_cancelled(cancellation)
    info = probe(url)
    ensure_not_cancelled(cancellation)

    if video_fallback_for_audio and not audio_only:
        raise DownloadError("Video fallback can only be used for an audio-only download")

    if preferred_format == 'format_hls':
        if audio_only:
            raise DownloadError("HLS media format cannot be used for an audio-only download")
        if info.kind is not MediaKind.HLS_MASTER:
            raise DownloadError("HLS media format requires a master HLS source")
        return ResolvedDownloadSource(
            url=url,
            format_downloaded="HLS 480p/720p/1080p",
            use_hls=False,
            remux_to_mp4=False,
            extension="m3u8",
            audio_only=False,
            hls_bundle=True,
            subtitles=info.subtitles,
        )

    if audio_only:
        if info.kind is MediaKind.HLS_MASTER:
            if not video_fallback_for_audio:
                raise DownloadError("Audio URL unexpectedly returned an HLS master playlist")
            # An audio fallback only needs one playable video rendition. Use the
            # smallest available resolution to avoid downloading excess video
            # bytes that will be discarded during local processing.
            rendition = select_rendition(info.renditions, 1)
            source_url = rendition.url
            use_hls = True
        else:
            source_url = url
            use_hls = info.kind is MediaKind.HLS_MEDIA
        format_downloaded = "audio"
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
    convert_video_to_m4a = audio_only and video_fallback_for_audio
    return ResolvedDownloadSource(
        url=source_url,
        format_downloaded=format_downloaded,
        use_hls=use_hls,
        remux_to_mp4=remux,
        extension="m4a" if convert_video_to_m4a else "mp4" if remux else info.suggested_extension,
        audio_only=audio_only,
        hls_bundle=False,
        expected_bytes=info.content_length,
        convert_video_to_m4a=convert_video_to_m4a,
        subtitles=info.subtitles if info.kind is MediaKind.HLS_MASTER else (),
    )
