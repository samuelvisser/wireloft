from fastapi import APIRouter

from backend.services.episode.service import get_episode_list, get_episode
from backend.services.episode.response_models import EpisodeItemResponse

router = APIRouter()

@router.get("/list", response_model=list[EpisodeItemResponse])
def episode_list(show_slug: str):
    return get_episode_list(show_slug)

@router.get("/{episode_slug}", response_model=EpisodeItemResponse)
def episode_detail(show_slug: str, episode_slug: str):
    return get_episode(show_slug, episode_slug)
