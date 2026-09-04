from __future__ import annotations

import json
from typing import Optional

from sqlalchemy.orm import Session

from backend.api.helpers import update_database_fields
from backend.api.models.show import *
from fastapi import HTTPException

from backend.db.models import DownloadProfileBase, Episode, Show
from task_manager.events.transactional import queue_event
from task_manager.scheduler.operations import (
    OperationTargetSpec,
    complete_operation,
    create_operation,
    operation_target_needs_dispatch,
    queue_operation_target_dispatch,
)


SYNC_LOG_META_KEY = "episode_sync_log"
SYNC_LOG_LIMIT = 10
SHOW_REDOWNLOAD_EPISODES_REQUESTED_EVENT = "show.redownload_episodes_requested"
_FETCH_EPISODES_TASK_KEY = "fetch_new_episodes"
_REFRESH_METADATA_TASK_KEY = "refresh_episode_metadata_worker"
_REDOWNLOAD_TASK_KEY = "redownload_show_episodes_worker"


def _show_operation_context(show: Show) -> dict[str, str]:
    return {
        "show_slug": show.slug,
        "show_title": show.title,
    }


def _single_show_target(task_key: str, show: Show, **task_kwargs) -> OperationTargetSpec:
    return OperationTargetSpec(
        task_key=task_key,
        resource_type="show",
        resource_id=show.id,
        task_kwargs=task_kwargs,
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

    create_operation(
        s,
        kind="show.index",
        resource_type="show",
        resource_id=show.id,
        title=show.title,
        targets=[_single_show_target(_FETCH_EPISODES_TASK_KEY, show)],
        context=_show_operation_context(show),
    )
    queue_event(s, "show.added", {
        "resource_id": show.id,
        "id": show.id,
        "slug": show.slug,
        "title": show.title,
    })

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

    target = _single_show_target(_FETCH_EPISODES_TASK_KEY, show)
    operation = create_operation(
        s,
        kind="show.sync",
        resource_type="show",
        resource_id=show.id,
        title=show.title,
        targets=[target],
        context=_show_operation_context(show),
    )
    if operation_target_needs_dispatch(s, operation.id, target.resolved_slot_key()):
        queue_event(s, "show.sync_requested", {
            "resource_id": show.id,
            "id": show.id,
            "slug": show.slug,
        })
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
    targets = [
        OperationTargetSpec(
            task_key=_REFRESH_METADATA_TASK_KEY,
            resource_type="episode",
            resource_id=episode.id,
            task_kwargs={"refresh": True},
            slot_key=f"episode:{episode.id}",
        )
        for episode in episodes
    ]
    operation = create_operation(
        s,
        kind="show.refresh_metadata",
        resource_type="show",
        resource_id=show.id,
        title=show.title,
        targets=targets,
        context={
            **_show_operation_context(show),
            "episodes_requested": len(episodes),
        },
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
        download_profile_id: int | None,
) -> dict[str, bool | int | str]:
    """Queue a destructive re-download for one or every Download Profile on a show."""
    show = (
        s.query(Show)
        .filter_by(slug=show_slug)
        .one_or_none()
    )
    if show is None:
        raise HTTPException(status_code=404, detail="Show not found")

    attached_profiles = (
        s.query(DownloadProfileBase)
        .filter_by(show_id=show.id)
        .order_by(DownloadProfileBase.id.asc())
        .all()
    )
    if not attached_profiles:
        raise HTTPException(status_code=422, detail="This show has no Download Profiles")

    if download_profile_id is None:
        selected_profile_count = len(attached_profiles)
    else:
        selected_profile = next(
            (profile for profile in attached_profiles if profile.id == download_profile_id),
            None,
        )
        if selected_profile is None:
            raise HTTPException(status_code=422, detail="Download Profile is not attached to this show")
        selected_profile_count = 1

    target = _single_show_target(
        _REDOWNLOAD_TASK_KEY,
        show,
        download_profile_id=download_profile_id,
    )
    operation = create_operation(
        s,
        kind="show.redownload_episodes",
        resource_type="show",
        resource_id=show.id,
        title=show.title,
        targets=[target],
        context={
            **_show_operation_context(show),
            "download_profiles_requested": selected_profile_count,
        },
    )
    if operation_target_needs_dispatch(s, operation.id, target.resolved_slot_key()):
        queue_event(s, SHOW_REDOWNLOAD_EPISODES_REQUESTED_EVENT, {
            "resource_id": show.id,
            "id": show.id,
            "slug": show.slug,
            "download_profile_id": download_profile_id,
        })
    return {
        "queued": True,
        "download_profiles_queued": selected_profile_count,
        "operation_id": operation.id,
    }


def get_show_sync_log(s: Session, show_slug: str) -> list[dict]:
    show = (
        s.query(Show)
        .filter_by(slug=show_slug)
        .one_or_none()
    )
    if show is None:
        raise HTTPException(status_code=404, detail="Show not found")

    raw = show.get_meta(SYNC_LOG_META_KEY)
    if not raw:
        return []

    try:
        history = json.loads(raw)
    except (TypeError, ValueError):
        return []

    if not isinstance(history, list):
        return []
    return history[:SYNC_LOG_LIMIT]
