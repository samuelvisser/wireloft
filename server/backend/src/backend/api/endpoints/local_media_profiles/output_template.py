from __future__ import annotations

from sqlalchemy import func, literal, select, union_all
from sqlalchemy.orm import Session, contains_eager, joinedload

from backend.api.models.local_media_profile import (
    LocalMediaProfileTemplatePreview,
    LocalMediaProfileTemplatePreviewResult,
    LocalMediaProfileTemplateSource,
    LocalMediaProfileTemplateSourcePage,
    LocalMediaProfileTemplateVariable,
)
from backend.db.models import Episode, Movie, MovieExtra, MovieExtraSource, Season, Show
from backend.types.local_media_profile_types import (
    LocalMediaProfileType,
    PreferredFormat,
    ShowLocalMediaProfileScope,
)
from backend.types.show_types import ShowType
from backend.utils.custom_metadata import (
    CustomMetadataScope,
    custom_metadata_template_variable,
)
from backend.utils.output_template import (
    MOVIE_OUTPUT_TEMPLATE_FIELDS,
    MOVIE_OUTPUT_TEMPLATE_METADATA_SCOPES,
    SHOW_OUTPUT_TEMPLATE_FIELDS,
    SHOW_OUTPUT_TEMPLATE_METADATA_SCOPES,
    episode_output_template_values,
    movie_output_template_values,
    output_template_fields,
    replace_output_extension,
    render_output_template,
)
from backend.utils.search import search_all_terms, search_relevance_score

from ..custom_metadata.service import get_custom_metadata_fields


_EXAMPLE_SHOW_VALUES = {
    "show": "example-show",
    "show_title": "Example Show",
    "season": "season-1",
    "season_name": "Season 1",
    "season_index": "1",
    "season_type": "normal",
    "season_number": "1",
    "episode": "the-first-episode",
    "episode_title": "The First Episode",
    "title": "The First Episode",
    "dw_episode_number": "1.00",
    "episode_type": "ep",
    "episode_extra_type": "",
    "episode_number": "1",
    "episode_sub_number": "",
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


def get_output_template_variables(
    session: Session,
    profile_type: LocalMediaProfileType,
) -> list[LocalMediaProfileTemplateVariable]:
    """Return custom template variables available to one Local Media Profile type."""
    if profile_type == LocalMediaProfileType.SHOW:
        scope: CustomMetadataScope = "show"
        description = "Custom show metadata"
    elif profile_type == LocalMediaProfileType.MOVIE:
        scope = "movie"
        description = "Custom movie metadata"
    else:
        raise ValueError("Template variables are only available for Show and Movie profiles")

    return [
        LocalMediaProfileTemplateVariable(
            name=custom_metadata_template_variable(scope, key),
            description=f"{description}: {key}",
        )
        for key in get_custom_metadata_fields(session, scope)
    ]


def _show_type_values(show_scope: ShowLocalMediaProfileScope) -> tuple[str, ...]:
    if show_scope == ShowLocalMediaProfileScope.BOTH:
        return (ShowType.PODCAST.value, ShowType.SERIES.value)
    if show_scope == ShowLocalMediaProfileScope.PODCAST:
        return (ShowType.PODCAST.value,)
    if show_scope == ShowLocalMediaProfileScope.SERIES:
        return (ShowType.SERIES.value,)
    raise ValueError(f"Unsupported show template source scope: {show_scope}")


def _show_source_page(
    session: Session,
    show_scope: ShowLocalMediaProfileScope,
    *,
    search: str | None,
    offset: int,
    limit: int,
) -> tuple[list[LocalMediaProfileTemplateSource], bool]:
    relevance = search_relevance_score(
        search,
        Episode.title,
        Show.title,
        Season.name,
        Episode.slug,
        Show.slug,
        Episode.episode_identifier,
        Show.author_name,
        Season.slug,
    )
    ordering = [
        func.lower(Show.title),
        Show.id,
        Episode.index,
        Episode.id,
    ]
    if relevance is not None:
        ordering.insert(0, relevance.desc())

    query = (
        select(Episode)
        .join(Episode.show)
        .join(Episode.season)
        .options(contains_eager(Episode.show), contains_eager(Episode.season))
        .where(Show.type.in_(_show_type_values(show_scope)))
        .where(*search_all_terms(
            search,
            Show.title,
            Show.slug,
            Show.author_name,
            Episode.title,
            Episode.slug,
            Episode.episode_identifier,
            Season.name,
            Season.slug,
        ))
        .order_by(*ordering)
        .offset(offset)
        .limit(limit + 1)
    )
    episodes = list(session.scalars(query).unique().all())
    has_more = len(episodes) > limit
    episodes = episodes[:limit]
    return [
        LocalMediaProfileTemplateSource(
            id=f"episode:{episode.id}",
            label=f"{episode.show.title} — {episode.title}",
            values=episode_output_template_values(episode),
        )
        for episode in episodes
    ], has_more


def _movie_source_page(
    session: Session,
    *,
    search: str | None,
    offset: int,
    limit: int,
) -> tuple[list[LocalMediaProfileTemplateSource], bool]:
    movie_relevance = search_relevance_score(
        search,
        Movie.title,
        Movie.extended_title,
        Movie.slug,
        Movie.author_name,
    )
    if movie_relevance is None:
        movie_relevance = literal(0)

    extra_relevance = search_relevance_score(
        search,
        MovieExtraSource.title,
        Movie.title,
        Movie.extended_title,
        MovieExtraSource.slug,
        Movie.slug,
        MovieExtra.movie_extra_type,
    )
    if extra_relevance is None:
        extra_relevance = literal(0)

    movie_query = (
        select(
            literal("movie").label("kind"),
            Movie.id.label("item_id"),
            Movie.id.label("movie_id"),
            movie_relevance.label("relevance"),
            func.lower(Movie.title).label("group_sort"),
            literal(0).label("kind_sort"),
            func.lower(Movie.title).label("item_sort"),
        )
        .where(*search_all_terms(
            search,
            Movie.title,
            Movie.extended_title,
            Movie.slug,
            Movie.author_name,
        ))
    )
    extra_query = (
        select(
            literal("movie-extra").label("kind"),
            MovieExtra.id.label("item_id"),
            Movie.id.label("movie_id"),
            extra_relevance.label("relevance"),
            func.lower(Movie.title).label("group_sort"),
            literal(1).label("kind_sort"),
            func.lower(MovieExtraSource.title).label("item_sort"),
        )
        .join(Movie, Movie.id == MovieExtra.movie_id)
        .join(MovieExtraSource, MovieExtraSource.id == MovieExtra.source_id)
        .where(*search_all_terms(
            search,
            Movie.title,
            Movie.extended_title,
            Movie.slug,
            MovieExtraSource.title,
            MovieExtraSource.slug,
            MovieExtra.movie_extra_type,
        ))
    )
    candidates = union_all(movie_query, extra_query).subquery()
    ordering = [
        candidates.c.group_sort,
        candidates.c.movie_id,
        candidates.c.kind_sort,
        candidates.c.item_sort,
        candidates.c.item_id,
    ]
    if (search or "").strip():
        ordering.insert(0, candidates.c.relevance.desc())

    rows = session.execute(
        select(
            candidates.c.kind,
            candidates.c.item_id,
            candidates.c.movie_id,
        )
        .order_by(*ordering)
        .offset(offset)
        .limit(limit + 1)
    ).all()
    has_more = len(rows) > limit
    rows = rows[:limit]

    movie_ids = {row.movie_id for row in rows}
    extra_ids = {row.item_id for row in rows if row.kind == "movie-extra"}
    movies = {
        movie.id: movie
        for movie in session.scalars(
            select(Movie).where(Movie.id.in_(movie_ids))
        ).all()
    } if movie_ids else {}
    extras = {
        extra.id: extra
        for extra in session.scalars(
            select(MovieExtra)
            .options(joinedload(MovieExtra.movie))
            .where(MovieExtra.id.in_(extra_ids))
        ).unique().all()
    } if extra_ids else {}

    sources: list[LocalMediaProfileTemplateSource] = []
    for row in rows:
        movie = movies.get(row.movie_id)
        if movie is None:
            continue
        if row.kind == "movie":
            sources.append(LocalMediaProfileTemplateSource(
                id=f"movie:{movie.id}",
                label=movie.title,
                values=movie_output_template_values(movie),
            ))
            continue

        extra = extras.get(row.item_id)
        if extra is None:
            continue
        sources.append(LocalMediaProfileTemplateSource(
            id=f"movie-extra:{extra.id}",
            label=f"{movie.title} — {extra.title}",
            values=movie_output_template_values(movie, extra),
        ))

    return sources, has_more


def get_output_template_source_page(
    session: Session,
    profile_type: LocalMediaProfileType,
    show_scope: ShowLocalMediaProfileScope = ShowLocalMediaProfileScope.BOTH,
    *,
    search: str | None = None,
    offset: int = 0,
    limit: int = 30,
) -> LocalMediaProfileTemplateSourcePage:
    """Search every locally stored media item applicable to a Local Media Profile."""
    if profile_type == LocalMediaProfileType.SHOW:
        sources, has_more = _show_source_page(
            session,
            show_scope,
            search=search,
            offset=offset,
            limit=limit,
        )
        fallback_values = _EXAMPLE_SHOW_VALUES
        fallback_label = "Example show episode"
    elif profile_type == LocalMediaProfileType.MOVIE:
        sources, has_more = _movie_source_page(
            session,
            search=search,
            offset=offset,
            limit=limit,
        )
        fallback_values = _EXAMPLE_MOVIE_VALUES
        fallback_label = "Example movie"
    else:
        raise ValueError("Template examples are only available for Show and Movie profiles")

    if not sources and offset == 0 and not (search or "").strip():
        sources = [LocalMediaProfileTemplateSource(
            id=f"example:{profile_type.value}",
            label=fallback_label,
            values=dict(fallback_values),
            fallback=True,
        )]

    return LocalMediaProfileTemplateSourcePage(
        items=sources,
        offset=offset,
        limit=limit,
        has_more=has_more,
    )


def get_output_template_preview(
    body: LocalMediaProfileTemplatePreview,
) -> LocalMediaProfileTemplatePreviewResult:
    if body.type == LocalMediaProfileType.SHOW:
        allowed_fields = SHOW_OUTPUT_TEMPLATE_FIELDS
        allowed_metadata_scopes = SHOW_OUTPUT_TEMPLATE_METADATA_SCOPES
    elif body.type == LocalMediaProfileType.MOVIE:
        allowed_fields = MOVIE_OUTPUT_TEMPLATE_FIELDS
        allowed_metadata_scopes = MOVIE_OUTPUT_TEMPLATE_METADATA_SCOPES
    else:
        raise ValueError("Template previews are only available for Show and Movie profiles")

    output_path = render_output_template(
        body.output_template,
        body.values,
        allowed_fields=allowed_fields,
        allowed_metadata_scopes=allowed_metadata_scopes,
    )
    extension = body.preferred_format.file_extension
    return LocalMediaProfileTemplatePreviewResult(
        output_path=replace_output_extension(output_path, extension),
        used_variables=sorted(output_template_fields(body.output_template)),
    )
