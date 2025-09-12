from fastapi import APIRouter

from dailywire_api.records import EpisodeRecord

router = APIRouter()

@router.get("", response_model=list[EpisodeRecord])
def episode_list(show_slug: str):
    ...

@router.get("/{episode_slug}", response_model=EpisodeRecord)
def episode_detail(show_slug: str, episode_slug: str):
    ...

