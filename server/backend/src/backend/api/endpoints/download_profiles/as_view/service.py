from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException
from sqlalchemy.orm import Session, joinedload, with_polymorphic
from sqlalchemy.orm.util import AliasedClass

from backend.api.models.download_profile_view import DownloadProfileAPIReadView
from backend.db.models import (
    DownloadProfileBase,
    LocalMediaProfileBase,
    PodcastDownloadProfile,
    SeriesDownloadProfile,
    Show,
)


@dataclass(frozen=True)
class _DownloadProfileViewSource:
    profile: AliasedClass[DownloadProfileBase]


def _to_view(item: AliasedClass[DownloadProfileBase]) -> DownloadProfileAPIReadView:
    return DownloadProfileAPIReadView.model_validate(
        _DownloadProfileViewSource(profile=item)
    )


def get_download_profile_views_list(s: Session) -> list[DownloadProfileAPIReadView]:
    profile = with_polymorphic(
        DownloadProfileBase,
        [PodcastDownloadProfile, SeriesDownloadProfile],
    )
    items = (
        s.query(profile)
        .options(
            joinedload(profile.show),
            joinedload(profile.local_media_profile),
        )
        .join(Show, Show.id == profile.show_id)
        .join(
            LocalMediaProfileBase,
            LocalMediaProfileBase.id == profile.local_media_profile_id,
        )
        .order_by(Show.title.asc(), profile.id.asc())
        .all()
    )
    return [_to_view(item) for item in items]


def get_download_profile_view(
    s: Session,
    download_profile_id: int,
) -> DownloadProfileAPIReadView:
    profile = with_polymorphic(
        DownloadProfileBase,
        [PodcastDownloadProfile, SeriesDownloadProfile],
    )
    item = (
        s.query(profile)
        .options(
            joinedload(profile.show),
            joinedload(profile.local_media_profile),
        )
        .filter_by(id=download_profile_id)
        .one_or_none()
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Download profile not found")
    return _to_view(item)
