from fastapi import APIRouter

from .service import *
from ...models.episode import EpisodeAPIRead

router = APIRouter()

@router.get("", response_model=list[EpisodeAPIRead])
def episode_list(show_slug: str):
    return get_episodes_list(show_slug)


@router.post("", response_model=EpisodeAPIRead)
def episode_create(body: EpisodeAPICreate):
    return create_episode(body)


@router.get("/{episode_slug}", response_model=EpisodeAPIRead)
def episode_detail(show_slug: str, episode_slug: str):
    return get_episode(show_slug, episode_slug)


@router.patch("/{episode_slug}", response_model=EpisodeAPIRead)
def episode_update(show_slug: str, episode_slug: str, body: EpisodeAPIUpdate):
    return update_episode(show_slug, episode_slug, body)


@router.delete("/{episode_slug}", response_model=EpisodeAPIRead)
def episode_delete(show_slug: str, episode_slug: str):
    return delete_episode(show_slug, episode_slug)