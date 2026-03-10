from backend.api.endpoints.seasons.service import create_season
from backend.api.models.season import SeasonAPICreate, SeasonAPIRead
from backend.db.models import Show
from dailywire_api.records import DwSeasonRecord


def create_season_by_dw_season(s, *, show: Show, dw_season: DwSeasonRecord) -> SeasonAPIRead:

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