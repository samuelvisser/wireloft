from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models import DownloadProfileBase, LocalMediaProfileBase, MediaDownloadBase
from task_manager.scheduler.operation_factory import create_operation
from task_manager.scheduler.operations import complete_operation, queue_operation_target_dispatch

from .operations import LocalMediaProfileDeleteDownloadsOperation


def request_local_media_profile_download_delete(
    s: Session,
    local_media_profile_slug: str,
) -> dict[str, bool | int | str]:
    profile = (
        s.query(LocalMediaProfileBase)
        .filter_by(slug=local_media_profile_slug)
        .one_or_none()
    )
    if profile is None:
        raise HTTPException(status_code=404, detail="Media profile not found")

    download_ids = tuple(s.scalars(
        select(MediaDownloadBase.id)
        .where(MediaDownloadBase.local_media_profile_id == profile.id)
        .order_by(MediaDownloadBase.id.asc())
    ))

    disabled_download_profiles = 0
    if download_ids:
        download_profiles = list(
            s.query(DownloadProfileBase)
            .filter(
                DownloadProfileBase.local_media_profile_id == profile.id,
                DownloadProfileBase.enable_profile.is_(True),
            )
            .all()
        )
        for download_profile in download_profiles:
            download_profile.enable_profile = False
        disabled_download_profiles = len(download_profiles)

    operation = create_operation(
        s,
        LocalMediaProfileDeleteDownloadsOperation(
            profile,
            media_download_ids=download_ids,
            disabled_download_profiles=disabled_download_profiles,
        ),
    )

    if not download_ids:
        complete_operation(
            s,
            operation.id,
            summary=f"No downloads use {profile.name}",
            data={
                "files_deleted": 0,
                "downloads_requested": 0,
                "download_profiles_disabled": 0,
            },
        )
    else:
        for download_id in download_ids:
            queue_operation_target_dispatch(
                s,
                operation.id,
                f"media_download:{download_id}",
            )

    s.flush()
    return {
        "queued": bool(download_ids),
        "downloads_queued": len(download_ids),
        "download_profiles_disabled": disabled_download_profiles,
        "operation_id": operation.id,
    }
