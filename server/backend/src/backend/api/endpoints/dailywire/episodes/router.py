from fastapi import APIRouter

from backend.api.endpoints.dailywire.episodes.service import get_episodes_from_show_list
from dailywire_api.records import EpisodeRecord


router = APIRouter(prefix="/shows/{show_slug}/episodes", tags=["DailyWire Episodes"])

@router.get("", response_model=list[EpisodeRecord])
def episode_list(show_slug: str):
    return get_episodes_from_show_list(show_slug)


@router.get("/{episode_slug}", response_model=EpisodeRecord)
def episode_detail(show_slug: str, episode_slug: str):
    ...

