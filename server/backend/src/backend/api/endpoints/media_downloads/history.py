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


def _task_result_data(item: dict) -> dict:
    result = item.get("result")
    if not isinstance(result, dict):
        return {}
    data = result.get("data")
    return data if isinstance(data, dict) else {}


def _task_is_redownload(item: dict) -> bool:
    inputs = item.get("inputs")
    if isinstance(inputs, dict) and isinstance(inputs.get("is_redownload"), bool):
        return inputs["is_redownload"]
    return _task_result_data(item).get("is_redownload") is True


def _task_status(item: dict) -> str:
    status = item.get("status")
    if status == "FAILED":
        return "error"
    if status == "CANCELED":
        return "cancelled"
    if status == "RUNNING":
        return "downloading"
    if status == "SUCCEEDED":
        return "redownloaded" if _task_is_redownload(item) else "downloaded"
    return "pending"


def _task_error(item: dict) -> str | None:
    if item.get("last_error"):
        return str(item["last_error"])
    if item.get("status") == "FAILED" and item.get("message"):
        return str(item["message"])
    return None


def _task_history_entry(item: dict) -> dict:
    return {
        "key": f"task-{item['id']}",
        "status": _task_status(item),
        "activity": "Redownload" if _task_is_redownload(item) else "Initial download",
        "occurred_at": item.get("finished_at") or item.get("started_at"),
        "error": _task_error(item),
    }


def _history_time(item: dict) -> datetime:
    return item.get("occurred_at") or _MIN_HISTORY_TIME


def get_media_download_history(
    s: Session,
    media_download_id: int,
    *,
    offset: int = 0,
    limit: int = 50,
) -> dict:
    """Return normalized download history independent of its storage source."""
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
    task_items = [_task_history_entry(item) for item in task_page["items"]]

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
            "key": f"event-{event.id}",
            "status": event.event_type,
            "activity": "WireLoft",
            "occurred_at": event.occurred_at,
            "error": None,
        }
        for event in events
    ]

    items: list[dict] = [*task_items, *event_items]
    if include_artifact_problem:
        items.append({
            "key": "artifact-current",
            "status": download.artifact_status,
            "activity": "File watcher",
            "occurred_at": download.updated_at,
            "error": download.artifact_error,
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
