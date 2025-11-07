from fastapi import APIRouter

from backend.api.endpoints.dailywire.episodes.service import *
from dailywire_api.records import DwEpisodeRecord, DwEpisodeDetailRecord


router = APIRouter(prefix="/episodes", tags=["DailyWire Episodes"])

@router.get("/by-show-slug/{show_slug}", response_model=list[DwEpisodeRecord])
def episodes_by_show_list(show_slug: str):
    return get_episodes_list_by_show(show_slug)


@router.get("/{episode_slug}", response_model=DwEpisodeDetailRecord)
def episode_detail(episode_slug: str):
    return get_episode_details(episode_slug)