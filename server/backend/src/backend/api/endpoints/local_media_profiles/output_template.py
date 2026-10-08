from __future__ import annotations

import hashlib
from sqlalchemy import and_, case, func, literal, or_, select, union_all
from sqlalchemy.orm import Session, contains_eager, joinedload

from backend.api.pagination import (
    InvalidCursorError,
    KeysetField,
    cursor_key_values,
    decode_cursor,
    encode_cursor,
    keyset_after,
)
from backend.api.models.local_media_profile import (
    LocalMediaProfileTemplatePreview,
    LocalMediaProfileTemplatePreviewResult,
    LocalMediaProfileTemplateSource,
    LocalMediaProfileTemplateSourcePage,
    LocalMediaProfileTemplateVariable,
)
from backend.db.models import Episode, Movie, MovieExtra, MovieExtraSource, Season, Show, ShowLocalMediaProfile
from backend.services.custom_index_preview import (
    CustomIndexPreviewMode,
    plan_custom_index_preview,
)
from backend.services.custom_indexes import simulate_episode_indexes
from backend.types.local_media_profile_types import (
    LocalMediaProfileType,
    PreferredFormat,
    ShowLocalMediaProfileScope,
)
from backend.types.show_types import ShowType
from backend.utils.custom_index import indexing_value_definition_keys
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
    output_template_custom_index_keys,
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
    "episode_index": "1",
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


def _show_template_source(episode: Episode) -> LocalMediaProfileTemplateSource:
    return LocalMediaProfileTemplateSource(
        id=f"episode:{episode.id}",
        label=f"{episode.show.title} — {episode.title}",
        values=episode_output_template_values(episode),
    )


def _show_source_anchor_offset(
    session: Session,
    show_scope: ShowLocalMediaProfileScope,
    source_id: str,
    *,
    limit: int,
) -> int | None:
    """Return a page offset that keeps one selected Episode near the middle of the page."""
    kind, separator, identifier = source_id.partition(":")
    if kind != "episode" or not separator or not identifier.isascii() or not identifier.isdigit():
        return None

    episode = session.scalar(
        select(Episode)
        .options(joinedload(Episode.show))
        .where(Episode.id == int(identifier))
    )
    if episode is None or episode.show.type not in _show_type_values(show_scope):
        return None

    show_title = episode.show.title.lower()
    before_anchor = or_(
        func.lower(Show.title) < show_title,
        and_(func.lower(Show.title) == show_title, Show.id < episode.show_id),
        and_(
            func.lower(Show.title) == show_title,
            Show.id == episode.show_id,
            Episode.index < episode.index,
        ),
        and_(
            func.lower(Show.title) == show_title,
            Show.id == episode.show_id,
            Episode.index == episode.index,
            Episode.id < episode.id,
        ),
    )
    position = session.scalar(
        select(func.count())
        .select_from(Episode)
        .join(Episode.show)
        .join(Episode.season)
        .where(Show.type.in_(_show_type_values(show_scope)))
        .where(before_anchor)
    ) or 0
    return max(0, position - limit // 2)


def _modified_timestamp(model):
    return func.max(case(
        (model.updated_at > model.created_at, model.updated_at),
        else_=None,
    ))


def _show_source_revision(
    session: Session,
    show_scope: ShowLocalMediaProfileScope,
) -> str:
    episode_changed, show_changed, season_changed = session.execute(
        select(
            _modified_timestamp(Episode),
            _modified_timestamp(Show),
            _modified_timestamp(Season),
        )
        .select_from(Episode)
        .join(Episode.show)
        .join(Episode.season)
        .where(Show.type.in_(_show_type_values(show_scope)))
    ).one()
    return "|".join(
        value.isoformat() if value is not None else ""
        for value in (episode_changed, show_changed, season_changed)
    )


def _movie_source_revision(session: Session) -> str:
    movie_changed = session.scalar(
        select(_modified_timestamp(Movie)).select_from(Movie)
    )
    extra_changed = session.scalar(
        select(_modified_timestamp(MovieExtra)).select_from(MovieExtra)
    )

    # MovieExtraSource predates the common created/updated timestamp mixin.
    # Fingerprint only the fields that affect source ordering/search so metadata
    # edits are still detected. Inserts/deletes may conservatively change this
    # revision; that restarts from the head rather than risking a mixed order.
    source_rows = session.execute(
        select(
            MovieExtraSource.id,
            MovieExtraSource.slug,
            MovieExtraSource.title,
        ).order_by(MovieExtraSource.id)
    ).all()
    source_fingerprint = hashlib.sha256(
        "\n".join(
            f"{row.id}\0{row.slug}\0{row.title}"
            for row in source_rows
        ).encode("utf-8")
    ).hexdigest()[:16]

    return "|".join([
        movie_changed.isoformat() if movie_changed is not None else "",
        extra_changed.isoformat() if extra_changed is not None else "",
        source_fingerprint,
    ])


def _show_source_page(
    session: Session,
    show_scope: ShowLocalMediaProfileScope,
    *,
    search: str | None,
    cursor: str | None,
    limit: int,
    anchor_offset: int | None = None,
) -> tuple[list[LocalMediaProfileTemplateSource], str | None, str | None, str]:
    search_text = (search or "").strip()
    revision = _show_source_revision(session, show_scope)
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
    relevance_expr = relevance if relevance is not None else literal(0)
    group_sort = func.lower(Show.title)

    natural_fields = [
        (relevance_expr, True),
        (group_sort, False),
        (Show.id, False),
        (Episode.index, False),
        (Episode.id, False),
    ] if relevance is not None else [
        (group_sort, False),
        (Show.id, False),
        (Episode.index, False),
        (Episode.id, False),
    ]

    direction = "next"
    cursor_values: list[object] | None = None
    cursor_applied = False
    if cursor:
        try:
            values = decode_cursor(cursor)
            if (
                values.get("kind") != "template-show"
                or values.get("scope") != show_scope.value
                or values.get("search") != search_text
                or values.get("direction") not in {"next", "previous"}
            ):
                raise InvalidCursorError("Cursor does not match this template source collection")
            if values.get("revision") == revision:
                cursor_values = cursor_key_values(
                    values,
                    length=len(natural_fields),
                )
                direction = values["direction"]
                cursor_applied = True
        except InvalidCursorError as exc:
            raise ValueError(str(exc)) from exc

    query = (
        select(
            Episode,
            relevance_expr.label("relevance"),
            group_sort.label("group_sort"),
        )
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
    )

    query_fields = natural_fields
    if direction == "previous":
        query_fields = [(expr, not descending) for expr, descending in natural_fields]

    if cursor_values is not None:
        query = query.where(keyset_after([
            KeysetField(expr, value, descending=descending)
            for (expr, descending), value in zip(query_fields, cursor_values, strict=True)
        ]))

    ordering = [
        expr.desc() if descending else expr.asc()
        for expr, descending in query_fields
    ]
    query = query.order_by(*ordering)
    if cursor is None and anchor_offset:
        query = query.offset(anchor_offset)

    raw_rows = session.execute(query.limit(limit + 1)).unique().all()
    has_extra = len(raw_rows) > limit
    raw_rows = raw_rows[:limit]

    has_previous = (
        has_extra if direction == "previous"
        else cursor_applied or bool(anchor_offset)
    )
    has_next = (
        True if direction == "previous" and cursor_applied
        else has_extra
    )
    if direction == "previous":
        raw_rows.reverse()

    def row_key(row) -> list[object]:
        episode = row[0]
        values: list[object] = []
        if relevance is not None:
            values.append(int(row._mapping["relevance"]))
        values.extend([
            row._mapping["group_sort"],
            episode.show_id,
            episode.index,
            episode.id,
        ])
        return values

    previous_cursor = None
    next_cursor = None
    if has_previous and raw_rows:
        previous_cursor = encode_cursor({
            "kind": "template-show",
            "scope": show_scope.value,
            "search": search_text,
            "direction": "previous",
            "revision": revision,
            "key": row_key(raw_rows[0]),
        })
    if has_next and raw_rows:
        next_cursor = encode_cursor({
            "kind": "template-show",
            "scope": show_scope.value,
            "search": search_text,
            "direction": "next",
            "revision": revision,
            "key": row_key(raw_rows[-1]),
        })

    return [
        _show_template_source(row[0])
        for row in raw_rows
    ], next_cursor, previous_cursor, revision


def get_random_show_template_source(
    session: Session,
    show_scope: ShowLocalMediaProfileScope = ShowLocalMediaProfileScope.BOTH,
) -> LocalMediaProfileTemplateSource | None:
    """Choose an example uniformly by Show, then uniformly within that Show."""
    show_id = session.scalar(
        select(Episode.show_id)
        .join(Episode.show)
        .join(Episode.season)
        .where(Show.type.in_(_show_type_values(show_scope)))
        .group_by(Episode.show_id)
        .order_by(func.random())
        .limit(1)
    )
    if show_id is None:
        return None

    episode = session.scalar(
        select(Episode)
        .join(Episode.season)
        .where(Episode.show_id == show_id)
        .order_by(func.random())
        .limit(1)
    )
    return _show_template_source(episode) if episode is not None else None


def _movie_source_page(
    session: Session,
    *,
    search: str | None,
    cursor: str | None,
    limit: int,
) -> tuple[list[LocalMediaProfileTemplateSource], str | None, str | None, str]:
    search_text = (search or "").strip()
    revision = _movie_source_revision(session)
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

    natural_fields = [
        (candidates.c.relevance, True),
        (candidates.c.group_sort, False),
        (candidates.c.movie_id, False),
        (candidates.c.kind_sort, False),
        (candidates.c.item_sort, False),
        (candidates.c.item_id, False),
    ] if search_text else [
        (candidates.c.group_sort, False),
        (candidates.c.movie_id, False),
        (candidates.c.kind_sort, False),
        (candidates.c.item_sort, False),
        (candidates.c.item_id, False),
    ]

    direction = "next"
    cursor_values: list[object] | None = None
    cursor_applied = False
    if cursor:
        try:
            values = decode_cursor(cursor)
            if (
                values.get("kind") != "template-movie"
                or values.get("search") != search_text
                or values.get("direction") not in {"next", "previous"}
            ):
                raise InvalidCursorError("Cursor does not match this template source collection")
            if values.get("revision") == revision:
                cursor_values = cursor_key_values(
                    values,
                    length=len(natural_fields),
                )
                direction = values["direction"]
                cursor_applied = True
        except InvalidCursorError as exc:
            raise ValueError(str(exc)) from exc

    query_fields = natural_fields
    if direction == "previous":
        query_fields = [(expr, not descending) for expr, descending in natural_fields]

    stmt = select(
        candidates.c.kind,
        candidates.c.item_id,
        candidates.c.movie_id,
        candidates.c.relevance,
        candidates.c.group_sort,
        candidates.c.kind_sort,
        candidates.c.item_sort,
    )
    if cursor_values is not None:
        stmt = stmt.where(keyset_after([
            KeysetField(expr, value, descending=descending)
            for (expr, descending), value in zip(query_fields, cursor_values, strict=True)
        ]))
    stmt = stmt.order_by(*[
        expr.desc() if descending else expr.asc()
        for expr, descending in query_fields
    ])

    raw_rows = session.execute(stmt.limit(limit + 1)).all()
    has_extra = len(raw_rows) > limit
    raw_rows = raw_rows[:limit]
    has_previous = has_extra if direction == "previous" else cursor_applied
    has_next = True if direction == "previous" and cursor_applied else has_extra
    if direction == "previous":
        raw_rows.reverse()

    def row_key(row) -> list[object]:
        values: list[object] = []
        if search_text:
            values.append(int(row.relevance))
        values.extend([
            row.group_sort,
            row.movie_id,
            row.kind_sort,
            row.item_sort,
            row.item_id,
        ])
        return values

    previous_cursor = None
    next_cursor = None
    if has_previous and raw_rows:
        previous_cursor = encode_cursor({
            "kind": "template-movie",
            "search": search_text,
            "direction": "previous",
            "revision": revision,
            "key": row_key(raw_rows[0]),
        })
    if has_next and raw_rows:
        next_cursor = encode_cursor({
            "kind": "template-movie",
            "search": search_text,
            "direction": "next",
            "revision": revision,
            "key": row_key(raw_rows[-1]),
        })

    movie_ids = {row.movie_id for row in raw_rows}
    extra_ids = {row.item_id for row in raw_rows if row.kind == "movie-extra"}
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
    for row in raw_rows:
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

    return sources, next_cursor, previous_cursor, revision


def get_output_template_source_page(
    session: Session,
    profile_type: LocalMediaProfileType,
    show_scope: ShowLocalMediaProfileScope = ShowLocalMediaProfileScope.BOTH,
    *,
    search: str | None = None,
    cursor: str | None = None,
    limit: int = 30,
    anchor_source_id: str | None = None,
) -> LocalMediaProfileTemplateSourcePage:
    """Search locally stored media with stable bidirectional cursor pagination."""
    if profile_type == LocalMediaProfileType.SHOW:
        anchor_offset = None
        if cursor is None and anchor_source_id and not (search or "").strip():
            anchor_offset = _show_source_anchor_offset(
                session,
                show_scope,
                anchor_source_id,
                limit=limit,
            )
        sources, next_cursor, previous_cursor, revision = _show_source_page(
            session,
            show_scope,
            search=search,
            cursor=cursor,
            limit=limit,
            anchor_offset=anchor_offset,
        )
        fallback_values = _EXAMPLE_SHOW_VALUES
        fallback_label = "Example show episode"
    elif profile_type == LocalMediaProfileType.MOVIE:
        sources, next_cursor, previous_cursor, revision = _movie_source_page(
            session,
            search=search,
            cursor=cursor,
            limit=limit,
        )
        fallback_values = _EXAMPLE_MOVIE_VALUES
        fallback_label = "Example movie"
    else:
        raise ValueError("Template examples are only available for Show and Movie profiles")

    if not sources and cursor is None and not (search or "").strip():
        sources = [LocalMediaProfileTemplateSource(
            id=f"example:{profile_type.value}",
            label=fallback_label,
            values=dict(fallback_values),
            fallback=True,
        )]

    return LocalMediaProfileTemplateSourcePage(
        items=sources,
        limit=limit,
        next_cursor=next_cursor,
        previous_cursor=previous_cursor,
        revision=revision,
    )


class _PersistedPreviewAssignmentMissing(Exception):
    pass


def _simulate_show_preview_assignments(
    session: Session | None,
    episode: Episode | None,
    body: LocalMediaProfileTemplatePreview,
    definitions: frozenset[str],
) -> dict[str, int]:
    if session is None or episode is None:
        return {}
    episodes = list(session.scalars(
        select(Episode)
        .options(joinedload(Episode.show), joinedload(Episode.season))
        .where(
            Episode.show_id == episode.show_id,
            Episode.index <= episode.index,
        )
        .order_by(Episode.index.asc(), Episode.id.asc())
    ).unique().all())
    return simulate_episode_indexes(
        episodes,
        template=body.output_template,
        definitions=definitions,
        values_overrides={episode.id: body.values},
    )[episode.id]


def _render_show_preview(
    session: Session | None,
    body: LocalMediaProfileTemplatePreview,
    *,
    index_keys: frozenset[str],
) -> tuple[str, frozenset[str], frozenset[str]]:
    if not index_keys:
        return (
            render_output_template(
                body.output_template,
                body.values,
                allowed_fields=SHOW_OUTPUT_TEMPLATE_FIELDS,
                allowed_metadata_scopes=SHOW_OUTPUT_TEMPLATE_METADATA_SCOPES,
            ),
            frozenset(),
            frozenset(),
        )

    profile = (
        session.get(ShowLocalMediaProfile, body.local_media_profile_id)
        if (
            body.indexing_values is None
            and session is not None
            and body.local_media_profile_id is not None
        )
        else None
    )
    definitions = (
        frozenset(item.key for item in body.indexing_values)
        if body.indexing_values is not None
        else indexing_value_definition_keys(profile) if profile is not None else frozenset()
    )
    if not index_keys & definitions:
        return (
            render_output_template(
                body.output_template,
                body.values,
                allowed_fields=SHOW_OUTPUT_TEMPLATE_FIELDS,
                allowed_metadata_scopes=SHOW_OUTPUT_TEMPLATE_METADATA_SCOPES,
                custom_index_resolver=lambda _key: "",
            ),
            definitions,
            frozenset(),
        )

    source_id = body.source_id or ""
    episode: Episode | None = None
    if session is not None and source_id.startswith("episode:"):
        try:
            episode = session.get(Episode, int(source_id.split(":", 1)[1]))
        except ValueError:
            episode = None
    plan = plan_custom_index_preview(
        session,
        draft_template=body.output_template,
        draft_definition_keys=definitions,
        episode=episode,
        local_media_profile_id=body.local_media_profile_id,
        draft_values=body.values,
        referenced_keys=index_keys,
    )
    assignments = (
        _simulate_show_preview_assignments(session, episode, body, definitions)
        if plan.mode == CustomIndexPreviewMode.SIMULATE
        else plan.persisted_assignments
    )
    provisional: dict[str, int] = {}

    def resolve_index(key: str) -> object:
        if key not in definitions:
            return ""
        if plan.mode == CustomIndexPreviewMode.USE_PERSISTED and key not in assignments:
            raise _PersistedPreviewAssignmentMissing(key)
        if key not in assignments:
            provisional[key] = 1
        return assignments.get(key, 1)

    def render(assignments_for_render: dict[str, int]) -> str:
        nonlocal assignments
        assignments = assignments_for_render
        return render_output_template(
            body.output_template,
            body.values,
            allowed_fields=SHOW_OUTPUT_TEMPLATE_FIELDS,
            allowed_metadata_scopes=SHOW_OUTPUT_TEMPLATE_METADATA_SCOPES,
            custom_index_resolver=resolve_index if index_keys else None,
        )

    try:
        output_path = render(assignments)
    except _PersistedPreviewAssignmentMissing:
        # Defensive fallback for incomplete/corrupt persisted state. Static
        # equivalence is only an optimization; it must never change preview
        # correctness.
        provisional.clear()
        output_path = render(
            _simulate_show_preview_assignments(session, episode, body, definitions)
        )
    return output_path, definitions, frozenset(provisional)


def get_output_template_preview(
    session: Session | None,
    body: LocalMediaProfileTemplatePreview,
) -> LocalMediaProfileTemplatePreviewResult:
    index_keys = output_template_custom_index_keys(body.output_template)
    definition_keys: frozenset[str] = frozenset()
    provisional_keys: frozenset[str] = frozenset()
    if body.type == LocalMediaProfileType.SHOW:
        output_path, definition_keys, provisional_keys = _render_show_preview(
            session,
            body,
            index_keys=index_keys,
        )
    elif body.type == LocalMediaProfileType.MOVIE:
        if index_keys:
            raise ValueError("custom_index is only available to Show Local Media Profiles")
        output_path = render_output_template(
            body.output_template,
            body.values,
            allowed_fields=MOVIE_OUTPUT_TEMPLATE_FIELDS,
            allowed_metadata_scopes=MOVIE_OUTPUT_TEMPLATE_METADATA_SCOPES,
        )
    else:
        raise ValueError("Template previews are only available for Show and Movie profiles")

    if body.preferred_format == PreferredFormat.FORMAT_AUDIO_ONLY:
        extension = "m4a"
    elif body.preferred_format == PreferredFormat.FORMAT_HLS:
        extension = "m3u8"
    else:
        extension = "mp4"
    return LocalMediaProfileTemplatePreviewResult(
        output_path=replace_output_extension(output_path, extension),
        used_variables=sorted(output_template_fields(body.output_template)),
        used_indexing_values=sorted(index_keys),
        missing_indexing_values=sorted(index_keys - definition_keys),
        provisional_indexing_values=sorted(provisional_keys),
    )
