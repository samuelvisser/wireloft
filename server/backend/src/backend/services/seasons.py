from __future__ import annotations

from sqlalchemy.orm import Session

from backend.db.models import Season
from backend.types.season_types import SeasonType
from backend.types.show_types import ShowType
from backend.utils.season_ordering import season_type_from_name
from task_manager.events.transactional import queue_event


def create_season_record(
    s: Session,
    *,
    show_id: int,
    index: int,
    slug: str,
    name: str,
    update_show_profiles: bool = False,
) -> Season:
    """Create one persistent season without depending on an API request model."""
    season_type = season_type_from_name(name)
    if season_type is SeasonType.EXTRA:
        season_number = 0
    else:
        season_number = max(
            (
                existing.season_number
                for existing in s.query(Season).filter(Season.show_id == show_id)
                if existing.season_type == SeasonType.NORMAL.value
            ),
            default=0,
        ) + 1

    season = Season(
        show_id=show_id,
        index=index,
        slug=slug,
        name=name,
        season_type=season_type.value,
        season_number=season_number,
    )
    s.add(season)
    s.flush()

    if update_show_profiles and season.show.type == ShowType.SERIES.value:
        for profile in season.show.download_profiles:
            if profile.include_upcoming_seasons:
                profile.seasons.append(season)
        s.flush()

    queue_event(
        s,
        "season.added",
        {
            "resource_id": season.id,
            "id": season.id,
            "slug": season.slug,
            "show_id": season.show_id,
        },
    )
    return season
