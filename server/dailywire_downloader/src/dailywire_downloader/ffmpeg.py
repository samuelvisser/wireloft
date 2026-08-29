from __future__ import annotations

import logging
import os
import shutil
import subprocess
from typing import Optional

from .errors import DownloadCancelled, DownloadError, FfmpegNotFoundError
from .models import CancelCheck

logger = logging.getLogger(__name__)

# How many of the last (non-boilerplate) output lines to surface in the
# raised error / stored error_message.
_ERROR_TAIL_LINES = 15

# ffmpeg always prints these before touching the actual input/output, and
# they carry no diagnostic value for a remux failure: the "configuration:"
# line alone is routinely 600-900+ characters (every --enable-lib flag the
# binary was built with), so on a build with a large config, keeping it in
# the tail can by itself fill (and overflow) the entire error budget before
# the line that actually explains the failure. Drop them outright rather
# than count on the tail window happening to be short enough to exclude them.
_FFMPEG_BANNER_PREFIXES = (
    "ffmpeg version",
    "built with",
    "configuration:",
    "libavutil",
    "libavcodec",
    "libavformat",
    "libavdevice",
    "libavfilter",
    "libswscale",
    "libswresample",
)


def ffmpeg_available(ffmpeg_path: str = "ffmpeg") -> bool:
    """Whether the given ffmpeg binary can be found on PATH (or is an existing file)."""
    return shutil.which(ffmpeg_path) is not None


def remux_to_mp4(
        src_path: str,
        dest_path: str,
        *,
        ffmpeg_path: str = "ffmpeg",
        should_cancel: Optional[CancelCheck] = None,
) -> None:
    """Repackage a downloaded media file (e.g. raw HLS/MPEG-TS) into an MP4 container.

    This is a stream copy, not a re-encode: ffmpeg only rewrites the container,
    so it is fast and lossless. It exists because plain MPEG-TS output (what HLS
    segments concatenate into) plays poorly in most media players/servers
    compared to MP4. Writes to ``<dest_path>.part`` and renames on success.

    ``-f mp4`` forces the output muxer explicitly: ffmpeg otherwise picks it
    from the *output filename's own extension*, and the real destination
    write path here is ``<dest_path>.part`` (renamed into place only once
    the mux succeeds) - an extension ffmpeg can't map to any muxer at all,
    so without this it fails outright with "Unable to choose an output
    format" before ever touching a single frame.

    Two more flags address failure modes that show up once muxing actually
    starts: ``-fflags +genpts`` regenerates timestamps across the segment
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
        command = [
            ffmpeg_path, "-y",
            "-fflags", "+genpts",
            "-i", src_path,
            "-c", "copy",
            "-bsf:a", "aac_adtstoasc",
            "-movflags", "+faststart",
            "-f", "mp4",
            part_path,
        ]
        result = (
            _run_cancellable(command, should_cancel)
            if should_cancel is not None
            else subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
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


def _run_cancellable(command: list[str], should_cancel: CancelCheck):
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        while True:
            if should_cancel():
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                raise DownloadCancelled("Download cancelled during local processing")
            try:
                output, _ = process.communicate(timeout=0.1)
                break
            except subprocess.TimeoutExpired:
                continue
    except BaseException:
        if process.poll() is None:
            process.kill()
            process.wait()
        raise

    return subprocess.CompletedProcess(command, process.returncode, output)


def _tail_lines(output: str, count: int = _ERROR_TAIL_LINES) -> str:
    all_lines = [line for line in output.splitlines() if line.strip()]
    content_lines = [
        line for line in all_lines
        if not line.strip().startswith(_FFMPEG_BANNER_PREFIXES)
    ]
    # If literally everything was banner (e.g. ffmpeg died before printing
    # anything else), fall back to the raw tail so something is still shown.
    lines = content_lines or all_lines
    return "\n".join(lines[-count:])


def _remove_quietly(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass
