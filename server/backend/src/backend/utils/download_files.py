from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def remove_download_artifacts(file_path: Optional[str]) -> None:
    """Remove a download's owned final file and every temporary form WireLoft uses.

    HLS/direct downloads write ``.part`` files, while video remuxing also uses
    ``.rawts`` and ``.rawts.part``. Cancellation can happen in any one of those
    phases, so cleanup must cover all four paths and be safe to repeat when the
    worker later observes the cancellation itself.

    A path ending in the Local Media Profile ``.ext`` marker is unresolved: no
    download attempt has claimed that concrete filesystem name yet. Treat it as
    non-owned so cancellation/delete can never remove an unrelated real ``.ext``
    file while temporary-mode bytes are being staged elsewhere.
    """
    if not file_path:
        return

    base_path = Path(file_path)
    if base_path.suffix == ".ext":
        return

    paths = (
        base_path,
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