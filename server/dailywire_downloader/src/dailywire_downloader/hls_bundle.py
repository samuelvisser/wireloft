from __future__ import annotations

import os
import re
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Optional
from urllib.parse import urljoin, urlparse

from .errors import DownloadCancelled, DownloadError, EncryptedMediaError, MediaUnavailableError
from .hls import is_master_playlist, is_playlist, parse_attribute_list, parse_master_playlist
from .http import http_get, http_get_text
from .models import CancelCheck, DownloadProgress, DownloadResult, ProgressCallback, VideoRendition


_TARGET_HEIGHTS = (480, 720, 1080)
_PROGRESS_INTERVAL_S = 1.0
_CHUNK_SIZE = 256 * 1024
_URI_ATTRIBUTE_RE = re.compile(r'URI="[^"]*"')
_HLS_BUNDLE_MARKER = ".wireloft-hls-bundle"


@dataclass(frozen=True)
class _PlaylistJob:
    source_url: str
    output_directory: Path
    text: str
    segment_count: int


def hls_asset_root(master_path: str | Path) -> Path:
    """Return the companion directory owned by a local HLS master playlist."""
    return Path(f"{Path(master_path)}.assets")


def hls_asset_marker(master_path: str | Path) -> Path:
    return hls_asset_root(master_path) / _HLS_BUNDLE_MARKER


def missing_hls_bundle_files(master_path: str | Path) -> list[Path]:
    """Return missing/unsafe files referenced by a WireLoft local HLS bundle."""
    root = hls_asset_root(master_path)
    missing: list[Path] = []

    if not hls_asset_marker(master_path).is_file():
        return [hls_asset_marker(master_path)]

    required_playlists = [
        root / f"{height}p" / "playlist.m3u8"
        for height in _TARGET_HEIGHTS
    ]
    for playlist in required_playlists:
        if not playlist.is_file():
            missing.append(playlist)

    for playlist in root.glob("*/playlist.m3u8"):
        if playlist.is_file():
            missing.extend(_missing_playlist_files(playlist, root=root))

    return missing


def download_hls_bundle(
        master_url: str,
        master_path: str,
        *,
        progress: Optional[ProgressCallback] = None,
        should_cancel: Optional[CancelCheck] = None,
) -> DownloadResult:
    """Store 480p, 720p and 1080p as a compact adaptive HLS bundle.

    Each rendition is stored as one byte-range-addressed media file instead of
    hundreds of loose segment files. The master and media playlists remain
    normal HLS and use paths served by WireLoft's stable RSS endpoint.
    """
    _ensure_not_cancelled(should_cancel)
    master_text = http_get_text(master_url)
    if not is_playlist(master_text) or not is_master_playlist(master_text):
        raise DownloadError("HLS output requires a master playlist")

    renditions = parse_master_playlist(master_text, base_url=master_url)
    selected = _select_required_renditions(renditions)
    selected_urls = {rendition.url for rendition in selected.values()}

    asset_root = hls_asset_root(master_path)
    staging_asset_root = Path(f"{asset_root}.part")
    part_path = Path(f"{master_path}.part")
    try:
        shutil.rmtree(staging_asset_root, ignore_errors=True)
        if asset_root.exists():
            marker = asset_root / _HLS_BUNDLE_MARKER
            if marker.is_file():
                shutil.rmtree(asset_root)
            else:
                raise DownloadError(
                    f"HLS asset destination already exists and is not owned by WireLoft: {asset_root}"
                )
        staging_asset_root.mkdir(parents=True, exist_ok=False)
        (staging_asset_root / _HLS_BUNDLE_MARKER).write_text(
            "WireLoft local HLS bundle\n",
            encoding="utf-8",
        )
        Path(master_path).parent.mkdir(parents=True, exist_ok=True)

        master_lines, jobs = _build_master_and_jobs(
            master_text,
            master_url=master_url,
            selected_urls=selected_urls,
            selected=selected,
            asset_root=staging_asset_root,
        )
        segments_total = sum(job.segment_count for job in jobs)
        bytes_downloaded = 0
        segments_done = 0
        last_report = 0.0

        def report(*, force: bool = False) -> None:
            nonlocal last_report
            now = time.monotonic()
            if progress and (force or now - last_report >= _PROGRESS_INTERVAL_S):
                last_report = now
                progress(DownloadProgress(
                    bytes_downloaded=bytes_downloaded,
                    segments_done=segments_done,
                    segments_total=segments_total,
                ))

        def add_bytes(amount: int) -> None:
            nonlocal bytes_downloaded
            bytes_downloaded += amount
            report()

        def complete_segment() -> None:
            nonlocal segments_done
            segments_done += 1
            report()

        for job in jobs:
            _ensure_not_cancelled(should_cancel)
            playlist_lines = _mirror_media_playlist(
                job,
                should_cancel=should_cancel,
                on_bytes=add_bytes,
                on_segment=complete_segment,
            )
            playlist_path = job.output_directory / "playlist.m3u8"
            playlist_path.write_text(
                "\n".join(playlist_lines).rstrip() + "\n",
                encoding="utf-8",
            )

        part_path.write_text(
            "\n".join(master_lines).rstrip() + "\n",
            encoding="utf-8",
        )
        _ensure_not_cancelled(should_cancel)
        os.replace(staging_asset_root, asset_root)
        os.replace(part_path, master_path)
        report(force=True)
        return DownloadResult(
            path=str(master_path),
            bytes_downloaded=bytes_downloaded,
            segments_downloaded=segments_total,
        )
    except BaseException:
        try:
            part_path.unlink(missing_ok=True)
        except OSError:
            pass
        shutil.rmtree(staging_asset_root, ignore_errors=True)

        # Direct-mode downloads reserve the final master path as a zero-byte
        # placeholder. If publication failed after the asset directory moved,
        # remove that owned directory as part of the failed attempt.
        try:
            master_published = (
                Path(master_path).is_file()
                and Path(master_path).stat().st_size > 0
            )
        except OSError:
            master_published = False
        if not master_published and (asset_root / _HLS_BUNDLE_MARKER).is_file():
            shutil.rmtree(asset_root, ignore_errors=True)
        raise


def _select_required_renditions(
        renditions: list[VideoRendition],
) -> dict[int, VideoRendition]:
    selected: dict[int, VideoRendition] = {}
    for height in _TARGET_HEIGHTS:
        matches = [item for item in renditions if item.height == height]
        if not matches:
            raise MediaUnavailableError(
                "HLS source does not provide all required adaptive renditions "
                "(480p, 720p and 1080p)"
            )
        selected[height] = max(
            matches,
            key=lambda item: item.bandwidth or 0,
        )
    return selected


def _build_master_and_jobs(
        master_text: str,
        *,
        master_url: str,
        selected_urls: set[str],
        selected: dict[int, VideoRendition],
        asset_root: Path,
) -> tuple[list[str], list[_PlaylistJob]]:
    lines = master_text.splitlines()
    selected_audio_groups: set[str] = set()
    selected_stream_lines: list[tuple[str, str, int]] = []

    index = 0
    while index < len(lines):
        line = lines[index].strip()
        if not line.startswith("#EXT-X-STREAM-INF:"):
            index += 1
            continue
        attrs = parse_attribute_list(line.split(":", 1)[1])
        uri_index = index + 1
        while uri_index < len(lines) and (
            not lines[uri_index].strip()
            or lines[uri_index].lstrip().startswith("#")
        ):
            uri_index += 1
        if uri_index >= len(lines):
            break

        source_url = urljoin(master_url, lines[uri_index].strip())
        if source_url in selected_urls:
            height = next(
                height
                for height, rendition in selected.items()
                if rendition.url == source_url
            )
            selected_stream_lines.append((line, source_url, height))
            audio_group = attrs.get("AUDIO")
            if audio_group:
                selected_audio_groups.add(audio_group)
        index = uri_index + 1

    if len(selected_stream_lines) != len(_TARGET_HEIGHTS):
        raise DownloadError(
            "Could not map required HLS renditions back to the master playlist"
        )

    master_out = ["#EXTM3U"]
    jobs: list[_PlaylistJob] = []

    for raw in lines[1:]:
        line = raw.strip()
        if line.startswith(("#EXT-X-VERSION:", "#EXT-X-INDEPENDENT-SEGMENTS")):
            master_out.append(line)

    audio_index = 0
    for raw in lines:
        line = raw.strip()
        if not line.startswith("#EXT-X-MEDIA:"):
            continue
        attrs = parse_attribute_list(line.split(":", 1)[1])
        if attrs.get("TYPE") != "AUDIO":
            continue
        if attrs.get("GROUP-ID") not in selected_audio_groups:
            continue

        uri = attrs.get("URI")
        if not uri:
            master_out.append(line)
            continue

        public_uri = f"hls/audio-{audio_index}/playlist.m3u8"
        output_directory = asset_root / f"audio-{audio_index}"
        source_url = urljoin(master_url, uri)
        text = http_get_text(source_url)
        _validate_vod_media_playlist(text)
        master_out.append(
            _URI_ATTRIBUTE_RE.sub(
                f'URI="{public_uri}"',
                line,
                count=1,
            )
        )
        jobs.append(_PlaylistJob(
            source_url=source_url,
            output_directory=output_directory,
            text=text,
            segment_count=_count_media_segments(text),
        ))
        audio_index += 1

    for stream_line, source_url, height in sorted(
        selected_stream_lines,
        key=lambda item: item[2],
    ):
        public_uri = f"hls/{height}p/playlist.m3u8"
        text = http_get_text(source_url)
        _validate_vod_media_playlist(text)
        master_out.append(stream_line)
        master_out.append(public_uri)
        jobs.append(_PlaylistJob(
            source_url=source_url,
            output_directory=asset_root / f"{height}p",
            text=text,
            segment_count=_count_media_segments(text),
        ))

    return master_out, jobs


def _validate_vod_media_playlist(text: str) -> None:
    if not is_playlist(text) or is_master_playlist(text):
        raise DownloadError("Expected an HLS media playlist")
    if "#EXT-X-ENDLIST" not in text:
        raise DownloadError(
            "Refusing to store a live/incomplete HLS playlist as a local download"
        )
    if "#EXT-X-BYTERANGE" in text or "BYTERANGE=" in text:
        raise DownloadError(
            "Source byte-range HLS playlists are not supported for local HLS downloads"
        )

    for raw in text.splitlines():
        line = raw.strip()
        if not line.startswith("#EXT-X-KEY:"):
            continue
        attrs = parse_attribute_list(line.split(":", 1)[1])
        if attrs.get("METHOD", "NONE").upper() != "NONE":
            raise EncryptedMediaError(
                f"Encrypted HLS stream (METHOD={attrs.get('METHOD')}) is not supported"
            )


def _count_media_segments(text: str) -> int:
    expect_segment = False
    count = 0
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("#EXTINF:"):
            expect_segment = True
            continue
        if expect_segment and line and not line.startswith("#"):
            count += 1
            expect_segment = False
    return count


def _mirror_media_playlist(
        job: _PlaylistJob,
        *,
        should_cancel: Optional[CancelCheck],
        on_bytes,
        on_segment,
) -> list[str]:
    job.output_directory.mkdir(parents=True, exist_ok=False)
    media_filename = _compact_media_filename(job.text)
    media_path = job.output_directory / media_filename
    output: list[str] = []
    expect_segment = False

    with media_path.open("xb") as media_file:
        for raw in job.text.splitlines():
            _ensure_not_cancelled(should_cancel)
            line = raw.strip()

            if line.startswith("#EXT-X-MAP:"):
                attrs = parse_attribute_list(line.split(":", 1)[1])
                uri = attrs.get("URI")
                if not uri:
                    output.append(raw)
                    continue
                offset = media_file.tell()
                amount = _download_into(
                    urljoin(job.source_url, uri),
                    media_file,
                    should_cancel=should_cancel,
                )
                on_bytes(amount)
                rewritten = _URI_ATTRIBUTE_RE.sub(
                    f'URI="{media_filename}"',
                    raw,
                    count=1,
                )
                output.append(
                    f'{rewritten},BYTERANGE="{amount}@{offset}"'
                )
                continue

            if line.startswith("#EXTINF:"):
                expect_segment = True
                output.append(raw)
                continue

            if expect_segment and line and not line.startswith("#"):
                offset = media_file.tell()
                amount = _download_into(
                    urljoin(job.source_url, line),
                    media_file,
                    should_cancel=should_cancel,
                )
                on_bytes(amount)
                on_segment()
                output.append(f"#EXT-X-BYTERANGE:{amount}@{offset}")
                output.append(media_filename)
                expect_segment = False
                continue

            output.append(raw)

    return _ensure_byterange_playlist_version(output)


def _compact_media_filename(text: str) -> str:
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("#EXT-X-MAP:"):
            return "media.mp4"

    expect_segment = False
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("#EXTINF:"):
            expect_segment = True
            continue
        if expect_segment and line and not line.startswith("#"):
            return f"media{_safe_suffix(line, default='.ts')}"

    raise DownloadError("HLS media playlist contains no segments")


def _ensure_byterange_playlist_version(lines: list[str]) -> list[str]:
    required_version = 6 if any(
        raw.strip().startswith("#EXT-X-MAP:")
        for raw in lines
    ) else 4
    for index, raw in enumerate(lines):
        line = raw.strip()
        if not line.startswith("#EXT-X-VERSION:"):
            continue
        try:
            version = int(line.split(":", 1)[1])
        except ValueError:
            version = required_version
        lines[index] = f"#EXT-X-VERSION:{max(version, required_version)}"
        return lines

    insert_at = 1 if lines and lines[0].strip() == "#EXTM3U" else 0
    lines.insert(insert_at, f"#EXT-X-VERSION:{required_version}")
    return lines


def _download_into(
        url: str,
        destination: BinaryIO,
        *,
        should_cancel: Optional[CancelCheck],
) -> int:
    written = 0
    with http_get(url) as response:
        for chunk in response.iter_chunks(_CHUNK_SIZE):
            _ensure_not_cancelled(should_cancel)
            destination.write(chunk)
            written += len(chunk)
    return written


def _safe_suffix(url: str, *, default: str) -> str:
    suffix = Path(urlparse(url).path).suffix.lower()
    if suffix in {".ts", ".m4s", ".mp4", ".aac", ".m4a"}:
        if suffix == ".m4s":
            return ".mp4"
        return suffix
    return default


def _missing_playlist_files(playlist: Path, *, root: Path) -> list[Path]:
    try:
        text = playlist.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return [playlist]

    missing: list[Path] = []
    saw_segment = False
    resolved_root = root.resolve()
    for raw in text.splitlines():
        line = raw.strip()
        uri: str | None = None
        if line.startswith("#EXT-X-MAP:"):
            uri = parse_attribute_list(line.split(":", 1)[1]).get("URI")
        elif line and not line.startswith("#"):
            uri = line
            saw_segment = True

        if not uri:
            continue
        candidate = (playlist.parent / uri).resolve()
        if not candidate.is_relative_to(resolved_root) or not candidate.is_file():
            missing.append(candidate)

    if not saw_segment:
        missing.append(playlist)
    return missing


def _ensure_not_cancelled(should_cancel: Optional[CancelCheck]) -> None:
    if should_cancel and should_cancel():
        raise DownloadCancelled("Download cancelled")
