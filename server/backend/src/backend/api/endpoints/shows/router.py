from fastapi import APIRouter, status

from .as_bundle import show_as_bundle_router
from .as_view import show_view_router
from .service import get_shows_list, create_show, get_show, update_show, delete_show
from ...models.show import ShowAPIRead, ShowAPICreate, ShowAPIUpdate
from backend.app import db_session

router = APIRouter(prefix="/shows", tags=["Shows"])

router.include_router(show_view_router, prefix = "/as-view")
router.include_router(show_as_bundle_router, prefix = "/as-bundle")

@router.get("", response_model=list[ShowAPIRead])
def show_list():
    with db_session() as s:
        return get_shows_list(s)


@router.post("", response_model=ShowAPIRead, status_code=status.HTTP_201_CREATED)
def show_create(body: ShowAPICreate):
    with db_session() as s:
        try:
            result = create_show(s, body)
            s.commit()
            return result
        except Exception:
            s.rollback()
            raise


@router.post("/bundle", response_model=ShowAPIRead)
def show_create(body: ShowAPICreate):
    with db_session() as s:
        try:
            result = create_show(s, body)
            s.commit()
            return result
        except Exception:
            s.rollback()
            raise


@router.get("/{show_slug}", response_model=ShowAPIRead)
def show_detail(show_slug: str):
    with db_session() as s:
        return get_show(s, show_slug)


@router.patch("/{show_slug}", response_model=ShowAPIRead)
def show_update(show_slug: str, body: ShowAPIUpdate):
    with db_session() as s:
        try:
            result = update_show(s, show_slug, body)
            s.commit()
            return result
        except Exception:
            s.rollback()
            raise


@router.delete("/{show_slug}", response_model=ShowAPIRead)
def show_delete(show_slug: str):
    with db_session() as s:
        try:
            result = delete_show(s, show_slug)
            s.commit()
            return result
        except Exception:
            s.rollback()
            raise