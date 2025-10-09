from fastapi import APIRouter, status

from .service import *
from ...models.episode import *
from backend.app import db_session

router = APIRouter(prefix="/shows/{show_slug}/episodes", tags=["Episodes"])

@router.get("", response_model=list[EpisodeAPIRead])
def episode_list(show_slug: str):
    """
    List all episodes for a show.
    """
    with db_session() as s:
        return get_episodes_list(s, show_slug)


@router.post("", response_model=EpisodeAPIRead, status_code=status.HTTP_201_CREATED)
def episode_create(body: EpisodeAPICreate):
    with db_session() as s:
        try:
            result = create_episode(s, body)
            s.commit()
            return result
        except Exception:
            s.rollback()
            raise


@router.get("/{episode_slug}", response_model=EpisodeAPIRead)
def episode_detail(show_slug: str, episode_slug: str):
    with db_session() as s:
        return get_episode(s, show_slug, episode_slug)


@router.patch("/{episode_slug}", response_model=EpisodeAPIRead)
def episode_update(show_slug: str, episode_slug: str, body: EpisodeAPIUpdate):
    with db_session() as s:
        try:
            result = update_episode(s, show_slug, episode_slug, body)
            s.commit()
            return result
        except Exception:
            s.rollback()
            raise


@router.delete("/{episode_slug}", response_model=EpisodeAPIRead)
def episode_delete(show_slug: str, episode_slug: str):
    with db_session() as s:
        try:
            result = delete_episode(s, show_slug, episode_slug)
            s.commit()
            return result
        except Exception:
            s.rollback()
            raise