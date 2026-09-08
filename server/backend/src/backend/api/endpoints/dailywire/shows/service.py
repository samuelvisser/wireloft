from __future__ import annotations

from threading import Lock
from time import monotonic
from typing import Optional

from pydantic import ValidationError

from dailywire_api.dw_api.client import MiddlewareClient, MiddlewareAPIError
from dailywire_api.records import DwShowRecord
from dailywire_api.records.DwShowRecord import ProbableShowType
from dailywire_authorisation import DeviceAuthClient


_SHOW_TYPE_CACHE_SECONDS = 30 * 60
_show_type_cache: dict[str, tuple[float, ProbableShowType]] = {}
_show_type_cache_lock = Lock()


def _middleware_client() -> MiddlewareClient:
    tokens = DeviceAuthClient().get_token()
    return MiddlewareClient(
        access_token=tokens.access_token if tokens else None,
        pace_requests=False,
    )


def get_show(
    show_slug: str,
    *,
    membership_plan: Optional[str] = None,
) -> DwShowRecord:
    """Fetch a DailyWire show by slug from the middleware API and normalize it.

    Parameters
    - show_slug: The DailyWire show slug (e.g., "the-ben-shapiro-show").
    - membership_plan: Optional membership plan that can affect content selection.
    """
    return _middleware_client().get_show_page(slug=show_slug, membership_plan=membership_plan)


def get_show_type_classifications(show_slugs: list[str]) -> dict[str, ProbableShowType]:
    """Return DwShowRecord's existing best-effort type classification for each slug.

    Catalog rows do not contain the season/episode data used by ``probable_show_type``.
    Fetch the same normalized Daily Wire show model used by the Add Show wizard and
    expose only that model's result. Successful classifications are cached because the
    result is stable enough for interactive browsing.
    """
    slugs = list(dict.fromkeys(slug.strip() for slug in show_slugs if slug.strip()))
    if not slugs:
        return {}

    now = monotonic()
    result: dict[str, ProbableShowType] = {}
    missing: list[str] = []
    with _show_type_cache_lock:
        for slug in slugs:
            cached = _show_type_cache.get(slug)
            if cached and now - cached[0] < _SHOW_TYPE_CACHE_SECONDS:
                result[slug] = cached[1]
            else:
                missing.append(slug)

    if not missing:
        return result

    client = _middleware_client()
    for slug in missing:
        try:
            classification = client.get_show_page(slug=slug).probable_show_type
        except (MiddlewareAPIError, ValidationError):
            # A single stale/unavailable catalog row should not make the whole browser
            # filter fail. Keep the model's explicit best-effort semantics by treating
            # that one result as unknown, but do not cache the failure so it can recover.
            result[slug] = ProbableShowType.unknown
            continue

        result[slug] = classification
        with _show_type_cache_lock:
            _show_type_cache[slug] = (monotonic(), classification)

    return result
