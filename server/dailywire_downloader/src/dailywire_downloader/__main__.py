"""Small CLI for probing and downloading media URLs by hand.

Examples:
    dailywire-downloader probe "https://stream.mux.com/<id>.m3u8?token=..."
    dailywire-downloader download "<rendition or file url>" out.ts
"""

from __future__ import annotations

import argparse
import sys

from . import DownloadError, MediaKind, __version__, download_file, download_hls, probe


def _print_progress(p) -> None:
    if p.segments_total:
        print(f"\r{p.segments_done}/{p.segments_total} segments, {p.bytes_downloaded // 1024} KiB", end="", flush=True)
    elif p.total_bytes:
        print(f"\r{p.bytes_downloaded}/{p.total_bytes} bytes", end="", flush=True)
    else:
        print(f"\r{p.bytes_downloaded} bytes", end="", flush=True)


def _cmd_probe(args: argparse.Namespace) -> int:
    info = probe(args.url)
    print(f"kind: {info.kind.value}")
    if info.kind is MediaKind.HLS_MASTER:
        for r in info.renditions:
            print(f"  {r.resolution or '?'}  bandwidth={r.bandwidth or '?'}  codecs={r.codecs or '?'}")
            print(f"    {r.url}")
    else:
        print(f"  content_type: {info.content_type}")
        print(f"  content_length: {info.content_length}")
    print(f"suggested extension: .{info.suggested_extension}")
    return 0


def _cmd_download(args: argparse.Namespace) -> int:
    info = probe(args.url)
    if info.kind is MediaKind.HLS_MASTER:
        print("URL is a master playlist; pick a rendition URL from `probe` output", file=sys.stderr)
        return 2

    if info.kind is MediaKind.HLS_MEDIA:
        result = download_hls(args.url, args.dest, progress=_print_progress)
    else:
        result = download_file(args.url, args.dest, progress=_print_progress)

    print(f"\nsaved {result.bytes_downloaded} bytes to {result.path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="dailywire-downloader",
        description="Probe and download HLS renditions or direct media files.",
    )
    parser.add_argument("--version", action="version", version=f"dailywire-downloader v{__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_probe = sub.add_parser("probe", help="Show what a media URL offers")
    p_probe.add_argument("url")
    p_probe.set_defaults(func=_cmd_probe)

    p_dl = sub.add_parser("download", help="Download a rendition/media URL to a file")
    p_dl.add_argument("url")
    p_dl.add_argument("dest")
    p_dl.set_defaults(func=_cmd_download)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except DownloadError as e:
        print(f"\nERROR: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
