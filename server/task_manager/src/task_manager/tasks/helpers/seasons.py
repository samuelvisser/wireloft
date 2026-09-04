from backend.api.endpoints.seasons.service import create_season
from backend.api.models.season import SeasonAPICreate, SeasonAPIRead
from backend.db.models import Show
from backend.utils.season_ordering import order_initial_seasons
from sqlalchemy.orm import Session
from dailywire_api.records import DwSeasonRecord


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
    """Order Daily Wire seasons for a completely unindexed show."""
    return order_initial_seasons(seasons)


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