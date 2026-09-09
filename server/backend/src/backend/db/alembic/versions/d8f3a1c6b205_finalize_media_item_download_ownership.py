"""Finalize media-item naming, download ownership, and database metadata.

Revision ID: d8f3a1c6b205
Revises: c5a9e2f7b104
"""

from alembic import op
import sqlalchemy as sa


revision = "d8f3a1c6b205"
down_revision = "c5a9e2f7b104"
branch_labels = None
depends_on = None


def _column_names(bind, table_name: str) -> set[str]:
    inspector = sa.inspect(bind)
    if not inspector.has_table(table_name):
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


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


def upgrade() -> None:
    bind = op.get_bind()

    # SQLite can leave DDL from an interrupted migration in place even when the
    # Alembic revision remains at c5. Every schema operation in this revision is
    # therefore restart-safe so `backend-api db upgrade` can resume the migration.
    _add_column_if_missing(
        bind,
        "settings",
        sa.Column("alembic_version_num", sa.String(length=32), nullable=True),
    )

    _rename_series_profile_fk_column(
        "series_download_profile_id",
        "download_profiles_series_id",
    )

    # Download timestamps belong to the concrete MediaDownload artifact. A media
    # item can have multiple downloads (one per Local Media Profile), so a single
    # item-level timestamp is ambiguous. Redownload attempts remain represented
    # by the canonical TaskRun history for each MediaDownload.
    _drop_column_if_present(bind, "media_items", "downloaded_date")
    _drop_column_if_present(bind, _episode_table_name(bind), "redownloaded_date")

    # Match the established joined-inheritance naming used by media_downloads:
    # one singular subtype suffix per concrete table.
    _rename_table_if_needed(bind, "media_items_episodes", "media_items_episode")
    _rename_table_if_needed(bind, "media_items_movie_extras", "media_items_movie_extra")
    _rename_table_if_needed(bind, "media_items_movies", "media_items_movie")

    # HasMetadataMixin uses the physical table name as its discriminator.
    bind.execute(sa.text(
        "UPDATE metadata SET parent_table = 'media_items_episode' "
        "WHERE parent_table = 'media_items_episodes'"
    ))


def downgrade() -> None:
    bind = op.get_bind()

    # The WireLoft database CLI materializes the legacy version table before
    # crossing this boundary. Refuse a direct raw-Alembic downgrade that would
    # otherwise delete the column used for persistent version tracking.
    if "alembic_version" not in sa.inspect(bind).get_table_names():
        raise RuntimeError(
            "Downgrading past d8f3a1c6b205 must use 'backend-api db downgrade' "
            "so Alembic version tracking can move out of settings first."
        )

    bind.execute(sa.text(
        "UPDATE metadata SET parent_table = 'media_items_episodes' "
        "WHERE parent_table = 'media_items_episode'"
    ))

    _rename_table_if_needed(bind, "media_items_movie_extra", "media_items_movie_extras")
    _rename_table_if_needed(bind, "media_items_movie", "media_items_movies")
    _rename_table_if_needed(bind, "media_items_episode", "media_items_episodes")

    # The removed aggregate timestamps cannot be reconstructed unambiguously
    # when multiple MediaDownloads exist, so downgrade restores nullable columns.
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
    _drop_column_if_present(bind, "settings", "alembic_version_num")
