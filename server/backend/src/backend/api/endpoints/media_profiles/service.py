from __future__ import annotations

import datetime as dt
from fastapi import HTTPException

from backend.api.models.response import MediaProfileItemResponse
from backend.app import db_session
from backend.db.models import MediaProfile


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _slugify(text: str | None) -> str:
    if not text:
        return ""
    s = str(text).strip().lower()
    out = []
    for ch in s:
        if ch.isalnum() or ch in "-_.":
            out.append(ch)
        elif ch.isspace() or ch in "/\\":
            out.append("-")
    slug = "".join(out)
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-")


def get_media_profiles_list() -> list[MediaProfileItemResponse]:
    with db_session() as s:
        profiles = (
            s.query(MediaProfile)
            .order_by(MediaProfile.id)
            .all()
        )
        return [MediaProfileItemResponse.model_validate(mp, from_attributes=True) for mp in profiles]


def get_media_profile(media_profile_slug: str) -> MediaProfileItemResponse:
    with db_session() as s:
        profile = s.query(MediaProfile).filter_by(slug=media_profile_slug).one_or_none()
        if profile is None:
            raise HTTPException(status_code=404, detail="Media profile not found")
        return MediaProfileItemResponse.model_validate(profile, from_attributes=True)


def create_media_profile(
    *,
    name: str,
    outputPathTemplate: str,
    preferredFormat: str,
    downloadSeriesImages: bool,
) -> MediaProfileItemResponse:
    slug = _slugify(name)
    if not slug:
        raise HTTPException(status_code=400, detail="Invalid profile name")

    with db_session() as s:
        # Ensure unique slug
        existing = s.query(MediaProfile).filter_by(slug=slug).one_or_none()
        if existing is not None:
            raise HTTPException(status_code=409, detail="Media profile slug already exists")

        mp = MediaProfile(
            slug=slug,
            name=name,
            output_template=outputPathTemplate,
            preferred_format=preferredFormat,
            download_series_images=downloadSeriesImages,
            created_date=_now(),
            modified_date=_now(),
        )
        s.add(mp)
        s.commit()
        s.refresh(mp)
        return MediaProfileItemResponse.model_validate(mp, from_attributes=True)


def update_media_profile(
    media_profile_slug: str,
    *,
    name: str | None = None,
    outputPathTemplate: str | None = None,
    preferredFormat: str | None = None,
    downloadSeriesImages: bool | None = None,
) -> MediaProfileItemResponse:
    with db_session() as s:
        mp = s.query(MediaProfile).filter_by(slug=media_profile_slug).one_or_none()
        if mp is None:
            raise HTTPException(status_code=404, detail="Media profile not found")

        if name is not None and name.strip():
            mp.name = name
        if outputPathTemplate is not None:
            mp.output_template = outputPathTemplate
        if preferredFormat is not None:
            mp.preferred_format = preferredFormat
        if downloadSeriesImages is not None:
            mp.download_series_images = downloadSeriesImages
        mp.modified_date = _now()
        s.commit()
        s.refresh(mp)
        return MediaProfileItemResponse.model_validate(mp, from_attributes=True)


def delete_media_profile(media_profile_slug: str) -> MediaProfileItemResponse:
    with db_session() as s:
        mp = s.query(MediaProfile).filter_by(slug=media_profile_slug).one_or_none()
        if mp is None:
            raise HTTPException(status_code=404, detail="Media profile not found")
        payload = MediaProfileItemResponse.model_validate(mp, from_attributes=True)
        s.delete(mp)
        s.commit()
        return payload
