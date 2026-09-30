"""Measured, cancellable filesystem transfers with durable completion."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Callable

from ..errors import DownloadCancelled
from ..models import DownloadProgress


def copy_file(
    source: Path, destination: Path, *,
    progress: Callable[[DownloadProgress], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> int:
    total = source.stat().st_size
    received = 0
    created = False
    try:
        with source.open("rb") as incoming, destination.open("xb") as outgoing:
            created = True
            while True:
                if should_cancel is not None and should_cancel():
                    raise DownloadCancelled("Canceled while copying files into the library")
                chunk = incoming.read(1024 * 1024)
                if not chunk:
                    break
                outgoing.write(chunk)
                received += len(chunk)
                if progress is not None:
                    progress(DownloadProgress(received, total))
            outgoing.flush()
            os.fsync(outgoing.fileno())
        if received != total:
            raise OSError("Source changed during publication")
        return received
    except BaseException:
        if created:
            destination.unlink(missing_ok=True)
        raise
