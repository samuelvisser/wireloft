from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from itertools import count
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DownloadPathReservation:
    """One filesystem-level claim on a concrete download destination."""

    path: Path
    stat_dev: int
    stat_ino: int

    def release_if_unclaimed(self) -> None:
        """Remove our empty placeholder if no completed file replaced it."""
        try:
            current = self.path.stat()
        except FileNotFoundError:
            return
        except OSError:
            logger.warning("Could not inspect download path reservation '%s'", self.path, exc_info=True)
            return

        # Successful downloaders atomically replace the placeholder. Size is an
        # important second guard for filesystems that expose weak inode values.
        if (
            current.st_size != 0
            or current.st_dev != self.stat_dev
            or current.st_ino != self.stat_ino
        ):
            return

        try:
            self.path.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            logger.warning("Could not remove download path reservation '%s'", self.path, exc_info=True)


def reserve_unique_download_path(path: str | Path) -> DownloadPathReservation:
    """Atomically claim the first unused exact filename on the filesystem.

    The supplied path must already contain the concrete media extension. Existing
    entries with other extensions do not collide. If the requested filename is
    occupied, ``-1``, ``-2``, and so on are inserted before the extension.

    The empty destination file itself is the reservation. ``O_EXCL`` makes the
    claim atomic across concurrent WireLoft workers and also respects any file or
    other filesystem entry created outside WireLoft. The downloader later writes
    to its normal temporary path and atomically replaces this placeholder on
    success.
    """
    requested = Path(path)
    requested.parent.mkdir(parents=True, exist_ok=True)

    for number in count(0):
        candidate = (
            requested
            if number == 0
            else requested.with_name(f"{requested.stem}-{number}{requested.suffix}")
        )
        try:
            fd = os.open(
                candidate,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o666,
            )
        except FileExistsError:
            continue

        try:
            reservation_stat = os.fstat(fd)
        except BaseException:
            try:
                os.close(fd)
            finally:
                try:
                    candidate.unlink()
                except OSError:
                    pass
            raise
        else:
            os.close(fd)

        return DownloadPathReservation(
            path=candidate,
            stat_dev=reservation_stat.st_dev,
            stat_ino=reservation_stat.st_ino,
        )

    raise RuntimeError("Could not allocate a unique download path")
