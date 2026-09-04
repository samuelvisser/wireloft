import re

from backend.api.endpoints.seasons.service import create_season
from backend.api.models.season import SeasonAPICreate, SeasonAPIRead
from backend.db.models import Show
from sqlalchemy.orm import Session
from dailywire_api.records import DwSeasonRecord


_YEAR_SEASON_PATTERNS = (
    re.compile(r"(?:^|-)season-((?:19|20)\d{2})(?:-|$)", re.IGNORECASE),
    re.compile(r"(?:^|-)((?:19|20)\d{2})-season(?:-|$)", re.IGNORECASE),
)
_NUMBERED_SEASON_PATTERN = re.compile(
    r"(?:^|-)season-(\d+)(?:-season)?(?:-|$)",
    re.IGNORECASE,
)


def select_dw_seasons_to_create(
    *,
    existing_season_slugs: set[str],
    seasons: list[DwSeasonRecord],
) -> list[DwSeasonRecord]:
    """Select seasons to insert without ever changing an existing index."""
    if not existing_season_slugs:
        return order_initial_dw_seasons(seasons)

    # After initial indexing, discovery order is authoritative. New seasons only
    # receive the next index; existing season indices are never recalculated.
    return [season for season in seasons if season.slug not in existing_season_slugs]


def order_initial_dw_seasons(seasons: list[DwSeasonRecord]) -> list[DwSeasonRecord]:
    """Return the deterministic season order used only for a show's first index.

    Daily Wire usually returns seasons oldest-to-newest, but some shows return
    numbered seasons in the wrong order. Preserve unstructured seasons such as
    ``Extras`` in API order at the start, then sort recognizable numbered or
    year-based seasons ascending by their value.
    """
    decorated: list[tuple[tuple[int, int, int], DwSeasonRecord]] = []
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


def create_season_by_dw_season(s: Session, *, show: Show, dw_season: DwSeasonRecord) -> SeasonAPIRead:

    last_index = show.seasons[0].index if len(show.seasons) > 0 else 0
    data = {
        **dw_season.model_dump(mode="python", by_alias=False),
        **{
            "show_id": show.id,
            "index": last_index + 1,
        }
    }

    seasonApi = SeasonAPICreate.model_validate(data)
    return create_season(s, seasonApi, update_show_profiles=True)