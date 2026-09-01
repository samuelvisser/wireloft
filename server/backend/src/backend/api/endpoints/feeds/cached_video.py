from __future__ import annotations

import hashlib
import logging
import os
import subprocess
import threading
import time
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException

from config import get_settings


logger = logging.getLogger(__name__)

_CACHE_DIRECTORY = ".wireloft-rss-video-cache"
_CACHE_MAX_AGE_SECONDS = 7 * 24 * 60 * 60
_CACHE_LOCKS: dict[Path, threading.Lock] = {}
_CACHE_LOCKS_GUARD = threading.Lock()


def _cache_path(episode_uuid: str) -> Path:
    digest = hashlib.sha256(episode_uuid.encode("utf-8")).hexdigest()
    root = Path(get_settings().download_settings.download_root) / _CACHE_DIRECTORY
    return root / f"{digest}.mp4"


def _is_current(path: Path) -> bool:
    try:
        stat = path.stat()
    except OSError:
        return False
    return stat.st_size > 0 and time.time() - stat.st_mtime < _CACHE_MAX_AGE_SECONDS


def get_cached_mp4_path(episode_uuid: str) -> Path | None:
    path = _cache_path(episode_uuid)
    return path if _is_current(path) else None


def get_cached_mp4_size(episode_uuid: str) -> int | None:
    path = get_cached_mp4_path(episode_uuid)
    if path is None:
        return None
    try:
        return path.stat().st_size
    except OSError:
        return None


def _lock_for(path: Path) -> threading.Lock:
    with _CACHE_LOCKS_GUARD:
        return _CACHE_LOCKS.setdefault(path, threading.Lock())


def _cleanup_expired_files(root: Path) -> None:
    cutoff = time.time() - _CACHE_MAX_AGE_SECONDS
    try:
        paths = list(root.iterdir())
    except OSError:
        return

    for path in paths:
        try:
            if path.is_file() and path.stat().st_mtime < cutoff:
                path.unlink()
        except OSError:
            continue


def _ffmpeg_command(source_url: str, output_path: Path) -> list[str]:
    return [
        get_settings().download_settings.ffmpeg_path,
        "-hide_banner",
        "-loglevel", "error",
        "-nostats",
        "-nostdin",
        "-y",
        "-fflags", "+genpts",
        "-i", source_url,
        "-map", "0:v:0",
        "-map", "0:a:0?",
        "-c", "copy",
        "-bsf:a", "aac_adtstoasc",
        "-movflags", "+faststart",
        "-f", "mp4",
        str(output_path),
    ]


def prepare_cached_mp4(source_url: str, *, episode_uuid: str) -> Path:
    target = _cache_path(episode_uuid)
    target.parent.mkdir(parents=True, exist_ok=True)

    with _lock_for(target):
        if _is_current(target):
            try:
                target.touch()
            except OSError:
                pass
            return target

        _cleanup_expired_files(target.parent)
        temporary = target.with_name(f".{target.stem}.{uuid4().hex}.part")
        try:
            try:
                completed = subprocess.run(
                    _ffmpeg_command(source_url, temporary),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    text=True,
                    check=False,
                )
            except FileNotFoundError as exc:
                raise HTTPException(
                    status_code=503,
                    detail="ffmpeg is required to prepare cached RSS video",
                ) from exc
            except OSError as exc:
                raise HTTPException(
                    status_code=502,
                    detail="Could not prepare Daily Wire video",
                ) from exc

            try:
                prepared = temporary.is_file() and temporary.stat().st_size > 0
            except OSError:
                prepared = False

            if completed.returncode != 0 or not prepared:
                logger.error(
                    "ffmpeg failed to prepare cached RSS video (exit %s): %s",
                    completed.returncode,
                    completed.stderr[-4000:],
                )
                raise HTTPException(
                    status_code=502,
                    detail="Daily Wire video could not be prepared as MP4",
                )

            os.replace(temporary, target)
            return target
        finally:
            temporary.unlink(missing_ok=True)
