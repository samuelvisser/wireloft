from __future__ import annotations

import re
from typing import Protocol, Sequence, TypeVar

from backend.types.season_types import SeasonType


class SeasonWithNameAndSlug(Protocol):
    name: str
    slug: str


SeasonT = TypeVar("SeasonT", bound=SeasonWithNameAndSlug)

_EXTRAS_NAME_PATTERN = re.compile(r"\bextras?\b", re.IGNORECASE)
_YEAR_SEASON_PATTERNS = (
    re.compile(r"(?:^|-)season-((?:19|20)\d{2})(?:-|$)", re.IGNORECASE),
    re.compile(r"(?:^|-)((?:19|20)\d{2})-season(?:-|$)", re.IGNORECASE),
)
_NUMBERED_SEASON_PATTERN = re.compile(
    r"(?:^|-)season-(\d+)(?:-season)?(?:-|$)",
    re.IGNORECASE,
)


def season_type_from_name(name: str) -> SeasonType:
    """Infer The Daily Wire season semantics from its human-readable name."""
    return (
        SeasonType.EXTRA
        if _EXTRAS_NAME_PATTERN.search(name or "")
        else SeasonType.NORMAL
    )


def order_initial_seasons(seasons: Sequence[SeasonT]) -> list[SeasonT]:
    """Return deterministic persistent season order for a newly added show.

    This deliberately preserves WireLoft's existing internal-index behavior:
    unstructured slugs stay first in The Daily Wire API order, while recognizable
    numbered/year slugs follow in ascending order. Semantic season numbering is
    handled separately by season_type/season_number so an Extras name can override
    a misleading numbered slug without changing the internal index.
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
