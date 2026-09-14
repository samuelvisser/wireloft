from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.api.endpoints.tasks.service import query_ledger
from backend.db.models.media_download import MediaDownloadBase
from backend.types.download_profile_types import MediaDownloadArtifactStatus
from backend.types.media_types import MediaType
from task_manager.scheduler.types import ResourceType


_PROBLEM_ARTIFACT_STATUSES = {
    MediaDownloadArtifactStatus.MISSING.value,
    MediaDownloadArtifactStatus.CORRUPTED.value,
}


def _download_definition_key(download: MediaDownloadBase) -> str:
    if download.type == MediaType.EPISODE.value:
        return "download_episode"
    if download.type in {MediaType.MOVIE.value, MediaType.MOVIE_EXTRA.value}:
        return "download_movie"
    raise HTTPException(status_code=422, detail=f"Unsupported media download type '{download.type}'")


def get_media_download_history(
    s: Session,
    media_download_id: int,
    *,
    offset: int = 0,
    limit: int = 50,
) -> dict:
    """Combine canonical download TaskRuns with the current artifact problem state.

    TaskRun history remains untouched. If the file watcher currently considers the
    artifact missing or corrupted, that durable MediaDownload state is projected as
    the newest download-history entry so consumers can present the complete lifecycle
    without pretending the watcher itself was a download task.
    """
    download = s.get(MediaDownloadBase, media_download_id)
    if download is None:
        raise HTTPException(status_code=404, detail="Media download not found")

    include_artifact_problem = download.artifact_status in _PROBLEM_ARTIFACT_STATUSES

    # The artifact problem is the newest synthetic item. Account for it when mapping
    # the combined page offset back onto the underlying TaskRun ledger.
    task_offset = max(offset - 1, 0) if include_artifact_problem else offset
    task_page = query_ledger(
        s,
        definition_key=_download_definition_key(download),
        resource_type=ResourceType.MEDIA_DOWNLOAD.value,
        resource_ids=[media_download_id],
        order_by="started_at",
        order="desc",
        offset=task_offset,
        limit=limit,
    )

    task_items = [
        {"source": "task", **item}
        for item in task_page["items"]
    ]

    items: list[dict] = []
    if include_artifact_problem and offset == 0:
        items.append({
            "source": "artifact",
            "artifact_status": download.artifact_status,
            "artifact_error": download.artifact_error,
            "file_path": download.file_path,
            "observed_at": download.updated_at,
        })
        items.extend(task_items[:max(limit - 1, 0)])
    else:
        items.extend(task_items[:limit])

    total = int(task_page["total"]) + (1 if include_artifact_problem else 0)
    return {
        "items": items,
        "total": total,
        "offset": offset,
        "limit": limit,
        "has_more": offset + len(items) < total,
    }
