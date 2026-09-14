from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import joinedload, selectinload, Session
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
    "season_index": "1",
    "episode": "the-first-episode",
    "episode_title": "The First Episode",
    "title": "The First Episode",
    "episode_type": "ep",
    "episode_number": "1",
    "episode_label": "1",
    "episode_identifier": "ep.1",
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
    "movie_slug": "example-movie",
    "movie_title": "Example Movie",
    "movie_extended_title": "Example Movie",
    "movie_author": "Example Studio",
    "movie_mature_rating": "PG-13",
    "movie_duration_seconds": "6420",
    "movie_date": "2026-08-30",
    "movie_time": "00:00:00",
    "movie_datetime": "2026-08-30 00:00:00",
    "movie_year": "2026",
    "movie_month": "08",
    "movie_day": "30",
    "movie_hour": "00",
    "movie_minute": "00",
    "movie_second": "00",
    "slug": "example-movie",
    "title": "Example Movie",
    "extended_title": "Example Movie",
    "author": "Example Studio",
    "mature_rating": "PG-13",
    "rating": "PG-13",
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


def _template_fields_for_type(profile_type: LocalMediaProfileType) -> frozenset[str]:
    if profile_type == LocalMediaProfileType.SHOW:
        return SHOW_OUTPUT_TEMPLATE_FIELDS
    if profile_type == LocalMediaProfileType.MOVIE:
        return MOVIE_OUTPUT_TEMPLATE_FIELDS
    raise ValueError("Output templates are only available for Show and Movie profiles")


def _alternate_collision_probe_values(
    profile_type: LocalMediaProfileType,
) -> dict[str, str]:
    if profile_type == LocalMediaProfileType.SHOW:
        values = dict(_EXAMPLE_SHOW_VALUES)
        values.update({
            "show": "another-show",
            "show_title": "Another Show",
            "season": "season-2",
            "season_name": "Season 2",
            "season_index": "2",
            "episode": "another-episode",
            "episode_title": "Another Episode",
            "title": "Another Episode",
            "episode_type": "aux",
            "episode_number": "42",
            "episode_label": "42",
            "episode_identifier": "aux.42",
            "episode_published_date": "2025-01-02",
            "episode_published_time": "03:04:05",
            "episode_published_datetime": "2025-01-02 03:04:05",
            "date": "2025-01-02",
            "time": "03:04:05",
            "datetime": "2025-01-02 03:04:05",
            "year": "2025",
            "month": "01",
            "day": "02",
            "hour": "03",
            "minute": "04",
            "second": "05",
        })
        return values

    if profile_type == LocalMediaProfileType.MOVIE:
        values = dict(_EXAMPLE_MOVIE_VALUES)
        values.update({
            "movie_slug": "another-movie",
            "movie_title": "Another Movie",
            "movie_extended_title": "Another Movie Extended",
            "movie_author": "Another Studio",
            "movie_mature_rating": "R",
            "movie_duration_seconds": "7200",
            "movie_date": "2025-01-02",
            "movie_time": "03:04:05",
            "movie_datetime": "2025-01-02 03:04:05",
            "movie_year": "2025",
            "movie_month": "01",
            "movie_day": "02",
            "movie_hour": "03",
            "movie_minute": "04",
            "movie_second": "05",
            "slug": "another-trailer",
            "title": "Another Trailer",
            "extended_title": "Another Trailer",
            "author": "",
            "mature_rating": "",
            "rating": "",
            "duration_seconds": "120",
            "media_type": "trailer",
            "date": "2025-01-03",
            "time": "04:05:06",
            "datetime": "2025-01-03 04:05:06",
            "year": "2025",
            "month": "01",
            "day": "03",
            "hour": "04",
            "minute": "05",
            "second": "06",
        })
        return values

    raise ValueError("Output templates are only available for Show and Movie profiles")


def _preferred_format_extension(preferred_format: PreferredFormat | str) -> str:
    return "m4a" if preferred_format == PreferredFormat.FORMAT_AUDIO_ONLY else "mp4"


def _render_collision_path(
    output_template: str,
    *,
    profile_type: LocalMediaProfileType,
    preferred_format: PreferredFormat | str,
    values: dict[str, str],
) -> str:
    rendered = render_output_template(
        output_template,
        values,
        allowed_fields=_template_fields_for_type(profile_type),
    )
    return replace_output_extension(
        rendered,
        _preferred_format_extension(preferred_format),
    )


def _collision_probe_values(
    s: Session,
    profile_type: LocalMediaProfileType,
) -> list[tuple[str, dict[str, str]]]:
    sources = get_output_template_sources(s, profile_type).sources
    probes = [(source.label, source.values) for source in sources]

    fallback_values = (
        _EXAMPLE_SHOW_VALUES
        if profile_type == LocalMediaProfileType.SHOW
        else _EXAMPLE_MOVIE_VALUES
    )
    if not any(source.fallback for source in sources):
        probes.append(("WireLoft example", dict(fallback_values)))

    probes.append(("alternate WireLoft example", _alternate_collision_probe_values(profile_type)))
    return probes


def _find_rendered_output_collision(
    body: LocalMediaProfileAPICreate | LocalMediaProfileAPIUpdate,
    existing: LocalMediaProfileBase,
    probes: list[tuple[str, dict[str, str]]],
) -> tuple[str, str] | None:
    profile_type = LocalMediaProfileType(body.type)
    for label, values in probes:
        try:
            candidate_path = _render_collision_path(
                body.output_template,
                profile_type=profile_type,
                preferred_format=body.preferred_format,
                values=values,
            )
            existing_path = _render_collision_path(
                existing.output_template,
                profile_type=profile_type,
                preferred_format=existing.preferred_format,
                values=values,
            )
        except ValueError:
            # Stored profiles may predate stricter template validation, and a
            # representative probe can exercise a branch that is impossible for
            # real media. Do not make an unrelated old template block all edits.
            continue
        if candidate_path == existing_path:
            return label, candidate_path
    return None


def _ensure_unique_profile_settings(
    s: Session,
    body: LocalMediaProfileAPICreate | LocalMediaProfileAPIUpdate,
    *,
    exclude_id: int | None = None,
) -> None:
    exact_query = s.query(LocalMediaProfileBase).filter(
        LocalMediaProfileBase.type == body.type,
        LocalMediaProfileBase.output_template == body.output_template,
        LocalMediaProfileBase.preferred_format == body.preferred_format,
    )
    if exclude_id is not None:
        exact_query = exact_query.filter(LocalMediaProfileBase.id != exclude_id)
    if exact_query.first() is not None:
        raise HTTPException(
            status_code=409,
            detail=[{
                "loc": ["body", "outputTemplate"],
                "msg": "A Local Media Profile with this type, output path template, and preferred format already exists",
                "type": "unique_violation",
            }],
        )

    # Raw template strings can differ while rendering to the same file because of
    # Jinja assignments/conditions or filename sanitization. Compare the actual
    # rendered paths against every profile of the same media type. Preferred
    # format is reflected by the concrete extension, so audio/video profiles may
    # share a template safely while two video-quality profiles may not target the
    # same .mp4 path.
    profiles_query = s.query(LocalMediaProfileBase).filter(
        LocalMediaProfileBase.type == body.type,
    )
    if exclude_id is not None:
        profiles_query = profiles_query.filter(LocalMediaProfileBase.id != exclude_id)

    existing_profiles = profiles_query.all()
    if not existing_profiles:
        return

    probes = _collision_probe_values(s, LocalMediaProfileType(body.type))
    for existing in existing_profiles:
        collision = _find_rendered_output_collision(body, existing, probes)
        if collision is None:
            continue
        label, output_path = collision
        raise HTTPException(
            status_code=409,
            detail=[{
                "loc": ["body", "outputTemplate"],
                "msg": (
                    "Output template resolves to the same file as Local Media Profile "
                    f"'{existing.name}' for {label}: {output_path}. Choose a template "
                    "that produces a different output path."
                ),
                "type": "output_path_collision",
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
    if body.type != LocalMediaProfileType.SHOW:
        data.pop("show_scope", None)
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
    exclude_fields = {"show_scope"} if local_media_profile.type != LocalMediaProfileType.SHOW.value else None
    update_database_fields(local_media_profile, body, exclude_fields=exclude_fields)
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
    """Return recent locally stored examples, or one complete fallback example."""
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
            .options(selectinload(Movie.movie_extras))
            .order_by(Movie.created_at.desc(), Movie.id.desc())
            .limit(20)
            .all()
        )
        sources = []
        for movie in movies:
            if len(sources) >= 20:
                break
            sources.append(LocalMediaProfileTemplateSource(
                id=f"movie:{movie.id}",
                label=movie.title,
                values=movie_output_template_values(movie),
            ))
            for movie_extra in movie.movie_extras:
                if len(sources) >= 20:
                    break
                sources.append(LocalMediaProfileTemplateSource(
                    id=f"movie-extra:{movie_extra.id}",
                    label=f"\u00a0\u00a0↳ {movie_extra.title}",
                    values=movie_output_template_values(movie, movie_extra),
                ))
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