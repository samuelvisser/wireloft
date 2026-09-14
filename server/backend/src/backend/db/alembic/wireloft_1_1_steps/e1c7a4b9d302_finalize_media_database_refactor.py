"""Finalize the media database refactor.

Revision ID: e1c7a4b9d302
Revises: c1f7b9e4d205

All schema and data changes developed after ``c1f7b9e4d205`` are intentionally
consolidated here. None of the intermediate development revisions shipped, so
there is no value in keeping transient schemas in the permanent migration path.
"""

from __future__ import annotations

import json

from alembic import op
from alembic.runtime.migration import MigrationContext
from alembic.util import CommandError
import sqlalchemy as sa

from backend.db.alembic_version import (
    SETTINGS_VERSION_COLUMN,
    SETTINGS_VERSION_TABLE,
    apply_settings_version_table,
)


revision = "e1c7a4b9d302"
down_revision = "c1f7b9e4d205"
branch_labels = None
depends_on = None


_LEGACY_VERSION_TABLE = "alembic_version"
_UNMANAGED_TABLES = {"apscheduler_jobs"}
_CONTENT_FIELDS = (
    "title",
    "description",
    "duration",
    "background_image_path",
    "thumbnail_landscape_path",
    "thumbnail_portrait_path",
    "thumbnail_square_path",
)
_SOURCE_FIELDS = (
    *_CONTENT_FIELDS,
    "sharing_url",
    "published_date",
    "available_for",
)


def _column_names(bind, table_name: str) -> set[str]:
    inspector = sa.inspect(bind)
    if not inspector.has_table(table_name):
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def _legacy_version_table() -> sa.Table:
    return sa.Table(
        _LEGACY_VERSION_TABLE,
        sa.MetaData(),
        sa.Column("version_num", sa.String(32), primary_key=True, nullable=False),
    )


def _legacy_revisions(bind) -> tuple[str, ...]:
    return tuple(
        bind.execute(
            sa.select(_legacy_version_table().c.version_num)
        ).scalars()
    )


def _settings_version_rows(bind) -> list[dict]:
    return list(bind.execute(sa.text(
        f"SELECT id, {SETTINGS_VERSION_COLUMN} "
        f"FROM {SETTINGS_VERSION_TABLE} ORDER BY id"
    )).mappings())


def configure_version_storage_for_upgrade(context: MigrationContext) -> None:
    """Select version storage while upgrading across this consolidated boundary."""
    connection = context.connection
    if connection is None:
        return

    inspector = sa.inspect(connection)
    tables = set(inspector.get_table_names())
    application_tables = tables - _UNMANAGED_TABLES

    # A fresh database starts with Alembic's native version table. The
    # consolidated migration switches the same context to Settings at its end.
    if not application_tables:
        return

    settings_has_version = (
        SETTINGS_VERSION_TABLE in tables
        and SETTINGS_VERSION_COLUMN in _column_names(connection, SETTINGS_VERSION_TABLE)
    )
    legacy_exists = _LEGACY_VERSION_TABLE in tables

    # Databases that have not crossed this boundary still use Alembic's native
    # table. Current databases, including ones downgraded by current WireLoft,
    # always use settings.alembic_version_num.
    if legacy_exists:
        return

    if not settings_has_version:
        raise CommandError(
            "Database contains tables but is not Alembic-managed by a supported WireLoft schema. "
            "Delete/recreate it, or manually stamp the correct Alembic revision before upgrading."
        )

    settings_rows = _settings_version_rows(connection)
    if len(settings_rows) != 1 or settings_rows[0][SETTINGS_VERSION_COLUMN] is None:
        raise CommandError(
            "settings.alembic_version_num must contain exactly one current revision before upgrading."
        )

    apply_settings_version_table(context)


def _handoff_version_storage(bind) -> None:
    """Move Alembic's live MigrationContext from its old table into Settings."""
    inspector = sa.inspect(bind)
    if not inspector.has_table(_LEGACY_VERSION_TABLE):
        apply_settings_version_table(op.get_context())
        return

    revisions = _legacy_revisions(bind)
    if len(revisions) != 1:
        raise RuntimeError(
            "Cannot move Alembic version tracking into settings unless the database "
            f"has exactly one current revision; found {revisions}."
        )

    current_revision = revisions[0]
    if current_revision != down_revision:
        raise RuntimeError(
            "The Alembic version-storage handoff can only run while upgrading "
            f"from {down_revision}; found {current_revision}."
        )

    settings_rows = _settings_version_rows(bind)
    if len(settings_rows) != 1:
        raise RuntimeError(
            "The settings table must contain exactly one row before Alembic "
            "version tracking can be moved into it."
        )

    stored_revision = settings_rows[0][SETTINGS_VERSION_COLUMN]
    if stored_revision not in (None, current_revision):
        raise RuntimeError(
            "settings.alembic_version_num disagrees with the legacy Alembic version table."
        )

    bind.execute(
        sa.text(
            f"UPDATE {SETTINGS_VERSION_TABLE} "
            f"SET {SETTINGS_VERSION_COLUMN} = :revision WHERE id = :settings_id"
        ),
        {
            "revision": current_revision,
            "settings_id": settings_rows[0]["id"],
        },
    )

    # Alembic updates c1 -> e1 after upgrade() returns. Switch the live context
    # first so that update goes directly into Settings.
    _legacy_version_table().drop(bind)
    apply_settings_version_table(op.get_context())


def _add_movie_page_metadata() -> None:
    with op.batch_alter_table("movies") as batch:
        batch.add_column(sa.Column("has_video", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column("status", sa.String(), nullable=True))
        batch.add_column(sa.Column("published_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("background", sa.String(), nullable=True))
        batch.add_column(sa.Column("byline", sa.String(), nullable=True))
        batch.add_column(sa.Column("language", sa.String(), nullable=True))
        batch.add_column(sa.Column("origin_country", sa.String(), nullable=True))
        batch.add_column(sa.Column("images", sa.JSON(), nullable=False, server_default="{}"))
        batch.add_column(sa.Column("cast_and_crew", sa.JSON(), nullable=False, server_default="[]"))
        batch.add_column(sa.Column("directed_by", sa.JSON(), nullable=False, server_default="[]"))
        batch.add_column(sa.Column("genres", sa.JSON(), nullable=False, server_default="[]"))
        batch.add_column(sa.Column("hosts", sa.JSON(), nullable=False, server_default="[]"))
        batch.add_column(sa.Column("more_like_this", sa.JSON(), nullable=False, server_default="[]"))
        batch.add_column(sa.Column("production_companies", sa.JSON(), nullable=False, server_default="[]"))
        batch.add_column(sa.Column("shop_items", sa.JSON(), nullable=False, server_default="[]"))
        batch.add_column(sa.Column("starring", sa.JSON(), nullable=False, server_default="[]"))
        batch.add_column(sa.Column("written_by", sa.JSON(), nullable=False, server_default="[]"))

    with op.batch_alter_table("movie_extras") as batch:
        batch.add_column(sa.Column("available_for", sa.JSON(), nullable=False, server_default="[]"))


def _remove_movie_page_metadata() -> None:
    with op.batch_alter_table("movie_extras") as batch:
        batch.drop_column("available_for")

    with op.batch_alter_table("movies") as batch:
        batch.drop_column("written_by")
        batch.drop_column("starring")
        batch.drop_column("shop_items")
        batch.drop_column("production_companies")
        batch.drop_column("more_like_this")
        batch.drop_column("hosts")
        batch.drop_column("genres")
        batch.drop_column("directed_by")
        batch.drop_column("cast_and_crew")
        batch.drop_column("images")
        batch.drop_column("origin_country")
        batch.drop_column("language")
        batch.drop_column("byline")
        batch.drop_column("background")
        batch.drop_column("published_at")
        batch.drop_column("status")
        batch.drop_column("has_video")


def _scope_movie_extra_identity() -> None:
    with op.batch_alter_table("movie_extras") as batch:
        batch.drop_index("ix_movie_extras_dw_id")
        batch.drop_index("ix_movie_extras_slug")
        batch.create_index("ix_movie_extras_dw_id", ["dw_id"], unique=False)
        batch.create_index("ix_movie_extras_slug", ["slug"], unique=False)
        batch.create_unique_constraint(
            "uq_movie_extras_movie_id_dw_id",
            ["movie_id", "dw_id"],
        )
        batch.create_unique_constraint(
            "uq_movie_extras_movie_id_slug",
            ["movie_id", "slug"],
        )


def _restore_global_movie_extra_identity() -> None:
    bind = op.get_bind()
    duplicate_dw_id = bind.execute(sa.text(
        "SELECT dw_id FROM movie_extras "
        "WHERE dw_id IS NOT NULL "
        "GROUP BY dw_id HAVING COUNT(*) > 1 LIMIT 1"
    )).scalar_one_or_none()
    duplicate_slug = bind.execute(sa.text(
        "SELECT slug FROM movie_extras "
        "GROUP BY slug HAVING COUNT(*) > 1 LIMIT 1"
    )).scalar_one_or_none()
    if duplicate_dw_id is not None or duplicate_slug is not None:
        raise RuntimeError(
            "Cannot downgrade movie-extra identity constraints because Daily Wire "
            "clips are currently shared by multiple movies. The older schema "
            "requires globally unique movie-extra IDs and slugs."
        )

    with op.batch_alter_table("movie_extras") as batch:
        batch.drop_constraint("uq_movie_extras_movie_id_slug", type_="unique")
        batch.drop_constraint("uq_movie_extras_movie_id_dw_id", type_="unique")
        batch.drop_index("ix_movie_extras_slug")
        batch.drop_index("ix_movie_extras_dw_id")
        batch.create_index("ix_movie_extras_dw_id", ["dw_id"], unique=True)
        batch.create_index("ix_movie_extras_slug", ["slug"], unique=True)


def _official_trailer_links(bind) -> list[tuple[int, int]]:
    """Snapshot links SQLite may null while batch-rebuilding movie_extras."""
    return [
        (int(row.id), int(row.official_trailer_id))
        for row in bind.execute(sa.text(
            "SELECT id, official_trailer_id FROM movies "
            "WHERE official_trailer_id IS NOT NULL"
        ))
    ]


def _restore_official_trailer_links(bind, links: list[tuple[int, int]]) -> None:
    for movie_id, movie_extra_id in links:
        bind.execute(sa.text(
            "UPDATE movies SET official_trailer_id = :movie_extra_id WHERE id = :movie_id"
        ), {
            "movie_id": movie_id,
            "movie_extra_id": movie_extra_id,
        })


def _as_list(value) -> list[str]:
    if isinstance(value, list):
        return list(value)
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except (TypeError, ValueError):
            return []
        return list(decoded) if isinstance(decoded, list) else []
    return []


def _drop_dailywire_ids(bind) -> None:
    duplicate_movie_slug = bind.execute(sa.text(
        "SELECT slug FROM movies GROUP BY slug HAVING COUNT(*) > 1 LIMIT 1"
    )).scalar_one_or_none()
    if duplicate_movie_slug is not None:
        raise RuntimeError(
            "Cannot make movie slugs the canonical identity because duplicate "
            f"movie slug {duplicate_movie_slug!r} already exists"
        )

    bind.execute(sa.text(
        "UPDATE movies SET release_date_source_id = NULL "
        "WHERE release_date_source = 'dailywire'"
    ))

    official_trailer_links = _official_trailer_links(bind)
    with op.batch_alter_table("movie_extras") as batch:
        batch.drop_constraint("uq_movie_extras_movie_id_dw_id", type_="unique")
        batch.drop_index("ix_movie_extras_dw_id")
        batch.drop_column("dw_id")

    with op.batch_alter_table("movies") as batch:
        batch.drop_index("ix_movies_dw_id")
        batch.drop_column("dw_id")
        batch.create_index("ix_movies_slug", ["slug"], unique=True)
    _restore_official_trailer_links(bind, official_trailer_links)


def _restore_dailywire_id_columns(bind) -> None:
    official_trailer_links = _official_trailer_links(bind)
    with op.batch_alter_table("movies") as batch:
        batch.drop_index("ix_movies_slug")
        batch.add_column(sa.Column("dw_id", sa.String(), nullable=True))
        batch.create_index("ix_movies_dw_id", ["dw_id"], unique=True)

    with op.batch_alter_table("movie_extras") as batch:
        batch.add_column(sa.Column("dw_id", sa.String(), nullable=True))
        batch.create_index("ix_movie_extras_dw_id", ["dw_id"], unique=False)
        batch.create_unique_constraint(
            "uq_movie_extras_movie_id_dw_id",
            ["movie_id", "dw_id"],
        )
    _restore_official_trailer_links(bind, official_trailer_links)


def _normalize_movie_extra_sources(bind) -> None:
    official_trailer_links = _official_trailer_links(bind)

    op.create_table(
        "movie_extra_sources",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("slug", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_movie_extra_sources")),
        sa.UniqueConstraint("slug", name="uq_movie_extra_sources_slug"),
    )
    bind.execute(sa.text(
        "INSERT INTO movie_extra_sources (slug) "
        "SELECT DISTINCT slug FROM movie_extras"
    ))

    with op.batch_alter_table("movie_extras") as batch:
        batch.add_column(sa.Column("source_id", sa.Integer(), nullable=True))

    bind.execute(sa.text(
        "UPDATE movie_extras SET source_id = ("
        "SELECT movie_extra_sources.id FROM movie_extra_sources "
        "WHERE movie_extra_sources.slug = movie_extras.slug"
        ")"
    ))
    unresolved = bind.execute(sa.text(
        "SELECT COUNT(*) FROM movie_extras WHERE source_id IS NULL"
    )).scalar_one()
    if unresolved:
        raise RuntimeError(
            "Could not resolve every existing movie extra to its immutable slug source"
        )

    with op.batch_alter_table("movie_extras") as batch:
        batch.drop_constraint("uq_movie_extras_movie_id_slug", type_="unique")
        batch.drop_index("ix_movie_extras_slug")
        batch.create_index("ix_movie_extras_source_id", ["source_id"], unique=False)
        batch.create_unique_constraint(
            "uq_movie_extras_movie_id_source_id",
            ["movie_id", "source_id"],
        )
        batch.create_foreign_key(
            "fk_movie_extras_source_id_movie_extra_sources",
            "movie_extra_sources",
            ["source_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch.alter_column(
            "source_id",
            existing_type=sa.Integer(),
            nullable=False,
        )
        batch.drop_column("slug")

    _restore_official_trailer_links(bind, official_trailer_links)


def _denormalize_movie_extra_sources(bind) -> None:
    official_trailer_links = _official_trailer_links(bind)

    with op.batch_alter_table("movie_extras") as batch:
        batch.add_column(sa.Column("slug", sa.String(), nullable=True))

    bind.execute(sa.text(
        "UPDATE movie_extras SET slug = ("
        "SELECT movie_extra_sources.slug FROM movie_extra_sources "
        "WHERE movie_extra_sources.id = movie_extras.source_id"
        ")"
    ))
    unresolved = bind.execute(sa.text(
        "SELECT COUNT(*) FROM movie_extras WHERE slug IS NULL"
    )).scalar_one()
    if unresolved:
        raise RuntimeError(
            "Cannot downgrade movie-extra sources because one or more source slugs are missing"
        )

    with op.batch_alter_table("movie_extras") as batch:
        batch.alter_column(
            "slug",
            existing_type=sa.String(),
            nullable=False,
        )
        batch.drop_constraint(
            "fk_movie_extras_source_id_movie_extra_sources",
            type_="foreignkey",
        )
        batch.drop_constraint(
            "uq_movie_extras_movie_id_source_id",
            type_="unique",
        )
        batch.drop_index("ix_movie_extras_source_id")
        batch.drop_column("source_id")
        batch.create_index("ix_movie_extras_slug", ["slug"], unique=False)
        batch.create_unique_constraint(
            "uq_movie_extras_movie_id_slug",
            ["movie_id", "slug"],
        )

    _restore_official_trailer_links(bind, official_trailer_links)
    op.drop_table("movie_extra_sources")


def _add_source_metadata_columns() -> None:
    # Direct ADD COLUMN avoids rebuilding a parent table already referenced by
    # movie_extras.source_id on SQLite.
    op.add_column(
        "movie_extra_sources",
        sa.Column("title", sa.String(), nullable=False, server_default=""),
    )
    op.add_column(
        "movie_extra_sources",
        sa.Column("description", sa.String(), nullable=True),
    )
    op.add_column(
        "movie_extra_sources",
        sa.Column("duration", sa.Float(), nullable=False, server_default="0"),
    )
    op.add_column(
        "movie_extra_sources",
        sa.Column("background_image_path", sa.String(), nullable=True),
    )
    op.add_column(
        "movie_extra_sources",
        sa.Column("thumbnail_landscape_path", sa.String(), nullable=True),
    )
    op.add_column(
        "movie_extra_sources",
        sa.Column("thumbnail_portrait_path", sa.String(), nullable=True),
    )
    op.add_column(
        "movie_extra_sources",
        sa.Column("thumbnail_square_path", sa.String(), nullable=True),
    )
    op.add_column(
        "movie_extra_sources",
        sa.Column("sharing_url", sa.String(), nullable=True),
    )
    op.add_column(
        "movie_extra_sources",
        sa.Column("published_date", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "movie_extra_sources",
        sa.Column("available_for", sa.JSON(), nullable=False, server_default="[]"),
    )


def _backfill_source_metadata(bind) -> None:
    metadata = sa.MetaData()
    sources = sa.Table("movie_extra_sources", metadata, autoload_with=bind)
    extras = sa.Table("movie_extras", metadata, autoload_with=bind)
    media_items = sa.Table("media_items", metadata, autoload_with=bind)

    merged: dict[int, dict] = {
        int(row.id): {
            "slug": row.slug,
            "title": "",
            "description": None,
            "duration": 0.0,
            "background_image_path": None,
            "thumbnail_landscape_path": None,
            "thumbnail_portrait_path": None,
            "thumbnail_square_path": None,
            "sharing_url": None,
            "published_date": None,
            "available_for": [],
        }
        for row in bind.execute(sa.select(sources.c.id, sources.c.slug))
    }

    rows = bind.execute(
        sa.select(
            extras.c.source_id,
            extras.c.id.label("placement_id"),
            media_items.c.updated_at,
            media_items.c.title,
            media_items.c.description,
            media_items.c.duration,
            media_items.c.background_image_path,
            media_items.c.thumbnail_landscape_path,
            media_items.c.thumbnail_portrait_path,
            media_items.c.thumbnail_square_path,
            extras.c.sharing_url,
            extras.c.published_date,
            extras.c.available_for,
        )
        .select_from(extras.join(media_items, media_items.c.id == extras.c.id))
        .order_by(
            extras.c.source_id,
            media_items.c.updated_at.desc(),
            extras.c.id.desc(),
        )
    ).mappings()

    for row in rows:
        values = merged[int(row["source_id"])]
        if not values["title"] and row["title"]:
            values["title"] = row["title"]
        if values["description"] is None and row["description"] is not None:
            values["description"] = row["description"]
        if values["duration"] <= 0 and row["duration"] and row["duration"] > 0:
            values["duration"] = float(row["duration"])
        for field in (
            "background_image_path",
            "thumbnail_landscape_path",
            "thumbnail_portrait_path",
            "thumbnail_square_path",
            "sharing_url",
            "published_date",
        ):
            if values[field] is None and row[field] is not None:
                values[field] = row[field]
        if not values["available_for"]:
            values["available_for"] = _as_list(row["available_for"])

    for source_id, values in merged.items():
        values["title"] = values["title"] or values.pop("slug")
        bind.execute(
            sa.update(sources)
            .where(sources.c.id == source_id)
            .values(**{field: values[field] for field in _SOURCE_FIELDS})
        )

    bind.execute(
        sa.update(media_items)
        .where(media_items.c.type == "movie_extra")
        .values(
            title="",
            description=None,
            duration=0.0,
            background_image_path=None,
            thumbnail_landscape_path=None,
            thumbnail_portrait_path=None,
            thumbnail_square_path=None,
        )
    )


def _move_movie_extra_metadata_to_sources(bind) -> None:
    _add_source_metadata_columns()
    _backfill_source_metadata(bind)

    official_trailer_links = _official_trailer_links(bind)
    with op.batch_alter_table("movie_extras") as batch:
        batch.drop_column("available_for")
        batch.drop_column("published_date")
        batch.drop_column("sharing_url")
    _restore_official_trailer_links(bind, official_trailer_links)


def _restore_movie_extra_metadata_to_placements(bind) -> None:
    op.add_column(
        "movie_extras",
        sa.Column("sharing_url", sa.String(), nullable=True),
    )
    op.add_column(
        "movie_extras",
        sa.Column("published_date", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "movie_extras",
        sa.Column("available_for", sa.JSON(), nullable=False, server_default="[]"),
    )

    metadata = sa.MetaData()
    sources = sa.Table("movie_extra_sources", metadata, autoload_with=bind)
    extras = sa.Table("movie_extras", metadata, autoload_with=bind)
    media_items = sa.Table("media_items", metadata, autoload_with=bind)

    rows = bind.execute(
        sa.select(
            extras.c.id.label("placement_id"),
            sources.c.title,
            sources.c.description,
            sources.c.duration,
            sources.c.background_image_path,
            sources.c.thumbnail_landscape_path,
            sources.c.thumbnail_portrait_path,
            sources.c.thumbnail_square_path,
            sources.c.sharing_url,
            sources.c.published_date,
            sources.c.available_for,
        ).select_from(extras.join(sources, sources.c.id == extras.c.source_id))
    ).mappings()

    for row in rows:
        placement_id = int(row["placement_id"])
        bind.execute(
            sa.update(media_items)
            .where(media_items.c.id == placement_id)
            .values(
                title=row["title"],
                description=row["description"],
                duration=row["duration"],
                background_image_path=row["background_image_path"],
                thumbnail_landscape_path=row["thumbnail_landscape_path"],
                thumbnail_portrait_path=row["thumbnail_portrait_path"],
                thumbnail_square_path=row["thumbnail_square_path"],
            )
        )
        bind.execute(
            sa.update(extras)
            .where(extras.c.id == placement_id)
            .values(
                sharing_url=row["sharing_url"],
                published_date=row["published_date"],
                available_for=_as_list(row["available_for"]),
            )
        )

    for column in reversed(_SOURCE_FIELDS):
        op.drop_column("movie_extra_sources", column)


def _add_content_columns(table_name: str) -> None:
    op.add_column(
        table_name,
        sa.Column("title", sa.String(), nullable=False, server_default=""),
    )
    op.add_column(
        table_name,
        sa.Column("description", sa.String(), nullable=True),
    )
    op.add_column(
        table_name,
        sa.Column("duration", sa.Float(), nullable=False, server_default="0"),
    )
    op.add_column(
        table_name,
        sa.Column("background_image_path", sa.String(), nullable=True),
    )
    op.add_column(
        table_name,
        sa.Column("thumbnail_landscape_path", sa.String(), nullable=True),
    )
    op.add_column(
        table_name,
        sa.Column("thumbnail_portrait_path", sa.String(), nullable=True),
    )
    op.add_column(
        table_name,
        sa.Column("thumbnail_square_path", sa.String(), nullable=True),
    )


def _copy_content_metadata(
    bind,
    *,
    source_table_name: str,
    target_table_name: str,
) -> None:
    metadata = sa.MetaData()
    source = sa.Table(source_table_name, metadata, autoload_with=bind)
    target = sa.Table(target_table_name, metadata, autoload_with=bind)

    values = {
        field: (
            sa.select(source.c[field])
            .where(source.c.id == target.c.id)
            .scalar_subquery()
        )
        for field in _CONTENT_FIELDS
    }
    bind.execute(sa.update(target).values(**values))


def _move_content_metadata_to_owners(bind) -> None:
    _add_content_columns("episodes")
    _add_content_columns("movies")
    _copy_content_metadata(
        bind,
        source_table_name="media_items",
        target_table_name="episodes",
    )
    _copy_content_metadata(
        bind,
        source_table_name="media_items",
        target_table_name="movies",
    )

    for field in reversed(_CONTENT_FIELDS):
        op.drop_column("media_items", field)


def _restore_content_metadata_to_media_items(bind) -> None:
    _add_content_columns("media_items")

    metadata = sa.MetaData()
    media_items = sa.Table("media_items", metadata, autoload_with=bind)
    episodes = sa.Table("episodes", metadata, autoload_with=bind)
    movies = sa.Table("movies", metadata, autoload_with=bind)

    for concrete in (episodes, movies):
        bind.execute(
            sa.update(media_items)
            .where(media_items.c.id.in_(sa.select(concrete.c.id)))
            .values(**{
                field: (
                    sa.select(concrete.c[field])
                    .where(concrete.c.id == media_items.c.id)
                    .scalar_subquery()
                )
                for field in _CONTENT_FIELDS
            })
        )

    bind.execute(
        sa.update(media_items)
        .where(media_items.c.type == "movie_extra")
        .values(
            title="",
            description=None,
            duration=0.0,
            background_image_path=None,
            thumbnail_landscape_path=None,
            thumbnail_portrait_path=None,
            thumbnail_square_path=None,
        )
    )

    for field in reversed(_CONTENT_FIELDS):
        op.drop_column("movies", field)
        op.drop_column("episodes", field)


def _remove_promotional_movie_metadata() -> None:
    op.drop_column("movies", "shop_items")
    op.drop_column("movies", "more_like_this")


def _restore_promotional_movie_metadata() -> None:
    op.add_column(
        "movies",
        sa.Column("more_like_this", sa.JSON(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "movies",
        sa.Column("shop_items", sa.JSON(), nullable=False, server_default="[]"),
    )


def _rename_media_item_tables(bind) -> None:
    op.rename_table("episodes", "media_items_episodes")
    op.rename_table("movie_extras", "media_items_movie_extras")
    op.rename_table("movies", "media_items_movies")
    bind.execute(sa.text(
        "UPDATE metadata SET parent_table = 'media_items_episodes' "
        "WHERE parent_table = 'episodes'"
    ))


def _restore_legacy_media_item_table_names(bind) -> None:
    bind.execute(sa.text(
        "UPDATE metadata SET parent_table = 'episodes' "
        "WHERE parent_table = 'media_items_episodes'"
    ))
    op.rename_table("media_items_movie_extras", "movie_extras")
    op.rename_table("media_items_movies", "movies")
    op.rename_table("media_items_episodes", "episodes")


def _rename_series_profile_fk_column(old_name: str, new_name: str) -> None:
    bind = op.get_bind()
    columns = _column_names(bind, "download_profile_series_seasons")

    if new_name in columns:
        if old_name in columns:
            raise RuntimeError(
                "download_profile_series_seasons contains both the old and new "
                "series-profile foreign-key columns"
            )
        return
    if old_name not in columns:
        raise RuntimeError(
            "download_profile_series_seasons contains neither expected "
            f"series-profile foreign-key column ({old_name!r}, {new_name!r})"
        )

    with op.batch_alter_table("download_profile_series_seasons") as batch_op:
        batch_op.alter_column(
            old_name,
            new_column_name=new_name,
            existing_type=sa.Integer(),
            existing_nullable=True,
        )


def _rename_table_if_needed(bind, old_name: str, new_name: str) -> None:
    tables = set(sa.inspect(bind).get_table_names())
    old_exists = old_name in tables
    new_exists = new_name in tables

    if new_exists and not old_exists:
        return
    if old_exists and not new_exists:
        op.rename_table(old_name, new_name)
        return
    if old_exists and new_exists:
        raise RuntimeError(
            f"Cannot resume migration because both {old_name!r} and {new_name!r} exist"
        )
    raise RuntimeError(
        f"Cannot resume migration because neither {old_name!r} nor {new_name!r} exists"
    )


def _drop_column_if_present(bind, table_name: str, column_name: str) -> None:
    if column_name in _column_names(bind, table_name):
        op.drop_column(table_name, column_name)


def _add_column_if_missing(bind, table_name: str, column: sa.Column) -> None:
    if column.name not in _column_names(bind, table_name):
        op.add_column(table_name, column)


def _episode_table_name(bind) -> str:
    tables = set(sa.inspect(bind).get_table_names())
    old_exists = "media_items_episodes" in tables
    new_exists = "media_items_episode" in tables

    if old_exists == new_exists:
        raise RuntimeError(
            "Expected exactly one of 'media_items_episodes' or 'media_items_episode'"
        )
    return "media_items_episodes" if old_exists else "media_items_episode"


def _finalize_media_item_schema(bind) -> None:
    _add_column_if_missing(
        bind,
        SETTINGS_VERSION_TABLE,
        sa.Column(SETTINGS_VERSION_COLUMN, sa.String(length=32), nullable=True),
    )

    _rename_series_profile_fk_column(
        "series_download_profile_id",
        "download_profiles_series_id",
    )

    # Download timestamps belong to concrete MediaDownload artifacts rather than
    # their logical media items.
    _drop_column_if_present(bind, "media_items", "downloaded_date")
    _drop_column_if_present(bind, _episode_table_name(bind), "redownloaded_date")

    _rename_table_if_needed(bind, "media_items_episodes", "media_items_episode")
    _rename_table_if_needed(bind, "media_items_movie_extras", "media_items_movie_extra")
    _rename_table_if_needed(bind, "media_items_movies", "media_items_movie")

    bind.execute(sa.text(
        "UPDATE metadata SET parent_table = 'media_items_episode' "
        "WHERE parent_table = 'media_items_episodes'"
    ))


def _restore_pre_refactor_media_item_schema(bind) -> None:
    bind.execute(sa.text(
        "UPDATE metadata SET parent_table = 'media_items_episodes' "
        "WHERE parent_table = 'media_items_episode'"
    ))

    _rename_table_if_needed(bind, "media_items_movie_extra", "media_items_movie_extras")
    _rename_table_if_needed(bind, "media_items_movie", "media_items_movies")
    _rename_table_if_needed(bind, "media_items_episode", "media_items_episodes")

    _add_column_if_missing(
        bind,
        "media_items_episodes",
        sa.Column("redownloaded_date", sa.DateTime(), nullable=True),
    )
    _add_column_if_missing(
        bind,
        "media_items",
        sa.Column("downloaded_date", sa.DateTime(), nullable=True),
    )

    _rename_series_profile_fk_column(
        "download_profiles_series_id",
        "series_download_profile_id",
    )


def _repair_movie_extra_classifications(bind) -> None:
    """Make the explicit official-trailer relationship authoritative once."""
    bind.execute(sa.text(
        """
        UPDATE media_items_movie_extra
        SET movie_extra_type = 'trailer'
        WHERE id IN (
            SELECT official_trailer_id
            FROM media_items_movie
            WHERE official_trailer_id IS NOT NULL
        )
        """
    ))


def upgrade() -> None:
    bind = op.get_bind()

    # Preserve the exact sequence of the former development migrations while
    # exposing only one durable Alembic revision after c1.
    _add_movie_page_metadata()
    _scope_movie_extra_identity()
    _drop_dailywire_ids(bind)
    _normalize_movie_extra_sources(bind)
    _move_movie_extra_metadata_to_sources(bind)
    _move_content_metadata_to_owners(bind)
    _remove_promotional_movie_metadata()
    _rename_media_item_tables(bind)
    _finalize_media_item_schema(bind)
    _repair_movie_extra_classifications(bind)

    # Version-storage compatibility belongs to this one migration boundary. The
    # current WireLoft migration service only understands Settings afterwards.
    _handoff_version_storage(bind)


def downgrade() -> None:
    bind = op.get_bind()

    # Trailer classifications cannot be reconstructed after they are corrected;
    # leave the corrected value in place while reversing the schema changes.
    _restore_pre_refactor_media_item_schema(bind)
    _restore_legacy_media_item_table_names(bind)
    _restore_promotional_movie_metadata()
    _restore_content_metadata_to_media_items(bind)
    _restore_movie_extra_metadata_to_placements(bind)
    _denormalize_movie_extra_sources(bind)
    _restore_dailywire_id_columns(bind)
    _restore_global_movie_extra_identity()
    _remove_movie_page_metadata()

    # Version tracking is migration-runner infrastructure rather than application
    # schema state. Once moved into Settings, keep it there even below this
    # application-schema revision so current WireLoft can still operate on the DB.
