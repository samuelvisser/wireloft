from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException
from pydantic import TypeAdapter
from sqlalchemy.orm import Session, with_polymorphic

from backend.api.models.local_media_profile_view import (
    LocalMediaProfileAPIRead,
    LocalMediaProfileStatisticsAPIRead,
    LocalMediaProfileViewAPIRead,
)
from backend.db.models import (
    DownloadProfileBase,
    LocalMediaProfileBase,
    MediaDownloadBase,
)
from backend.types.download_profile_types import MediaDownloadArtifactStatus
from dailywire_downloader import hls_asset_marker
from task_manager.tasks.workers.file_watcher.service import resolve_media_download_file


def _raise_profile_in_use(message: str) -> None:
    raise HTTPException(
        status_code=409,
        detail=[{
            "loc": ["body", "__all__"],
            "msg": message,
            "type": "resource_in_use",
        }],
    )


def _path_is_file(path: str | None) -> bool:
    if not path:
        return False
    try:
        return Path(path).is_file()
    except OSError:
        # A path that cannot safely be inspected must never make a destructive
        # profile deletion less restrictive.
        return True


def _download_has_physical_artifact(
    s: Session,
    download: MediaDownloadBase,
) -> bool:
    if download.artifact_status != MediaDownloadArtifactStatus.ABSENT.value:
        if resolve_media_download_file(s, download) is not None:
            return True
    elif _path_is_file(download.file_path):
        # ABSENT is normally paired with an unresolved .ext path or a path whose
        # file has already been removed. Still inspect it so stale state cannot
        # orphan a file during profile deletion.
        return True

    if download.file_path and Path(download.file_path).suffix.lower() == ".m3u8":
        try:
            if hls_asset_marker(Path(download.file_path)).is_file():
                return True
        except OSError:
            return True

    return _path_is_file(download.thumbnail_path)


def ensure_local_media_profile_can_be_deleted(
    s: Session,
    local_media_profile: LocalMediaProfileBase,
) -> tuple[MediaDownloadBase, ...]:
    has_download_profiles = (
        s.query(DownloadProfileBase.id)
        .filter(DownloadProfileBase.local_media_profile_id == local_media_profile.id)
        .first()
        is not None
    )
    if has_download_profiles:
        _raise_profile_in_use(
            "This Local Media Profile cannot be deleted because one or more Download Profiles still use it. "
            "Change or delete those Download Profiles before deleting the profile."
        )

    downloads = tuple(
        s.query(MediaDownloadBase)
        .filter(MediaDownloadBase.local_media_profile_id == local_media_profile.id)
        .order_by(MediaDownloadBase.id)
        .all()
    )
    for download in downloads:
        if _download_has_physical_artifact(s, download):
            _raise_profile_in_use(
                "This Local Media Profile cannot be deleted because one or more managed downloads still have "
                "a physical file. Delete all downloads for this profile first."
            )

    return downloads


_local_media_profile_read_adapter = TypeAdapter(LocalMediaProfileAPIRead)


def _to_read(local_media_profile: LocalMediaProfileBase) -> LocalMediaProfileAPIRead:
    return _local_media_profile_read_adapter.validate_python(
        local_media_profile,
        from_attributes=True,
    )


def _get_local_media_profile_record(
    s: Session,
    local_media_profile_slug: str,
) -> LocalMediaProfileBase:
    profile = with_polymorphic(LocalMediaProfileBase, "*")
    local_media_profile = (
        s.query(profile)
        .filter(profile.slug == local_media_profile_slug)
        .one_or_none()
    )
    if local_media_profile is None:
        raise HTTPException(status_code=404, detail="Media profile not found")
    return local_media_profile


def get_local_media_profiles_list(s: Session) -> list[LocalMediaProfileAPIRead]:
    profile = with_polymorphic(LocalMediaProfileBase, "*")
    items = (
        s.query(profile)
        .order_by(profile.id)
        .all()
    )
    return [_to_read(item) for item in items]


def get_local_media_profile(
    s: Session,
    local_media_profile_slug: str,
) -> LocalMediaProfileAPIRead:
    return _to_read(_get_local_media_profile_record(s, local_media_profile_slug))


def get_local_media_profile_view(
    s: Session,
    local_media_profile_slug: str,
) -> LocalMediaProfileViewAPIRead:
    local_media_profile = _get_local_media_profile_record(s, local_media_profile_slug)
    downloads = tuple(
        s.query(MediaDownloadBase)
        .filter(MediaDownloadBase.local_media_profile_id == local_media_profile.id)
        .order_by(MediaDownloadBase.id)
        .all()
    )
    physical_statuses = {
        MediaDownloadArtifactStatus.AVAILABLE.value,
        MediaDownloadArtifactStatus.CORRUPTED.value,
    }
    downloaded = tuple(
        download for download in downloads
        if download.artifact_status in physical_statuses
    )
    storage_size_bytes = sum(
        int(
            download.downloaded_bytes
            if download.downloaded_bytes is not None
            else download.artifact_size_bytes or 0
        )
        for download in downloaded
    )
    download_profile_count = (
        s.query(DownloadProfileBase)
        .filter(DownloadProfileBase.local_media_profile_id == local_media_profile.id)
        .count()
    )

    return LocalMediaProfileViewAPIRead(
        profile=_to_read(local_media_profile),
        statistics=LocalMediaProfileStatisticsAPIRead(
            managed_media_count=len(downloads),
            downloaded_media_count=len(downloaded),
            storage_size_bytes=storage_size_bytes,
            download_profile_count=download_profile_count,
        ),
    )


def delete_local_media_profile_record(
    s: Session,
    local_media_profile: LocalMediaProfileBase,
) -> None:
    downloads = ensure_local_media_profile_can_be_deleted(s, local_media_profile)
    for download in downloads:
        s.delete(download)
    s.flush()
    s.delete(local_media_profile)
    s.flush()
