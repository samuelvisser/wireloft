from fastapi import APIRouter, status

from .with_profiles import show_with_profile_router
from .views import show_view_router
from .service import *
from ...models.show import *

router = APIRouter()

router.include_router(show_view_router, prefix = "/views")
router.include_router(show_with_profile_router, prefix = "/with-profiles")

@router.get("", response_model=list[ShowAPIRead])
def show_list():
    return get_shows_list()


@router.post("", response_model=ShowAPIRead, status_code=status.HTTP_201_CREATED)
def show_create(body: ShowAPICreate):
    return create_show(body)


@router.post("/bundle", response_model=ShowAPIRead)
def show_create(body: ShowAPICreate):
    return create_show(body)


@router.get("/{show_slug}", response_model=ShowAPIRead)
def show_detail(show_slug: str):
    return get_show(show_slug)


@router.patch("/{show_slug}", response_model=ShowAPIRead)
def show_update(show_slug: str, body: ShowAPIUpdate):
    return update_show(show_slug, body)


@router.delete("/{show_slug}", response_model=ShowAPIRead)
def show_delete(show_slug: str):
    return delete_show(show_slug)