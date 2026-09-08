from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from backend.api.helpers import update_database_fields
from backend.api.models.show import *
from fastapi import HTTPException

from backend.db.models import Episode, EpisodeMediaDownload, Show
from task_manager.events.transactional import queue_event
from task_manager.scheduler.operation_factory import create_operation
from task_manager.scheduler.operations import (
    complete_operation,
    queue_operation_target_dispatch,
)

from .events import ShowAdded
from .operations import (
    ShowIndexOperation,
    ShowMetadataRefreshOperation,
    ShowRedownloadOperation,
    ShowSyncOperation,
)


def get_shows_list(s: Session) -> list[ShowAPIRead]:
    shows = (
        s.query(Show)
        .order_by(Show.title.asc())
        .all()
    )
    return [ShowAPIRead.model_validate(show) for show in shows]


def get_show(s: Session, show_slug: str) -> ShowAPIRead:
    show = (
        s.query(Show)
        .filter_by(slug=show_slug)
        .one_or_none()
    )

    if show is None:
        raise HTTPException(status_code=404, detail="Show not found")

    return ShowAPIRead.model_validate(show)


def create_show(s: Session, body: ShowAPICreate) -> ShowAPIRead:
    # Build model from validated Pydantic data
    data = body.model_dump(by_alias=True)

    show = Show(**data)
    s.add(show)
    s.flush()

    create_operation(s, ShowIndexOperation(show))
    queue_event(s, "show.added", ShowAdded(show))

    return ShowAPIRead.model_validate(show)


def update_show(s: Session, show_slug: str, body: ShowAPIUpdate) -> ShowAPIRead:
    show: Optional[Show] = (
        s.query(Show)
        .filter_by(slug=show_slug)
        .one_or_none()
    )
    if show is None:
        raise HTTPException(status_code=404, detail="Show not found")

    # Apply changes and flush
    update_database_fields(show, body)
    s.flush()

    queue_event(s, "show.updated", {
        "resource_id": show.id,
        "id": show.id,
        "slug": show.slug,
    })

    return ShowAPIRead.model_validate(show)


def delete_show(s: Session, show_slug: str) -> ShowAPIRead:
    show = (
        s.query(Show)
        .filter_by(slug=show_slug)
        .one_or_none()
    )
    if show is None:
        raise HTTPException(status_code=404, detail="Show not found")

    payload = ShowAPIRead.model_validate(show)

    queue_event(s, "show.deleted", {
        "resource_id": show.id,
        "id": show.id,
        "slug": show.slug,
    })

    s.delete(show)
    s.flush()

    return payload


def request_show_sync(s: Session, show_slug: str) -> dict[str, bool | str]:
    show = (
        s.query(Show)
        .filter_by(slug=show_slug)
        .one_or_none()
    )
    if show is None:
        raise HTTPException(status_code=404, detail="Show not found")

    operation = create_operation(s, ShowSyncOperation(show))
    queue_operation_target_dispatch(s, operation.id, operation.targets[0].slot_key)
    return {"queued": True, "operation_id": operation.id}


def request_show_metadata_refresh(
        s: Session,
        show_slug: str,
) -> dict[str, bool | int | str]:
    """Queue the normal metadata refresh flow for every episode in one show."""
    show = (
        s.query(Show)
        .filter_by(slug=show_slug)
        .one_or_none()
    )
    if show is None:
        raise HTTPException(status_code=404, detail="Show not found")

    episodes = (
        s.query(Episode)
        .filter_by(show_id=show.id)
        .all()
    )
    operation = create_operation(
        s,
        ShowMetadataRefreshOperation(show, episodes),
    )

    if not episodes:
        complete_operation(
            s,
            operation.id,
            summary=f"No episodes to refresh in {show.title}",
            data={"episodes_refreshed": 0, "episodes_requested": 0},
        )
    else:
        for episode in episodes:
            if queue_operation_target_dispatch(s, operation.id, f"episode:{episode.id}"):
                episode.metadata_is_final = False

    s.flush()
    return {
        "queued": bool(episodes),
        "episodes_queued": len(episodes),
        "operation_id": operation.id,
    }


def request_show_episode_redownload(
        s: Session,
        show_slug: str,
        local_media_profile_id: int | None,
) -> dict[str, bool | int | str]:
    """Queue replacement downloads for existing episode media on a show."""
    show = (
        s.query(Show)
        .filter_by(slug=show_slug)
        .one_or_none()
    )
    if show is None:
        raise HTTPException(status_code=404, detail="Show not found")

    local_media_profile_ids = [
        profile_id
        for (profile_id,) in (
            s.query(EpisodeMediaDownload.local_media_profile_id)
            .join(Episode, Episode.id == EpisodeMediaDownload.media_item_id)
            .filter(Episode.show_id == show.id)
            .distinct()
            .order_by(EpisodeMediaDownload.local_media_profile_id.asc())
            .all()
        )
    ]
    if not local_media_profile_ids:
        raise HTTPException(status_code=422, detail="This show has no downloaded episodes")

    if local_media_profile_id is None:
        selected_profile_count = len(local_media_profile_ids)
    elif local_media_profile_id not in local_media_profile_ids:
        raise HTTPException(
            status_code=422,
            detail="Local Media Profile has no downloaded episodes for this show",
        )
    else:
        selected_profile_count = 1

    operation = create_operation(
        s,
        ShowRedownloadOperation(
            show,
            local_media_profile_id=local_media_profile_id,
            selected_profile_count=selected_profile_count,
        ),
    )
    queue_operation_target_dispatch(s, operation.id, operation.targets[0].slot_key)
    return {
        "queued": True,
        "local_media_profiles_queued": selected_profile_count,
        "operation_id": operation.id,
    }
