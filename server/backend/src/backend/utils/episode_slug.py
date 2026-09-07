from __future__ import annotations


NO_SHOW_TODAY_SLUG_FRAGMENT = "no-show-today"


def is_no_show_today_slug(slug: str | None) -> bool:
    """Return whether a Daily Wire slug identifies a No Show Today placeholder."""
    return bool(slug) and NO_SHOW_TODAY_SLUG_FRAGMENT in slug.casefold()
