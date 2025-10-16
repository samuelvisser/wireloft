from fastapi import APIRouter

from backend.api.endpoints.dailywire.episodes.service import *
from dailywire_api.records import EpisodeRecord
from dailywire_api.records.EpisodeDetailRecord import EpisodeDetailRecord

router = APIRouter(prefix="/episodes", tags=["DailyWire Episodes"])

@router.get("/by-show-slug/{show_slug}", response_model=list[EpisodeRecord])
def episodes_by_show_list(show_slug: str):
    return get_episodes_from_show_list(show_slug)


@router.get("/episodes/{episode_slug}", response_model=EpisodeDetailRecord)
def episode_detail(episode_slug: str):
    return get_episode_details(episode_slug)