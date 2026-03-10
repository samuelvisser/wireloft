from fastapi import APIRouter, status

from task_manager import events
from .as_bundle import show_as_bundle_router
from .as_view import show_view_router
from .service import get_shows_list, create_show, get_show, update_show, delete_show
from ..tasks.service import trigger_now as trigger_task_now
from ...models.show import ShowAPIRead, ShowAPICreate, ShowAPIUpdate
from backend.app import db_session

router = APIRouter(prefix="/shows", tags=["Shows"])

router.include_router(show_view_router)
router.include_router(show_as_bundle_router)

@router.get("", response_model=list[ShowAPIRead])
def show_list():
    """
    List all shows in the system.

    Returns a collection of all show records with their basic metadata.
    """
    with db_session() as s:
        return get_shows_list(s)


@router.post("", response_model=ShowAPIRead, status_code=status.HTTP_201_CREATED)
def show_create(body: ShowAPICreate) -> ShowAPIRead:
    """
    Create a new show entry.

    Adds a new show to the system with the provided metadata.
    Returns the created show with a generated slug identifier.
    """
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
    """
    Retrieve detailed information for a specific show.

    Returns complete show metadata including title, description, and configuration.
    """
    with db_session() as s:
        return get_show(s, show_slug)


@router.patch("/{show_slug}", response_model=ShowAPIRead)
def show_update(show_slug: str, body: ShowAPIUpdate):
    """
    Update an existing show's metadata.

    Partially updates show information with the provided fields.
    Only specified fields will be modified; omitted fields remain unchanged.
    """
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
    """
    Delete a show from the system.

    Permanently removes the specified show and its associated data.
    Returns the deleted show's information for confirmation.
    """
    with db_session() as s:
        try:
            result = delete_show(s, show_slug)
            s.commit()
            return result
        except Exception:
            s.rollback()
            raise