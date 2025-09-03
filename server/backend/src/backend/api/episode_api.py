from fastapi import APIRouter

from backend.services.episode.service import get_episode_list, get_episode
from backend.services.episode.response_models import EpisodeItem

router = APIRouter()

@router.get("/list", response_model=list[EpisodeItem])
def episode_list(show_id: str):
    return get_episode_list(show_id)

@router.get("/{episode_slug}", response_model=EpisodeItem)
def episode_detail(show_id: str, episode_slug: str):
    return get_episode(show_id, episode_slug)
