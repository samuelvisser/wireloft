from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import joinedload, Session
from fastapi import HTTPException

from backend.api.helpers import update_database_fields
from backend.api.models.local_media_profile import *
from backend.db.models import (
    Episode,
    LocalMediaProfileBase,
    Movie,
    MovieLocalMediaProfile,
    ShowLocalMediaProfile,
)
from backend.types.local_media_profile_types import LocalMediaProfileType, PreferredFormat
from backend.utils.output_template import (
    MOVIE_OUTPUT_TEMPLATE_FIELDS,
    SHOW_OUTPUT_TEMPLATE_FIELDS,
    episode_output_template_values,
    movie_output_template_values,
    output_template_fields,
    replace_output_extension,
    render_output_template,
)


_PROFILE_MODELS = {
    LocalMediaProfileType.SHOW.value: ShowLocalMediaProfile,
    LocalMediaProfileType.MOVIE.value: MovieLocalMediaProfile,
}

_EXAMPLE_SHOW_VALUES = {
    "show": "example-show",
    "show_title": "Example Show",
    "season": "season-1",
    "season_name": "Season 1",
    "episode": "the-first-episode",
    "episode_title": "The First Episode",
    "title": "The First Episode",
    "episode_type": "ep",
    "episode_number": "1",
    "ep_id": "EP-001",
    "episode_published_date": "2026-08-30",
    "episode_published_time": "20:00:00",
    "episode_published_datetime": "2026-08-30 20:00:00",
    "date": "2026-08-30",
    "time": "20:00:00",
    "datetime": "2026-08-30 20:00:00",
    "year": "2026",
    "month": "08",
    "day": "30",
    "hour": "20",
    "minute": "00",
    "second": "00",
}

_EXAMPLE_MOVIE_VALUES = {
    "movie": "example-movie",
    "movie_slug": "example-movie",
    "movie_title": "Example Movie",
    "title": "Example Movie",
    "movie_extended_title": "Example Movie",
    "extended_title": "Example Movie",
    "movie_dw_id": "movie-001",
    "dw_id": "movie-001",
    "movie_author": "Example Studio",
    "author": "Example Studio",
    "movie_mature_rating": "PG-13",
    "mature_rating": "PG-13",
    "rating": "PG-13",
    "movie_duration_seconds": "6420",
    "duration_seconds": "6420",
    "media_type": "movie",
    "date": "2026-08-30",
    "time": "00:00:00",
    "datetime": "2026-08-30 00:00:00",
    "year": "2026",
    "month": "08",
    "day": "30",
    "hour": "00",
    "minute": "00",
    "second": "00",
}


def _ensure_unique_profile_settings(
    s: Session,
    body: LocalMediaProfileAPICreate | LocalMediaProfileAPIUpdate,
    *,
    exclude_id: int | None = None,
) -> None:
    query = s.query(LocalMediaProfileBase).filter(
        LocalMediaProfileBase.type == body.type,
        LocalMediaProfileBase.output_template == body.output_template,
        LocalMediaProfileBase.preferred_format == body.preferred_format,
    )
    if exclude_id is not None:
        query = query.filter(LocalMediaProfileBase.id != exclude_id)
    if query.first() is not None:
        raise HTTPException(
            status_code=409,
            detail=[{
                "loc": ["body", "outputTemplate"],
                "msg": "A Local Media Profile with this type, output path template, and preferred format already exists",
                "type": "unique_violation",
            }],
        )


def get_local_media_profiles_list(s: Session) -> list[LocalMediaProfileAPIRead]:
    local_media_profiles = (
        s.query(LocalMediaProfileBase)
        .order_by(LocalMediaProfileBase.id)
        .all()
    )
    return [LocalMediaProfileAPIRead.model_validate(mp) for mp in local_media_profiles]


def get_local_media_profile(s: Session, local_media_profile_slug: str) -> LocalMediaProfileAPIRead:
    local_media_profile = (
        s.query(LocalMediaProfileBase)
        .filter_by(slug=local_media_profile_slug)
        .one_or_none()
    )
    if local_media_profile is None:
        raise HTTPException(status_code=404, detail="Media profile not found")
    return LocalMediaProfileAPIRead.model_validate(local_media_profile)


def create_local_media_profile(s: Session, body: LocalMediaProfileAPICreate) -> LocalMediaProfileAPIRead:
    _ensure_unique_profile_settings(s, body)
    data = body.model_dump(by_alias=True)
    profile_model = _PROFILE_MODELS[body.type]
    mp = profile_model(**data)
    s.add(mp)
    s.flush()
    return LocalMediaProfileAPIRead.model_validate(mp)


def update_local_media_profile(s: Session, local_media_profile_slug: str, body: LocalMediaProfileAPIUpdate) -> LocalMediaProfileAPIRead:
    local_media_profile: Optional[LocalMediaProfileBase] = (
        s.query(LocalMediaProfileBase)
        .filter_by(slug=local_media_profile_slug)
        .one_or_none()
    )
    if local_media_profile is None:
        raise HTTPException(status_code=404, detail="Media profile not found")
    if local_media_profile.type != body.type:
        raise HTTPException(status_code=422, detail="A Local Media Profile's type cannot be changed")

    _ensure_unique_profile_settings(s, body, exclude_id=local_media_profile.id)
    update_database_fields(local_media_profile, body)
    s.flush()
    return LocalMediaProfileAPIRead.model_validate(local_media_profile)


def delete_local_media_profile(s: Session, local_media_profile_slug: str) -> LocalMediaProfileAPIRead:
    local_media_profile = (
        s.query(LocalMediaProfileBase)
        .filter_by(slug=local_media_profile_slug)
        .one_or_none()
    )
    if local_media_profile is None:
        raise HTTPException(status_code=404, detail="Media profile not found")

    payload = LocalMediaProfileAPIRead.model_validate(local_media_profile)
    s.delete(local_media_profile)
    s.flush()
    return payload


def get_output_template_sources(
    s: Session,
    profile_type: LocalMediaProfileType,
) -> LocalMediaProfileTemplateSources:
    """Return at most ten recent real examples, or one complete fallback example."""
    if profile_type == LocalMediaProfileType.SHOW:
        episodes = (
            s.query(Episode)
            .options(joinedload(Episode.show), joinedload(Episode.season))
            .order_by(Episode.published_date.desc().nullslast(), Episode.created_at.desc(), Episode.id.desc())
            .limit(10)
            .all()
        )
        sources = [
            LocalMediaProfileTemplateSource(
                id=f"episode:{episode.id}",
                label=f"{episode.show.title} — {episode.title}",
                values=episode_output_template_values(episode),
            )
            for episode in episodes
        ]
        fallback_values = _EXAMPLE_SHOW_VALUES
        fallback_label = "Example show episode"
    elif profile_type == LocalMediaProfileType.MOVIE:
        movies = (
            s.query(Movie)
            .order_by(Movie.created_at.desc(), Movie.id.desc())
            .limit(10)
            .all()
        )
        sources = [
            LocalMediaProfileTemplateSource(
                id=f"movie:{movie.id}",
                label=movie.title,
                values=movie_output_template_values(movie),
            )
            for movie in movies
        ]
        fallback_values = _EXAMPLE_MOVIE_VALUES
        fallback_label = "Example movie"
    else:
        raise ValueError("Template examples are only available for Show and Movie profiles")

    if not sources:
        sources = [LocalMediaProfileTemplateSource(
            id=f"example:{profile_type.value}",
            label=fallback_label,
            values=dict(fallback_values),
            fallback=True,
        )]
    return LocalMediaProfileTemplateSources(sources=sources)


def preview_output_template(
    body: LocalMediaProfileTemplatePreview,
) -> LocalMediaProfileTemplatePreviewResult:
    if body.type == LocalMediaProfileType.SHOW:
        allowed_fields = SHOW_OUTPUT_TEMPLATE_FIELDS
    elif body.type == LocalMediaProfileType.MOVIE:
        allowed_fields = MOVIE_OUTPUT_TEMPLATE_FIELDS
    else:
        raise ValueError("Template previews are only available for Show and Movie profiles")

    output_path = render_output_template(
        body.output_template,
        body.values,
        allowed_fields=allowed_fields,
    )
    extension = "m4a" if body.preferred_format == PreferredFormat.FORMAT_AUDIO_ONLY else "mp4"
    return LocalMediaProfileTemplatePreviewResult(
        output_path=replace_output_extension(output_path, extension),
        used_variables=sorted(output_template_fields(body.output_template)),
    )
