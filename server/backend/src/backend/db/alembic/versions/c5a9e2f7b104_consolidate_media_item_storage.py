"""Consolidate media-item storage after movie-extra identity.

Revision ID: c5a9e2f7b104
Revises: c9f2d8a1b604
"""

from __future__ import annotations

import json

from alembic import op
import sqlalchemy as sa


revision = "c5a9e2f7b104"
down_revision = "c9f2d8a1b604"
branch_labels = None
depends_on = None


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


def upgrade() -> None:
    bind = op.get_bind()

    # This single migration intentionally contains every schema/data change made
    # after c9f2d8a1b604. Development databases at that revision can therefore
    # advance directly to the current layout without traversing transient feature
    # migrations that have not shipped as a release boundary.
    _drop_dailywire_ids(bind)
    _normalize_movie_extra_sources(bind)
    _move_movie_extra_metadata_to_sources(bind)
    _move_content_metadata_to_owners(bind)
    _remove_promotional_movie_metadata()
    _rename_media_item_tables(bind)


def downgrade() -> None:
    bind = op.get_bind()

    _restore_legacy_media_item_table_names(bind)
    _restore_promotional_movie_metadata()
    _restore_content_metadata_to_media_items(bind)
    _restore_movie_extra_metadata_to_placements(bind)
    _denormalize_movie_extra_sources(bind)
    _restore_dailywire_id_columns(bind)
