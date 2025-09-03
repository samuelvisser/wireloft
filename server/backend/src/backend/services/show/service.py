from fastapi import HTTPException

from backend.app import db_session
from backend.db.models import Show
from .response_models import ShowItem


def get_show_list() -> list[ShowItem]:
    with db_session() as s:
        shows = (
            s.query(Show)
            .order_by(Show.id)
            .all()
        )

        payload = [
            ShowItem(
                id=sh.id,
                slug=sh.slug,
                title=sh.title,
                author=sh.author_name,
                years="unknown",
            )
            for sh in shows
        ]
        return payload


def get_show(show_id: int) -> ShowItem:
    with db_session() as s:
        show = s.query(Show).filter_by(id=show_id).one_or_none()
        if show is None:
            raise HTTPException(status_code=404, detail="Show not found")
        desc = show.description
        prefix = "Years: "
        years = desc[len(prefix):] if (isinstance(desc, str) and desc.startswith(prefix)) else desc
        payload = ShowItem(
            id=show.id,
            slug=show.slug,
            title=show.title,
            author=show.author_name,
            years=years,
        )
        return payload
