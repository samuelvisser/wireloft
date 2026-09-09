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


def _rename_series_profile_fk_column(old_name: str, new_name: str) -> None:
    with op.batch_alter_table("download_profile_series_seasons") as batch_op:
        batch_op.alter_column(
            old_name,
            new_column_name=new_name,
            existing_type=sa.Integer(),
            existing_nullable=True,
        )


def upgrade() -> None:
    bind = op.get_bind()

    # This column becomes Alembic's version store after the migration command
    # finishes. The running command keeps using the legacy alembic_version table
    # until backend.db.migrations performs the atomic handoff.
    op.add_column(
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
    op.drop_column("media_items", "downloaded_date")
    op.drop_column("media_items_episodes", "redownloaded_date")

    # Match the established joined-inheritance naming used by media_downloads:
    # one singular subtype suffix per concrete table.
    op.rename_table("media_items_episodes", "media_items_episode")
    op.rename_table("media_items_movie_extras", "media_items_movie_extra")
    op.rename_table("media_items_movies", "media_items_movie")

    # HasMetadataMixin uses the physical table name as its discriminator.
    bind.execute(sa.text(
        "UPDATE metadata SET parent_table = 'media_items_episode' "
        "WHERE parent_table = 'media_items_episodes'"
    ))


def downgrade() -> None:
    bind = op.get_bind()

    # The WireLoft database CLI creates the legacy version table before crossing
    # this boundary. Refuse a direct raw-Alembic downgrade that would otherwise
    # delete the column Alembic is still using to track this very migration.
    if "alembic_version" not in sa.inspect(bind).get_table_names():
        raise RuntimeError(
            "Downgrading past d8f3a1c6b205 must use 'backend-api db downgrade' "
            "so Alembic version tracking can move out of settings first."
        )

    bind.execute(sa.text(
        "UPDATE metadata SET parent_table = 'media_items_episodes' "
        "WHERE parent_table = 'media_items_episode'"
    ))

    op.rename_table("media_items_movie_extra", "media_items_movie_extras")
    op.rename_table("media_items_movie", "media_items_movies")
    op.rename_table("media_items_episode", "media_items_episodes")

    # The removed aggregate timestamps cannot be reconstructed unambiguously
    # when multiple MediaDownloads exist, so downgrade restores nullable columns.
    op.add_column(
        "media_items_episodes",
        sa.Column("redownloaded_date", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "media_items",
        sa.Column("downloaded_date", sa.DateTime(), nullable=True),
    )

    _rename_series_profile_fk_column(
        "download_profiles_series_id",
        "series_download_profile_id",
    )
    op.drop_column("settings", "alembic_version_num")
