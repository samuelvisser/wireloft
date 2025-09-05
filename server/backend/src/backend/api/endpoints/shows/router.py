from fastapi import APIRouter

from .service import *
from ...models.request import ShowCreateBody, ShowUpdateBody
from ...models.response import ShowItemResponse

router = APIRouter()

@router.get("", response_model=list[ShowItemResponse])
def show_list():
    return get_show_list()


@router.post("", response_model=ShowItemResponse)
def show_create(body: ShowCreateBody):
    return create_show(**body.model_dump())


@router.get("/{show_slug}", response_model=ShowItemResponse)
def show_detail(show_slug: str):
    return get_show(show_slug)


@router.patch("/{show_slug}", response_model=ShowItemResponse)
def show_update(show_slug: str, body: ShowUpdateBody):
    return update_show(show_slug, **body.model_dump(exclude_unset=True))


@router.delete("/{show_slug}", response_model=ShowItemResponse)
def show_delete(show_slug: str):
    return delete_show(show_slug)