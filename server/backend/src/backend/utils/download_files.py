from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def remove_download_artifacts(file_path: Optional[str]) -> None:
    """Remove a download's final file and every temporary form WireLoft uses.

    HLS/direct downloads write ``.part`` files, while video remuxing also uses
    ``.rawts`` and ``.rawts.part``. Cancellation can happen in any one of those
    phases, so cleanup must cover all four paths and be safe to repeat when the
    worker later observes the cancellation itself.
    """
    if not file_path:
        return

    paths = (
        Path(file_path),
        Path(file_path + ".part"),
        Path(file_path + ".rawts"),
        Path(file_path + ".rawts.part"),
    )
    for path in paths:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            # An in-flight writer can briefly keep a file open on some hosts.
            # The worker calls this helper again after observing cancellation.
            logger.warning("Could not remove cancelled download artifact '%s'", path, exc_info=True)
