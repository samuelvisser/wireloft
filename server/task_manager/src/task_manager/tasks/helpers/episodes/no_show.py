from __future__ import annotations

import re

_NO_SHOW_TODAY_PATTERN = re.compile(r"no show today", re.IGNORECASE)


def is_no_show_today_title(title: str) -> bool:
    """Whether an episode title marks it as a "No Show Today" placeholder.

    Daily Wire publishes these on days a show doesn't air: a real feed entry
    with a title/thumbnail announcing there's nothing new, but no actual media
    behind it - its own episode-details endpoint 404s for it. It should never
    be queued for download, and once Daily Wire removes it there is nothing
    left worth keeping a local record of, unlike a real episode being pulled.
    """
    return bool(title) and bool(_NO_SHOW_TODAY_PATTERN.search(title))
