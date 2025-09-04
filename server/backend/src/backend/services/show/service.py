from fastapi import HTTPException

from backend.app import db_session
from backend.db.models import Show
from .response_models import ShowItemResponse


def get_show_list() -> list[ShowItemResponse]:
    with db_session() as s:
        shows = (
            s.query(Show)
            .order_by(Show.id)
            .all()
        )
        payload = [
            ShowItemResponse.model_validate(sh, from_attributes=True)
            for sh in shows
        ]
        return payload


def get_show(show_slug: str) -> ShowItemResponse:
    with db_session() as s:
        show = s.query(Show).filter_by(slug=show_slug).one_or_none()
        if show is None:
            raise HTTPException(status_code=404, detail="Show not found")

        payload = ShowItemResponse.model_validate(show, from_attributes=True)
        return payload
