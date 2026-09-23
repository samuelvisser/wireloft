from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Optional

from dailywire_downloader import hls_asset_marker, hls_asset_root

logger = logging.getLogger(__name__)


def remove_download_artifacts(
    file_path: Optional[str],
    thumbnail_path: Optional[str] = None,
) -> None:
    """Remove a download's owned final files and every temporary form WireLoft uses.

    HLS/direct downloads write ``.part`` files, while video remuxing also uses
    ``.rawts`` and ``.rawts.part``. Thumbnail embedding has its own temporary
    output, and sidecar thumbnails are tracked explicitly on MediaDownload.
    Cancellation can happen in any one of those phases, so cleanup must cover all
    owned paths and be safe to repeat when the worker later observes cancellation.

    A media path ending in the Local Media Profile ``.ext`` marker is unresolved:
    no download attempt has claimed that concrete filesystem name yet. Treat it as
    non-owned so cancellation/delete can never remove an unrelated real ``.ext``
    file while temporary-mode bytes are being staged elsewhere.
    """
    if file_path:
        base_path = Path(file_path)
        if base_path.suffix != ".ext":
            paths = (
                base_path,
                Path(file_path + ".part"),
                Path(file_path + ".rawts"),
                Path(file_path + ".rawts.part"),
                Path(file_path + ".thumbnail.part"),
            )
            for path in paths:
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    # An in-flight writer can briefly keep a file open on some hosts.
                    # The worker calls this helper again after observing cancellation.
                    logger.warning("Could not remove cancelled download artifact '%s'", path, exc_info=True)

            if base_path.suffix.lower() == ".m3u8":
                asset_root = hls_asset_root(base_path)
                directories = (
                    (asset_root, hls_asset_marker(base_path)),
                    (
                        Path(f"{asset_root}.part"),
                        Path(f"{asset_root}.part") / ".wireloft-hls-bundle",
                    ),
                )
                for directory, marker in directories:
                    if not marker.is_file():
                        continue
                    try:
                        shutil.rmtree(directory)
                    except FileNotFoundError:
                        pass
                    except OSError:
                        logger.warning(
                            "Could not remove HLS download assets '%s'",
                            directory,
                            exc_info=True,
                        )

    if thumbnail_path:
        for path in (Path(thumbnail_path), Path(thumbnail_path + ".part")):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                logger.warning("Could not remove thumbnail artifact '%s'", path, exc_info=True)
