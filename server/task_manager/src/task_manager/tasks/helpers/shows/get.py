from typing import Optional

from backend.db.models import Show, Episode

from sqlalchemy.orm import Session


def get_show_from_params(s: Session, *,
                         episode_id: Optional[int] = None,
                         episode_slug: Optional[str] = None,
                         show_id: Optional[int] = None,
                         show_slug: Optional[str] = None) -> Optional[Show]:
    if show_id is not None:
        return s.get(Show, show_id)
    if show_slug is not None:
        return s.query(Show).filter(Show.slug == show_slug).first()
    if episode_id is not None:
        return s.get(Episode, episode_id).show
    if episode_slug is not None:
        return s.query(Episode).filter(Episode.slug == episode_slug).first().show
    return None