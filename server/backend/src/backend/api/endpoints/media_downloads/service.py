from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session
from fastapi import HTTPException

from backend.api.helpers import update_database_fields
from backend.api.models.media_download import *
from backend.db.models import Episode, LocalMediaProfile, Show
from backend.db.models.media_download import EpisodeMediaDownload, MediaDownloadAttempt, MediaDownloadBase
from backend.types.download_profile_types import MediaDownloadStatus
from backend.types.media_types import MediaType
from backend.utils.output_template import resolve_episode_output_path

# Statuses that are safe to restart or replace: nothing is actively running
_RESTARTABLE_STATUSES = {MediaDownloadStatus.PENDING.value, MediaDownloadStatus.ERROR.value}


def get_media_downloads_list(s: Session) -> list[MediaDownloadAPIRead]:
    items = (
        s.query(MediaDownloadBase)
        .order_by(MediaDownloadBase.id)
        .all()
    )
    return [MediaDownloadAPIRead.model_validate(it) for it in items]


def get_media_downloads_view(
        s: Session,
        *,
        episode_slug: Optional[str] = None,
        statuses: Optional[list[str]] = None,
        limit: Optional[int] = None,
) -> list[MediaDownloadAPIReadView]:
    """Downloads joined with episode, show and profile context, newest first."""
    stmt = (
        select(EpisodeMediaDownload, Episode, Show, LocalMediaProfile)
        .join(Episode, Episode.id == EpisodeMediaDownload.media_item_id)
        .join(Show, Show.id == Episode.show_id)
        .join(LocalMediaProfile, LocalMediaProfile.id == EpisodeMediaDownload.local_media_profile_id)
        .order_by(EpisodeMediaDownload.id.desc())
    )
    if episode_slug is not None:
        stmt = stmt.where(Episode.slug == episode_slug)
    if statuses:
        stmt = stmt.where(EpisodeMediaDownload.download_status.in_(statuses))
    if limit is not None:
        stmt = stmt.limit(limit)

    views: list[MediaDownloadAPIReadView] = []
    for download, episode, show, profile in s.execute(stmt):
        base = MediaDownloadAPIRead.model_validate(download)
        views.append(MediaDownloadAPIReadView(
            **base.model_dump(by_alias=False),
            episode_slug=episode.slug,
            episode_title=episode.title,
            episode_identifier=episode.episode_identifier,
            show_slug=show.slug,
            show_title=show.title,
            local_media_profile_name=profile.name,
            preferred_format=profile.preferred_format,
            is_redownload_attempt=download.is_redownload_attempt,
            downloaded_publish_status=download.downloaded_publish_status,
        ))
    return views


def get_media_download_attempts(s: Session, media_download_id: int) -> list[MediaDownloadAttemptAPIRead]:
    """A download's full attempt ledger, newest first."""
    if s.get(MediaDownloadBase, media_download_id) is None:
        raise HTTPException(status_code=404, detail="Media download not found")

    items = (
        s.query(MediaDownloadAttempt)
        .filter_by(media_download_id=media_download_id)
        .order_by(MediaDownloadAttempt.id.desc())
        .all()
    )
    return [MediaDownloadAttemptAPIRead.model_validate(it) for it in items]


def get_media_download(s: Session, media_download_id: int) -> MediaDownloadAPIRead:
    item = (
        s.query(MediaDownloadBase)
        .filter_by(id=media_download_id)
        .one_or_none()
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Media download not found")

    return MediaDownloadAPIRead.model_validate(item)


def create_episode_download(s: Session, episode_slug: str, body: EpisodeDownloadAPICreate) -> EpisodeMediaDownload:
    """Create the download row for (episode, local media profile).

    Only one download per profile is allowed for an episode. An existing
    pending/errored row is reused (restarted); an active or finished one is a conflict.
    """
    episode: Optional[Episode] = (
        s.query(Episode).filter(Episode.slug == episode_slug).one_or_none()
    )
    if episode is None:
        raise HTTPException(status_code=404, detail="Episode not found")
    if episode.is_no_show_today:
        raise HTTPException(status_code=422, detail="This is not a downloadable episode")

    profile: Optional[LocalMediaProfile] = s.get(LocalMediaProfile, body.local_media_profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Local media profile not found")

    existing: Optional[EpisodeMediaDownload] = (
        s.query(EpisodeMediaDownload)
        .filter(
            EpisodeMediaDownload.media_item_id == episode.id,
            EpisodeMediaDownload.local_media_profile_id == profile.id,
        )
        .one_or_none()
    )
    if existing is not None:
        if existing.download_status not in _RESTARTABLE_STATUSES:
            raise HTTPException(
                status_code=409,
                detail=f"Episode already has a download for profile '{profile.name}'",
            )
        _reset_download(existing)
        s.flush()
        return existing

    download = EpisodeMediaDownload(
        type=MediaType.EPISODE.value,
        media_item_id=episode.id,
        local_media_profile_id=profile.id,
        download_status=MediaDownloadStatus.PENDING.value,
        file_path=str(resolve_episode_output_path(profile.output_template, episode=episode)),
        progress=0,
    )
    s.add(download)
    s.flush()
    return download


def retry_media_download(s: Session, media_download_id: int) -> EpisodeMediaDownload:
    """Reset an errored download so it can be started again."""
    download: Optional[EpisodeMediaDownload] = s.get(EpisodeMediaDownload, media_download_id)
    if download is None:
        raise HTTPException(status_code=404, detail="Media download not found")
    if download.download_status not in _RESTARTABLE_STATUSES:
        raise HTTPException(status_code=409, detail="Only pending or errored downloads can be retried")

    _reset_download(download)
    s.flush()
    return download


def _reset_download(download: MediaDownloadBase) -> None:
    download.download_status = MediaDownloadStatus.PENDING.value
    download.progress = 0
    download.error_message = None
    download.downloaded_bytes = None
    download.format_downloaded = None
    download.started_at = None
    download.finished_at = None


def update_media_download(s: Session, media_download_id: int, body: MediaDownloadAPIUpdate) -> MediaDownloadAPIRead:
    item: Optional[MediaDownloadBase] = (
        s.query(MediaDownloadBase)
        .filter_by(id=media_download_id)
        .one_or_none()
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Media download not found")

    update_database_fields(item, body)
    s.flush()
    return MediaDownloadAPIRead.model_validate(item)


def delete_media_download(s: Session, media_download_id: int) -> MediaDownloadAPIRead:
    item = (
        s.query(MediaDownloadBase)
        .filter_by(id=media_download_id)
        .one_or_none()
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Media download not found")

    if item.download_status == MediaDownloadStatus.DOWNLOADING.value:
        raise HTTPException(status_code=409, detail="Cannot delete a download that is currently running")

    payload = MediaDownloadAPIRead.model_validate(item)
    s.delete(item)
    s.flush()
    return payload
