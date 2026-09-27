"""Bounded image downloads and non-destructive, atomic artwork publication."""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
from typing import Callable

import requests

MAX_ASSET_BYTES = 20 * 1024 * 1024


class ArtworkConflict(ValueError):
    """An unsafe path or user-owned file must be left untouched."""


def safe_asset_path(download_root: Path, target: Path) -> Path:
    root = download_root.resolve()
    if target.is_symlink():
        raise ArtworkConflict(f"Artwork is a symlink and was left untouched: {target}")
    resolved = target.resolve()
    if resolved == root or not resolved.is_relative_to(root):
        raise ArtworkConflict("Artwork must remain inside the configured download root.")
    return resolved


def asset_file_hash(path: Path) -> str | None:
    if path.is_symlink():
        raise ArtworkConflict(f"Artwork is a symlink and was left untouched: {path}")
    try:
        if not path.is_file() or path.stat().st_size > MAX_ASSET_BYTES:
            if path.exists():
                raise ArtworkConflict(f"Existing artwork is not a supported image file: {path}")
            return None
        with path.open("rb") as source:
            return hashlib.file_digest(source, "sha256").hexdigest()
    except FileNotFoundError:
        return None


@contextmanager
def asset_file_lock(download_root: Path, target: Path):
    """Serialize cooperating workers/processes without stale crash-time leases."""
    target = safe_asset_path(download_root, target)
    directory = download_root.resolve() / ".wireloft-assets-locks"
    lock_path = safe_asset_path(download_root, directory / (hashlib.sha256(str(target).encode()).hexdigest() + ".lock"))
    directory.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as lock:
        if os.name == "nt":
            import msvcrt
            if lock.tell() == 0:
                lock.write(b"\0")
                lock.flush()
            def acquire():
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            def release():
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            def acquire():
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            def release():
                fcntl.flock(lock, fcntl.LOCK_UN)
        deadline = time.monotonic() + 30
        while True:
            try:
                acquire()
                break
            except (BlockingIOError, OSError):
                if time.monotonic() >= deadline:
                    raise TimeoutError("Timed out waiting for the show artwork writer")
                time.sleep(0.05)
        try:
            yield target
        finally:
            release()
    # Do not unlink lock files: another process can still have their inode open.


def download_show_asset_jpeg(
    url: str, workspace: Path, *, ffmpeg_path: str, check_cancelled: Callable[[], None],
) -> Path:
    """Decode and convert the source, rather than merely naming PNG/WebP bytes .jpg."""
    if not url.startswith(("http://", "https://")):
        raise ValueError("Show artwork requires an HTTP(S) URL")
    check_cancelled()
    source = workspace / "source.image"
    with requests.get(url, stream=True, timeout=(5, 30)) as response:
        response.raise_for_status()
        if not response.headers.get("Content-Type", "").lower().startswith("image/"):
            raise ValueError("The show artwork response was not an image")
        if int(response.headers.get("Content-Length", "0")) > MAX_ASSET_BYTES:
            raise ValueError("Show artwork exceeds the 20 MiB limit")
        size = 0
        with source.open("wb") as output:
            for chunk in response.iter_content(64 * 1024):
                check_cancelled()
                size += len(chunk)
                if size > MAX_ASSET_BYTES:
                    raise ValueError("Show artwork exceeds the 20 MiB limit")
                output.write(chunk)
    check_cancelled()
    destination = workspace / "asset.jpg"
    subprocess.run(
        [ffmpeg_path, "-nostdin", "-v", "error", "-protocol_whitelist", "file,pipe",
         "-f", "image2", "-pattern_type", "none", "-i", str(source), "-frames:v", "1", "-q:v", "2", "-update", "1", "-y", str(destination)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=45,
    )
    check_cancelled()
    if not destination.is_file() or not 0 < destination.stat().st_size <= MAX_ASSET_BYTES:
        raise ValueError("Show artwork could not be converted to a bounded JPEG")
    return destination


def publish_show_asset(
    source: Path, target: Path, *, download_root: Path, expected_hash: str | None,
    check_cancelled: Callable[[], None],
) -> None:
    """Copy to the target filesystem, then replace only the observed version."""
    target = safe_asset_path(download_root, target)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(prefix=".wireloft-artwork-", suffix=".tmp", dir=target.parent, delete=False) as output:
            temporary = Path(output.name)
            with source.open("rb") as incoming:
                shutil.copyfileobj(incoming, output)
            output.flush()
            os.fsync(output.fileno())
        check_cancelled()
        safe_asset_path(download_root, target)
        if asset_file_hash(target) != expected_hash:
            raise ArtworkConflict(f"Artwork changed during download and was left untouched: {target}")
        if expected_hash is None:
            try:
                # Claim a previously absent name atomically; never replace a file
                # another writer created after our absence check.
                os.link(temporary, target)
            except FileExistsError as exc:
                raise ArtworkConflict(f"Artwork appeared during download: {target}") from exc
            temporary.unlink()
        else:
            os.replace(temporary, target)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
