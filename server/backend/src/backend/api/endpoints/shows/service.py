from __future__ import annotations

import datetime as dt
import uuid
from fastapi import HTTPException

from backend.api.models.response import ShowItemResponse
from backend.app import db_session
from backend.db.models import Show, MediaProfile


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


def get_show_list() -> list[ShowItemResponse]:
    with db_session() as s:
        shows = (
            s.query(Show)
            .order_by(Show.id)
            .all()
        )
        return [ShowItemResponse.model_validate(sh, from_attributes=True) for sh in shows]


def get_show(show_slug: str) -> ShowItemResponse:
    with db_session() as s:
        show = s.query(Show).filter_by(slug=show_slug).one_or_none()
        if show is None:
            raise HTTPException(status_code=404, detail="Show not found")
        return ShowItemResponse.model_validate(show, from_attributes=True)


def _extract_slug_from_url(url: str) -> str:
    try:
        from urllib.parse import urlparse
        path = urlparse(url).path
        if not path:
            return ""
        parts = [p for p in path.split('/') if p]
        if len(parts) >= 2 and parts[0] == 'show':
            return parts[1]
        # Fallback to last segment
        return parts[-1] if parts else ""
    except Exception:
        return ""


def create_show(
    *,
    url: str,
    mediaProfileSlug: str,
    name: str,
    author: str,
    downloadMedia: bool,
    downloadDelayMinutes: int | str,
    redownloadAfterMinutes: int | str,
    downloadDays: int | str,
    deleteOlder: bool,
    titleFilter: str | None,
) -> ShowItemResponse:
    slug = _extract_slug_from_url(url)
    if not slug:
        raise HTTPException(status_code=400, detail="Invalid show URL; could not extract slug")

    with db_session() as s:
        existing = s.query(Show).filter_by(slug=slug).one_or_none()
        if existing is not None:
            raise HTTPException(status_code=409, detail="Show slug already exists")

        mp = s.query(MediaProfile).filter_by(slug=mediaProfileSlug).one_or_none()
        if mp is None:
            raise HTTPException(status_code=400, detail="Media profile not found")

        def to_int(v: int | str) -> int:
            try:
                return int(v)
            except Exception:
                return 0

        sh = Show(
            media_profile_id=mp.id,
            uuid=str(uuid.uuid4()),
            dw_id=slug,
            slug=slug,
            title=name,
            description=None,
            url=url,
            status="active",
            media_type="show",
            author_name=author,
            author_slug=_slugify(author),
            author_headshot_path=None,
            download_media=bool(downloadMedia),
            download_delay_minutes=to_int(downloadDelayMinutes),
            redownload_delay_minutes=to_int(redownloadAfterMinutes),
            download_days_in_past=to_int(downloadDays),
            delete_older_episodes=bool(deleteOlder),
            title_filter=titleFilter if (titleFilter or "").strip() else None,
            background_image_path=None,
            logo_image_path=None,
            thumbnail_landscape_path=None,
            thumbnail_portrait_path=None,
            thumbnail_square_path=None,
            created_date=_now(),
            modified_date=_now(),
        )
        s.add(sh)
        s.commit()
        s.refresh(sh)
        return ShowItemResponse.model_validate(sh, from_attributes=True)


def update_show(
    show_slug: str,
    *,
    url: str | None = None,
    mediaProfileSlug: str | None = None,
    name: str | None = None,
    author: str | None = None,
    downloadMedia: bool | None = None,
    downloadDelayMinutes: int | str | None = None,
    redownloadAfterMinutes: int | str | None = None,
    downloadDays: int | str | None = None,
    deleteOlder: bool | None = None,
    titleFilter: str | None = None,
) -> ShowItemResponse:
    with db_session() as s:
        sh = s.query(Show).filter_by(slug=show_slug).one_or_none()
        if sh is None:
            raise HTTPException(status_code=404, detail="Show not found")

        def to_int_opt(v):
            if v is None:
                return None
            try:
                return int(v)
            except Exception:
                return 0

        if url is not None and url.strip():
            sh.url = url
        if mediaProfileSlug is not None:
            mp = s.query(MediaProfile).filter_by(slug=mediaProfileSlug).one_or_none()
            if mp is None:
                raise HTTPException(status_code=400, detail="Media profile not found")
            sh.media_profile_id = mp.id
        if name is not None and name.strip():
            sh.title = name
        if author is not None:
            sh.author_name = author
            sh.author_slug = _slugify(author)
        if downloadMedia is not None:
            sh.download_media = bool(downloadMedia)
        vi = to_int_opt(downloadDelayMinutes)
        if vi is not None:
            sh.download_delay_minutes = vi
        vi = to_int_opt(redownloadAfterMinutes)
        if vi is not None:
            sh.redownload_delay_minutes = vi
        vi = to_int_opt(downloadDays)
        if vi is not None:
            sh.download_days_in_past = vi
        if deleteOlder is not None:
            sh.delete_older_episodes = bool(deleteOlder)
        if titleFilter is not None:
            sh.title_filter = titleFilter if titleFilter.strip() else None

        sh.modified_date = _now()
        s.commit()
        s.refresh(sh)
        return ShowItemResponse.model_validate(sh, from_attributes=True)


def delete_show(show_slug: str) -> ShowItemResponse:
    with db_session() as s:
        sh = s.query(Show).filter_by(slug=show_slug).one_or_none()
        if sh is None:
            raise HTTPException(status_code=404, detail="Show not found")
        payload = ShowItemResponse.model_validate(sh, from_attributes=True)
        s.delete(sh)
        s.commit()
        return payload
