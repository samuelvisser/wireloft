from __future__ import annotations

from sqlalchemy.orm import Session, joinedload, selectinload

from backend.api.models.local_media_profile import (
    LocalMediaProfileTemplatePreview,
    LocalMediaProfileTemplatePreviewResult,
    LocalMediaProfileTemplateSource,
    LocalMediaProfileTemplateSources,
)
from backend.db.models import Episode, Movie
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


def local_media_profile_template_preview(
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
