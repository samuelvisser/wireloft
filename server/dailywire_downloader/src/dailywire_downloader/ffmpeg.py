from __future__ import annotations

import os
import shutil
import subprocess

from .errors import DownloadError, FfmpegNotFoundError


def ffmpeg_available(ffmpeg_path: str = "ffmpeg") -> bool:
    """Whether the given ffmpeg binary can be found on PATH (or is an existing file)."""
    return shutil.which(ffmpeg_path) is not None


def remux_to_mp4(src_path: str, dest_path: str, *, ffmpeg_path: str = "ffmpeg") -> None:
    """Repackage a downloaded media file (e.g. raw HLS/MPEG-TS) into an MP4 container.

    This is a stream copy, not a re-encode: ffmpeg only rewrites the container,
    so it is fast and lossless. It exists because plain MPEG-TS output (what HLS
    segments concatenate into) plays poorly in most media players/servers
    compared to MP4. Writes to ``<dest_path>.part`` and renames on success.
    """
    if not ffmpeg_available(ffmpeg_path):
        raise FfmpegNotFoundError(
            f"ffmpeg binary '{ffmpeg_path}' not found on PATH; install ffmpeg or disable "
            f"download_settings.remux_video_to_mp4"
        )

    part_path = dest_path + ".part"
    try:
        result = subprocess.run(
            [
                ffmpeg_path, "-y",
                "-i", src_path,
                "-c", "copy",
                "-movflags", "+faststart",
                part_path,
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise DownloadError(f"ffmpeg remux to mp4 failed (exit {result.returncode}): {result.stderr[-2000:]}")
        os.replace(part_path, dest_path)
    except BaseException:
        _remove_quietly(part_path)
        raise


def _remove_quietly(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass
