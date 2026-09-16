from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.api.endpoints.tasks.service import query_ledger
from backend.db.models.media_download import MediaDownloadBase, MediaDownloadEvent
from backend.types.download_profile_types import MediaDownloadArtifactStatus
from backend.types.media_types import MediaType
from task_manager.scheduler.types import ResourceType


_PROBLEM_ARTIFACT_STATUSES = {
    MediaDownloadArtifactStatus.MISSING.value,
    MediaDownloadArtifactStatus.CORRUPTED.value,
}
_MIN_HISTORY_TIME = datetime.min.replace(tzinfo=timezone.utc)


def _download_definition_key(download: MediaDownloadBase) -> str:
    if download.type == MediaType.EPISODE.value:
        return "download_episode"
    if download.type in {MediaType.MOVIE.value, MediaType.MOVIE_EXTRA.value}:
        return "download_movie"
    raise HTTPException(status_code=422, detail=f"Unsupported media download type '{download.type}'")


def _history_time(item: dict) -> datetime:
    if item["source"] == "task":
        return item.get("finished_at") or item.get("started_at") or _MIN_HISTORY_TIME
    if item["source"] == "event":
        return item["occurred_at"]
    return item["observed_at"]


def get_media_download_history(
    s: Session,
    media_download_id: int,
    *,
    offset: int = 0,
    limit: int = 50,
) -> dict:
    """Combine download TaskRuns, artifact events and the current problem state."""
    download = s.get(MediaDownloadBase, media_download_id)
    if download is None:
        raise HTTPException(status_code=404, detail="Media download not found")

    include_artifact_problem = download.artifact_status in _PROBLEM_ARTIFACT_STATUSES
    fetch_limit = offset + limit

    task_page = query_ledger(
        s,
        definition_key=_download_definition_key(download),
        resource_type=ResourceType.MEDIA_DOWNLOAD.value,
        resource_ids=[media_download_id],
        order_by="started_at",
        order="desc",
        offset=0,
        limit=fetch_limit,
    )
    task_items = [{"source": "task", **item} for item in task_page["items"]]

    event_total = int(s.scalar(
        select(func.count(MediaDownloadEvent.id)).where(
            MediaDownloadEvent.media_download_id == media_download_id,
        )
    ) or 0)
    events = list(s.scalars(
        select(MediaDownloadEvent)
        .where(MediaDownloadEvent.media_download_id == media_download_id)
        .order_by(MediaDownloadEvent.occurred_at.desc(), MediaDownloadEvent.id.desc())
        .limit(fetch_limit)
    ))
    event_items = [
        {
            "source": "event",
            "id": event.id,
            "event_type": event.event_type,
            "file_path": event.file_path,
            "occurred_at": event.occurred_at,
        }
        for event in events
    ]

    items: list[dict] = [*task_items, *event_items]
    if include_artifact_problem:
        items.append({
            "source": "artifact",
            "artifact_status": download.artifact_status,
            "artifact_error": download.artifact_error,
            "file_path": download.file_path,
            "observed_at": download.updated_at,
        })

    items.sort(key=_history_time, reverse=True)
    items = items[offset:offset + limit]

    total = int(task_page["total"]) + event_total + (1 if include_artifact_problem else 0)
    return {
        "items": items,
        "total": total,
        "offset": offset,
        "limit": limit,
        "has_more": offset + len(items) < total,
    }
