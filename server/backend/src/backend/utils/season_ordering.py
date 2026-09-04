from __future__ import annotations

import re
from typing import Protocol, Sequence, TypeVar


class SeasonWithSlug(Protocol):
    slug: str


SeasonT = TypeVar("SeasonT", bound=SeasonWithSlug)

_YEAR_SEASON_PATTERNS = (
    re.compile(r"(?:^|-)season-((?:19|20)\d{2})(?:-|$)", re.IGNORECASE),
    re.compile(r"(?:^|-)((?:19|20)\d{2})-season(?:-|$)", re.IGNORECASE),
)
_NUMBERED_SEASON_PATTERN = re.compile(
    r"(?:^|-)season-(\d+)(?:-season)?(?:-|$)",
    re.IGNORECASE,
)


def order_initial_seasons(seasons: Sequence[SeasonT]) -> list[SeasonT]:
    """Return deterministic season order for the moment a show is first created.

    Daily Wire normally returns seasons oldest-to-newest, but some shows return
    numbered or year-based seasons out of order. Unstructured seasons such as
    ``Extras`` stay first in their API order. Recognizable numbered/year seasons
    follow, sorted ascending by the number encoded in their slug.
    """
    decorated: list[tuple[tuple[int, int, int], SeasonT]] = []
    for api_position, season in enumerate(seasons):
        structured_value = _structured_season_value(season.slug)
        if structured_value is None:
            key = (0, api_position, api_position)
        else:
            key = (1, structured_value, api_position)
        decorated.append((key, season))

    decorated.sort(key=lambda item: item[0])
    return [season for _, season in decorated]


def _structured_season_value(slug: str) -> int | None:
    for pattern in _YEAR_SEASON_PATTERNS:
        match = pattern.search(slug)
        if match:
            return int(match.group(1))

    match = _NUMBERED_SEASON_PATTERN.search(slug)
    if match:
        return int(match.group(1))

    return None
