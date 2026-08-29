from __future__ import annotations

from sqlalchemy.orm import Session, joinedload, with_polymorphic

from fastapi import HTTPException
from sqlalchemy.orm.util import AliasedClass

from backend.api.models.download_profile import DownloadProfileAPIRead
from backend.api.models.download_profile_view import DownloadProfileAPIReadView
from backend.api.models.podcast_download_profile import PodcastDownloadProfileAPIRead
from backend.api.models.series_download_profile import SeriesDownloadProfileAPIRead
from backend.types.download_profile_types import DownloadProfileType
from backend.db.models import DownloadProfileBase, LocalMediaProfileBase, PodcastDownloadProfile, SeriesDownloadProfile, Show


def _to_view(item: AliasedClass[DownloadProfileBase]) -> DownloadProfileAPIReadView:
    base = DownloadProfileAPIRead.model_validate(item).model_dump()
    show_title = item.show.title if getattr(item, "show", None) is not None else None
    show_slug = item.show.slug if getattr(item, "show", None) is not None else None
    preferred_format = (
        item.local_media_profile.preferred_format if getattr(item, "local_media_profile", None) is not None else None
    )

    # Map concrete implementation payload based on type discriminator
    t = str(getattr(item, "type", ""))
    if t == DownloadProfileType.PODCAST.value:
        impl = PodcastDownloadProfileAPIRead.model_validate(item)
    elif t == DownloadProfileType.SERIES.value:
        impl = SeriesDownloadProfileAPIRead.model_validate(item)
    else:
        # This will fail Pydantic validation, which is what we want; there always needs to ba an implementation
        impl = None

    return DownloadProfileAPIReadView.model_validate({
        **base,
        "show_title": show_title or "",
        "show_slug": show_slug or "",
        "local_media_profile_preferred_format": preferred_format or "",
        "download_profile_impl": impl,
    })


def get_download_profile_views_list(s: Session) -> list[DownloadProfileAPIReadView]:
    DP = with_polymorphic(DownloadProfileBase, [PodcastDownloadProfile, SeriesDownloadProfile])
    items = (
        s.query(DP)
        .options(
            joinedload(DP.show),
            joinedload(DP.local_media_profile),
        )
        .join(Show, Show.id == DP.show_id)
        .join(LocalMediaProfileBase, LocalMediaProfileBase.id == DP.local_media_profile_id)
        .order_by(Show.title.asc(), DP.id.asc())
        .all()
    )

    return [_to_view(it) for it in items]


def get_download_profile_view(s: Session, download_profile_id: int) -> DownloadProfileAPIReadView:
    DP = with_polymorphic(DownloadProfileBase, [PodcastDownloadProfile, SeriesDownloadProfile])
    item = (
        s.query(DP)
        .options(
            joinedload(DP.show),
            joinedload(DP.local_media_profile),
        )
        .filter_by(id=download_profile_id)
        .one_or_none()
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Download profile not found")

    return _to_view(item)
