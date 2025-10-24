from fastapi import APIRouter, status

from .service import *
from ....models.show import ShowAPIRead
from ....models.show_as_bundle import ShowAPICreateBundle
from backend.app import db_session
from backend.api.endpoints.tasks.service import trigger_now as trigger_task_now

router = APIRouter(prefix = "/as-bundle")


@router.post("", response_model=ShowAPIRead, status_code=status.HTTP_201_CREATED)
def show_create_as_bundle(body: ShowAPICreateBundle):
    """
    Create a new show with media- and download profiles in a single operation.

    Creates a show along with its associated download profiles (series or podcast) in one atomic transaction.
    This is a convenience endpoint for setting up a complete show configuration at once.
    Returns the created show with basic metadata.
    """
    with db_session() as s:
        try:
            result = create_show_bundle(s, body)
            s.commit()

            # After committing the new Show, trigger indexing of episodes
            try:
                trigger_task_now(definition_key="index_show_worker", resource_type="show", resource_id=result.id)
            except Exception:
                pass
            return result
        except Exception:
            s.rollback()
            raise
