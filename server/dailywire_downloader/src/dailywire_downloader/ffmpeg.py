from __future__ import annotations

import logging
import os
import shutil
import subprocess

from .errors import DownloadError, FfmpegNotFoundError

logger = logging.getLogger(__name__)

# How many of the last output lines to surface in the raised error / stored
# error_message. A raw character slice can land mid-line (e.g. inside
# ffmpeg's multi-line "configuration:" banner), which is what showed up in
# practice: a chunk of build flags with no actual error visible. Lines are a
# much more reliable unit to keep, since ffmpeg's real error is always its
# own line near the end.
_ERROR_TAIL_LINES = 20


def ffmpeg_available(ffmpeg_path: str = "ffmpeg") -> bool:
    """Whether the given ffmpeg binary can be found on PATH (or is an existing file)."""
    return shutil.which(ffmpeg_path) is not None


def remux_to_mp4(src_path: str, dest_path: str, *, ffmpeg_path: str = "ffmpeg") -> None:
    """Repackage a downloaded media file (e.g. raw HLS/MPEG-TS) into an MP4 container.

    This is a stream copy, not a re-encode: ffmpeg only rewrites the container,
    so it is fast and lossless. It exists because plain MPEG-TS output (what HLS
    segments concatenate into) plays poorly in most media players/servers
    compared to MP4. Writes to ``<dest_path>.part`` and renames on success.

    Two flags address the failure modes actually seen remuxing HLS-downloaded
    TS into MP4: ``-fflags +genpts`` regenerates timestamps across the segment
    boundaries in a concatenated TS file (MP4 is far less forgiving of
    discontinuous/non-monotonic timestamps than TS is), and
    ``-bsf:a aac_adtstoasc`` converts ADTS-framed AAC audio (how HLS carries
    it) into the raw-AAC-in-esds form MP4 requires; without it, muxing AAC
    audio from TS into MP4 reliably fails. It is a no-op when there is no
    audio stream, and safe here since Daily Wire's HLS audio is AAC.
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
                "-fflags", "+genpts",
                "-i", src_path,
                "-c", "copy",
                "-bsf:a", "aac_adtstoasc",
                "-movflags", "+faststart",
                part_path,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        if result.returncode != 0:
            logger.error(
                "ffmpeg remux to mp4 failed (exit %s) for '%s' -> '%s':\n%s",
                result.returncode, src_path, dest_path, result.stdout,
            )
            raise DownloadError(
                f"ffmpeg remux to mp4 failed (exit {result.returncode}): {_tail_lines(result.stdout)}"
            )
        os.replace(part_path, dest_path)
    except BaseException:
        _remove_quietly(part_path)
        raise


def _tail_lines(output: str, count: int = _ERROR_TAIL_LINES) -> str:
    lines = [line for line in output.splitlines() if line.strip()]
    return "\n".join(lines[-count:])


def _remove_quietly(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass
