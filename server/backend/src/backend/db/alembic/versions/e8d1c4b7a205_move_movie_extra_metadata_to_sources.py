"""Move globally intrinsic movie-extra metadata onto shared sources.

Revision ID: e8d1c4b7a205
Revises: f7c2a5d9e104
"""

from __future__ import annotations

import json

from alembic import op
import sqlalchemy as sa


revision = "e8d1c4b7a205"
down_revision = "f7c2a5d9e104"
branch_labels = None
depends_on = None


_SOURCE_FIELDS = (
    "title",
    "description",
    "duration",
    "background_image_path",
    "thumbnail_landscape_path",
    "thumbnail_portrait_path",
    "thumbnail_square_path",
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

    # media_items remains the polymorphic identity/download parent table, but its
    # clip-level metadata columns are no longer authoritative for MovieExtra.
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


def upgrade() -> None:
    bind = op.get_bind()

    # ADD COLUMN is intentionally used directly here. movie_extra_sources is
    # referenced by movie_extras, so an SQLite batch-table rebuild of this parent
    # table would violate the existing source_id foreign key.
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

    _backfill_source_metadata(bind)

    # Removing the old placement copies rebuilds movie_extras on SQLite. Preserve
    # the external movies.official_trailer_id relationship across that rebuild.
    official_trailer_links = _official_trailer_links(bind)
    with op.batch_alter_table("movie_extras") as batch:
        batch.drop_column("available_for")
        batch.drop_column("published_date")
        batch.drop_column("sharing_url")
    _restore_official_trailer_links(bind, official_trailer_links)


def downgrade() -> None:
    bind = op.get_bind()

    # Restore the previous parent-scoped copies before removing source metadata.
    # Direct ADD COLUMN avoids rebuilding movie_extras and disturbing trailer FKs.
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

    # Modern SQLite supports DROP COLUMN directly. Using it here is important:
    # batch-rebuilding movie_extra_sources would attempt to drop a parent table
    # that is still referenced by movie_extras.source_id.
    for column in reversed(_SOURCE_FIELDS):
        op.drop_column("movie_extra_sources", column)
