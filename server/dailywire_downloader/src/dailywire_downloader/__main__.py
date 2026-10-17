"""Command-line interface for completed downloads from already-resolved URLs.

This tool is an executor, not a provider extractor. It never searches for
playback URLs or reads WireLoft application configuration.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlparse

from . import DownloadError, DownloadSnapshot, SidecarSpec, __version__, download_media


def _pair(value: str) -> tuple[str, str]:
    key, separator, content = value.partition("=")
    if not separator or not key or not content:
        raise ValueError("Expected NAME=VALUE")
    return key, content


def _rendition(value: str) -> tuple[int, str]:
    height, url = _pair(value)
    if not height.isdecimal() or not url.startswith(("https://", "http://")):
        raise ValueError("Expected HEIGHT=HTTP_URL for an HLS rendition")
    return int(height), url


def _asset_extension(value: str) -> str:
    extension = Path(urlparse(value).path).suffix.lstrip(".").lower()
    return extension if extension.isalnum() else "bin"


def _collect_assets(args: argparse.Namespace) -> tuple[SidecarSpec, ...]:
    assets: list[SidecarSpec] = []
    for item in args.sidecar:
        asset_id, url = _pair(item)
        assets.append(SidecarSpec(
            id=asset_id, kind=asset_id, url=url, extension=_asset_extension(url),
        ))
    for item in args.generated_sidecar:
        asset_id, filename = _pair(item)
        extension = Path(filename).suffix.lstrip(".").lower() or "bin"
        assets.append(SidecarSpec(
            id=asset_id, kind=asset_id, content=Path(filename).read_bytes(),
            extension=extension,
        ))
    if args.sidecars_json:
        documents = json.loads(Path(args.sidecars_json).read_text(encoding="utf-8"))
        if not isinstance(documents, list):
            raise ValueError("Sidecar configuration must be a JSON array")
        for item in documents:
            if not isinstance(item, dict):
                raise ValueError("Each sidecar must be a JSON object")
            fields = dict(item)
            if "content_file" in fields:
                fields["content"] = Path(fields.pop("content_file")).read_bytes()
            if "allowed_extensions" in fields:
                fields["allowed_extensions"] = tuple(fields["allowed_extensions"])
            assets.append(SidecarSpec(**fields))
    if args.artwork:
        if not any(asset.id == args.artwork for asset in assets):
            raise ValueError("Embedded artwork ID is not a supplied sidecar")
    return tuple(assets)


def _print_progress(snapshot: DownloadSnapshot) -> None:
    media = next((stage for stage in snapshot.stages if stage.id == "media"), None)
    total = f" / {media.total_bytes}" if media is not None and media.total_bytes else ""
    received = media.bytes_received if media is not None else 0
    stage = next((stage for stage in snapshot.stages if stage.id == snapshot.main_activity), None)
    activity = stage.code if stage is not None else snapshot.phase
    print(f"\r{activity}: {received}{total} bytes", file=sys.stderr, end="", flush=True)


def _cmd_download(args: argparse.Namespace) -> int:
    assets = _collect_assets(args)
    metadata = dict(_pair(item) for item in args.metadata)
    execution = None
    try:
        execution = download_media(
            args.url, args.destination, transfer=args.transfer,
            format_label=args.format_label, extension=args.extension,
            download_mode=args.download_mode, temporary_root=args.temporary_root,
            ffmpeg_path=args.ffmpeg, remux_to_mp4=args.remux_to_mp4,
            convert_video_to_m4a=args.convert_video_to_m4a, audio_only=args.audio_only,
            sidecars=assets, metadata_tags=metadata, artwork_asset_id=args.artwork,
            hls_renditions=tuple(_rendition(item) for item in args.hls_rendition),
            progress=None if args.quiet else _print_progress,
        )
        if not args.quiet:
            print(file=sys.stderr)
        print(f"saved {execution.result.bytes_downloaded} transferred bytes to {execution.result.path}")
        for asset in execution.assets:
            print(f"  {asset.kind}: {asset.path}")
        return 0
    finally:
        if execution is not None:
            execution.cleanup_workspace()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="dailywire-downloader",
        description="Transfer an already-resolved media URL and apply optional processing.",
    )
    parser.add_argument("--version", action="version", version=f"dailywire-downloader v{__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    download = sub.add_parser("download", help="Download, post-process and publish media")
    download.add_argument("url", help="Direct media, HLS rendition, or HLS master URL")
    download.add_argument("destination", help="Final output file including extension")
    download.add_argument("--transfer", choices=("file", "hls", "hls_bundle"), default="file")
    download.add_argument("--extension", help="Explicit output extension (must match destination)")
    download.add_argument("--format-label", help="Opaque label included in the execution result")
    download.add_argument("--download-mode", choices=("temporary", "direct"), default="temporary")
    download.add_argument("--temporary-root", help="Temporary workspace root")
    download.add_argument("--ffmpeg", default="ffmpeg", help="Path to FFmpeg")
    download.add_argument("--remux-to-mp4", action="store_true")
    download.add_argument("--convert-video-to-m4a", action="store_true")
    download.add_argument("--audio-only", action="store_true")
    download.add_argument("--sidecar", action="append", default=[], metavar="ID=URL",
                          help="Download and publish an auxiliary file; may be repeated")
    download.add_argument("--generated-sidecar", action="append", default=[], metavar="ID=FILE",
                          help="Publish locally generated sidecar bytes; may be repeated")
    download.add_argument("--sidecars-json", metavar="FILE",
                          help="JSON array of complete SidecarSpec options; supports content_file")
    download.add_argument("--artwork", metavar="ID", help="Sidecar ID to embed as artwork")
    download.add_argument("--hls-rendition", action="append", default=[], metavar="HEIGHT=URL",
                          help="Resolved rendition for HLS bundles; repeat for each selected height")
    download.add_argument("--metadata", action="append", default=[], metavar="KEY=VALUE",
                          help="Embed a container metadata tag; may be repeated")
    download.add_argument("--quiet", action="store_true", help="Suppress progress updates")
    download.set_defaults(func=_cmd_download)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (DownloadError, ValueError, OSError) as error:
        print(f"\nERROR: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nDownload interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
