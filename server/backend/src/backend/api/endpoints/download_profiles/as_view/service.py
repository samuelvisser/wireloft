from __future__ import annotations

from sqlalchemy.orm import Session, joinedload
from fastapi import HTTPException

from backend.api.models.download_profile import DownloadProfileAPIReadView, DownloadProfileAPIRead
from backend.api.models.podcast_download_profile import PodcastDownloadProfileAPIRead
from backend.api.models.series_download_profile import SeriesDownloadProfileAPIRead
from backend.types.download_profile_types import DownloadProfileType
from backend.db.models import DownloadProfileBase, Show, LocalMediaProfile


def _to_view(item: DownloadProfileBase) -> DownloadProfileAPIReadView:
    base = DownloadProfileAPIRead.model_validate(item).model_dump()
    show_title = item.show.title if getattr(item, "show", None) is not None else None
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
        # Fallback: try series first as it is the more constrained; if validation fails, try podcast
        try:
            impl = SeriesDownloadProfileAPIRead.model_validate(item)
        except Exception:
            impl = PodcastDownloadProfileAPIRead.model_validate(item)

    return DownloadProfileAPIReadView.model_validate({
        **base,
        "show_title": show_title or "",
        "local_media_profile_preferred_format": preferred_format or "",
        "download_profile_impl": impl,
    })


def get_download_profile_views_list(s: Session) -> list[DownloadProfileAPIReadView]:
    items = (
        s.query(DownloadProfileBase)
        .options(
            joinedload(DownloadProfileBase.show),
            joinedload(DownloadProfileBase.local_media_profile),
        )
        .join(Show, Show.id == DownloadProfileBase.show_id)
        .join(LocalMediaProfile, LocalMediaProfile.id == DownloadProfileBase.local_media_profile_id)
        .order_by(Show.title.asc(), DownloadProfileBase.id.asc())
        .all()
    )
    return [_to_view(it) for it in items]


def get_download_profile_view(s: Session, download_profile_id: int) -> DownloadProfileAPIReadView:
    item = (
        s.query(DownloadProfileBase)
        .options(
            joinedload(DownloadProfileBase.show),
            joinedload(DownloadProfileBase.local_media_profile),
        )
        .filter(DownloadProfileBase.id == download_profile_id)
        .one_or_none()
    )

    if item is None:
        raise HTTPException(status_code=404, detail="Download profile not found")

    return _to_view(item)
