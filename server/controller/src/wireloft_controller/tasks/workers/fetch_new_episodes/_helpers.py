from typing import Optional, Sequence
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models import Show, Season, Episode
from wireloft_controller.tasks.helpers.episodes.mapper import EpisodeMapTuple
from wireloft_controller.tasks.helpers.episodes.status import is_published_final


def get_shows(s: Session, *, show_id: Optional[int], show_slug: Optional[str]) -> Sequence[Show]:
    # In case we're only interested in one show, get it from the database
    show: Optional[Show] = None
    if show_slug:
        show = s.execute(select(Show).where(Show.slug == show_slug)).scalar_one_or_none()
    elif show_id is not None:
        show = s.get(Show, show_id)

    if show is not None:
        shows: Sequence[Show] = [show]
    else:
        shows: Sequence[Show] = s.execute(select(Show)).scalars().all()
    return shows


def get_season_from_list_by_id(season_list: list[Season], season_id: int) -> Optional[Season]:
    for season in season_list:
        if season.id == season_id:
            return season
    return None


def contains_non_final_episode(ep_map: EpisodeMapTuple) -> bool:
    for _, eps in ep_map.items():
        for ep_tuple in eps:
            if not is_published_final(ep_tuple[1]):
                return True
    return False


def get_latest_ep_index(s: Session, *, show: Show) -> int:
    return s.execute(select(Episode.index).where(Episode.show_id == show.id).order_by(Episode.index.desc()).limit(1)).scalar()