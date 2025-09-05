from fastapi import APIRouter

from .service import *
from ...models.response import EpisodeItemResponse

router = APIRouter()

@router.get("", response_model=list[EpisodeItemResponse])
def episode_list(show_slug: str):
    return get_episode_list(show_slug)

@router.post("", response_model=EpisodeItemResponse)
def episode_create(show_slug: str):
    # Create an episode
    ...

@router.get("/{episode_slug}", response_model=EpisodeItemResponse)
def episode_detail(show_slug: str, episode_slug: str):
    return get_episode(show_slug, episode_slug)

@router.patch("/{episode_slug}", response_model=EpisodeItemResponse)
def episode_update(show_slug: str, episode_slug: str):
    # Update the episode
    ...

@router.delete("/{episode_slug}", response_model=EpisodeItemResponse)
def episode_delete(show_slug: str, episode_slug: str):
    # Delete the episode
    ...