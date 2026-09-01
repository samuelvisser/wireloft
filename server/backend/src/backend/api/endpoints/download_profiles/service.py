from __future__ import annotations

from typing import Optional, Sequence

from sqlalchemy.orm import Session
from fastapi import HTTPException

from backend.api.models.download_profile import DownloadProfileAPIRead
from backend.db.models.download_profile import DownloadProfileBase


def get_download_profiles_list(s: Session, show_slug: Optional[str] = None) -> list[DownloadProfileAPIRead]:

    if show_slug is not None:
        items = (
            s.query(DownloadProfileBase)
            .filter(
                DownloadProfileBase.show.has(slug=show_slug)
            )
            .order_by(DownloadProfileBase.id)
            .all()
        )
    else:
        items = (
            s.query(DownloadProfileBase)
            .order_by(DownloadProfileBase.id)
            .all()
        )

    return [DownloadProfileAPIRead.model_validate(it) for it in items]


def get_download_profile(s: Session, download_profile_id: int) -> DownloadProfileAPIRead:
    item = (
        s.query(DownloadProfileBase)
        .filter_by(id=download_profile_id)
        .one_or_none()
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Download profile not found")

    return DownloadProfileAPIRead.model_validate(item)


def require_unique_download_profile_episode_types(
        s: Session,
        *,
        show_id: int,
        local_media_profile_id: int,
        episode_types: Sequence[str],
        exclude_profile_id: int | None = None,
) -> None:
    requested_types = set(episode_types)
    if not requested_types:
        return

    query = s.query(DownloadProfileBase).filter(
        DownloadProfileBase.show_id == show_id,
        DownloadProfileBase.local_media_profile_id == local_media_profile_id,
    )
    if exclude_profile_id is not None:
        query = query.filter(DownloadProfileBase.id != exclude_profile_id)

    conflicts = sorted({
        episode_type
        for profile in query.all()
        for episode_type in profile.ep_id_type_list
        if episode_type in requested_types
    })
    if conflicts:
        raise HTTPException(
            status_code=409,
            detail=(
                "Episode types already used by another Download Profile for this show and Local Media Profile: "
                + ", ".join(conflicts)
            ),
        )
