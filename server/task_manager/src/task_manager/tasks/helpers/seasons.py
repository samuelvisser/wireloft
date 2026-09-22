from backend.db.models import Season, Show
from backend.services.seasons import create_season_record
from dailywire_api.records import DwSeasonRecord
from sqlalchemy.orm import Session


def create_season_by_dw_season(
    s: Session,
    *,
    show: Show,
    dw_season: DwSeasonRecord,
) -> Season:
    last_index = show.seasons[0].index if show.seasons else 0
    next_index = last_index + 1
    return create_season_record(
        s,
        show_id=show.id,
        index=next_index,
        slug=dw_season.slug,
        name=dw_season.name,
        update_show_profiles=True,
    )
