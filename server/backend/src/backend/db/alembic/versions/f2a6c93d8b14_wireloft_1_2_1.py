"""Upgrade the shipped WireLoft 1.2 schema to WireLoft 1.2.1.

Revision ID: f2a6c93d8b14
Revises: 6d4a8c1f2b90
Create Date: 2026-10-01

This is the single release migration from the schema shipped in WireLoft 1.2
to WireLoft 1.2.1. Schema and local-data changes developed for 1.2.1 are
consolidated here so transient prerelease revisions do not become part of the
permanent migration history.
"""
from __future__ import annotations

from pathlib import PurePath

from alembic import op
import sqlalchemy as sa


revision = "f2a6c93d8b14"
down_revision = "6d4a8c1f2b90"
branch_labels = None
depends_on = None


# Show artwork --------------------------------------------------------------


def _upgrade_show_assets() -> None:
    op.add_column(
        "local_media_profiles_show",
        sa.Column("download_show_assets", sa.Boolean(), nullable=True),
    )

    # Profiles created before this setting existed should not suddenly start
    # publishing artwork after an upgrade. New profiles remain NULL and inherit
    # the enabled system default.
    show_profiles = sa.table(
        "local_media_profiles_show",
        sa.column("download_show_assets", sa.Boolean()),
    )
    op.execute(show_profiles.update().values(download_show_assets=False))

    op.create_table(
        "show_local_assets",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "show_id",
            sa.Integer(),
            sa.ForeignKey("shows.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "local_media_profile_id",
            sa.Integer(),
            sa.ForeignKey("local_media_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("asset_type", sa.String(16), nullable=False),
        sa.Column("file_path", sa.String(), nullable=False),
        sa.Column("source_url", sa.String(), nullable=True),
        sa.Column("source_format", sa.String(16), nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=True),
        sa.Column("pending_hash", sa.String(64), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "show_id",
            "local_media_profile_id",
            "asset_type",
            "file_path",
            name="uq_show_local_asset_target",
        ),
    )
    op.create_index(
        "ix_show_local_assets_show_id",
        "show_local_assets",
        ["show_id"],
    )
    op.create_index(
        "ix_show_local_assets_local_media_profile_id",
        "show_local_assets",
        ["local_media_profile_id"],
    )


def _downgrade_show_assets() -> None:
    # Filesystem work deliberately belongs to the runtime reconciler, not Alembic.
    op.drop_table("show_local_assets")
    with op.batch_alter_table("local_media_profiles_show") as batch:
        batch.drop_column("download_show_assets")


# Media metadata ------------------------------------------------------------


def _upgrade_metadata_mode() -> None:
    # The prerelease-only embed_metadata/download_nfo flags are intentionally
    # skipped. A shipped 1.2 profile had no metadata preference, so it should
    # directly inherit the 1.2.1 system default.
    with op.batch_alter_table("local_media_profiles") as batch:
        batch.add_column(
            sa.Column(
                "metadata_mode",
                sa.String(length=24),
                nullable=False,
                server_default="system",
            )
        )


def _downgrade_metadata_mode() -> None:
    with op.batch_alter_table("local_media_profiles") as batch:
        batch.drop_column("metadata_mode")


# Task operation dependencies ----------------------------------------------


def _upgrade_operation_dependencies() -> None:
    op.add_column(
        "task_operations",
        sa.Column(
            "completion_progress",
            sa.Integer(),
            nullable=True,
            server_default=sa.text("0"),
        ),
    )
    op.execute(sa.text("""
        UPDATE task_operations
        SET completion_progress = CASE
            WHEN status IN ('SUCCEEDED', 'FAILED', 'PARTIAL', 'CANCELED') THEN 100
            ELSE COALESCE(progress, 0)
        END
    """))

    op.create_table(
        "task_operation_dependencies",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "parent_operation_id",
            sa.String(length=36),
            sa.ForeignKey("task_operations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "child_operation_id",
            sa.String(length=36),
            sa.ForeignKey("task_operations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("slot_key", sa.String(length=255), nullable=False),
        sa.Column(
            "weight",
            sa.Float(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column(
            "required",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "cancel_policy",
            sa.String(length=32),
            nullable=False,
            server_default="detach",
        ),
        sa.Column("context", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint(
            "parent_operation_id",
            "slot_key",
            name="uq_task_operation_dependencies_parent_slot",
        ),
        sa.UniqueConstraint(
            "parent_operation_id",
            "child_operation_id",
            name="uq_task_operation_dependencies_parent_child",
        ),
    )
    op.create_index(
        "ix_task_operation_dependencies_parent_operation_id",
        "task_operation_dependencies",
        ["parent_operation_id"],
    )
    op.create_index(
        "ix_task_operation_dependencies_child_operation_id",
        "task_operation_dependencies",
        ["child_operation_id"],
    )


def _downgrade_operation_dependencies() -> None:
    op.drop_index(
        "ix_task_operation_dependencies_child_operation_id",
        table_name="task_operation_dependencies",
    )
    op.drop_index(
        "ix_task_operation_dependencies_parent_operation_id",
        table_name="task_operation_dependencies",
    )
    op.drop_table("task_operation_dependencies")
    with op.batch_alter_table("task_operations") as batch:
        batch.drop_column("completion_progress")


# Download auxiliary assets -------------------------------------------------


def _upgrade_download_assets() -> None:
    assets = op.create_table(
        "media_download_assets",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "media_download_id",
            sa.Integer(),
            sa.ForeignKey("media_downloads.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("asset_key", sa.String(120), nullable=False),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("path", sa.String(), nullable=False),
        sa.Column("suffix", sa.String(120), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("fingerprint", sa.String(64), nullable=True),
        sa.UniqueConstraint(
            "media_download_id",
            "asset_key",
            name="uq_download_asset_key",
        ),
    )
    op.create_index(
        "ix_media_download_assets_media_download_id",
        "media_download_assets",
        ["media_download_id"],
    )

    connection = op.get_bind()
    # WireLoft 1.2 stores only the managed thumbnail path directly on the
    # download. Move it into the generic asset table without touching the
    # filesystem; identity is filled in on a later successful publication.
    rows = connection.execute(
        sa.text("SELECT id, thumbnail_path FROM media_downloads")
    ).mappings()
    for row in rows:
        path = row["thumbnail_path"]
        if not path:
            continue
        connection.execute(
            assets.insert().values(
                media_download_id=row["id"],
                asset_key="artwork",
                kind="thumbnail",
                path=path,
                suffix=PurePath(path).suffix or ".jpg",
            )
        )

    with op.batch_alter_table("media_downloads") as batch:
        batch.drop_column("thumbnail_path")


def _downgrade_download_assets() -> None:
    with op.batch_alter_table("media_downloads") as batch:
        batch.add_column(sa.Column("thumbnail_path", sa.String(), nullable=True))

    # WireLoft 1.2 has no generic sidecar/NFO representation. Restore the
    # artwork path it understands; 1.2.1-only auxiliary assets are discarded.
    op.execute(sa.text("""
        UPDATE media_downloads
        SET thumbnail_path = (
            SELECT path
            FROM media_download_assets
            WHERE media_download_id = media_downloads.id
              AND asset_key = 'artwork'
        )
    """))
    op.drop_table("media_download_assets")


# Query indexes -------------------------------------------------------------


def _upgrade_query_indexes() -> None:
    op.create_index(
        "ix_media_items_episode_show_published_id",
        "media_items_episode",
        ["show_id", "published_date", "id"],
        unique=False,
    )
    op.create_index(
        "ix_task_runs_definition_status_resource_started_id",
        "task_runs",
        [
            "definition_id",
            "status",
            "resource_type",
            "resource_id",
            "started_at",
            "id",
        ],
        unique=False,
    )
    op.create_index(
        "ix_media_items_episode_show_publish_status",
        "media_items_episode",
        ["show_id", "publish_status"],
        unique=False,
    )
    op.create_index(
        "ix_media_items_episode_season_index_id",
        "media_items_episode",
        ["season_id", "index", "id"],
        unique=False,
    )
    op.create_index(
        "ix_media_items_episode_unfinished_metadata_status",
        "media_items_episode",
        ["publish_status"],
        unique=False,
        sqlite_where=sa.text("metadata_is_final = 0"),
    )
    op.create_index(
        "ix_media_download_history_download_occurred_id",
        "media_download_history",
        ["media_download_id", "occurred_at", "id"],
        unique=False,
    )
    op.create_index(
        "ix_media_downloads_local_profile_id",
        "media_downloads",
        ["local_media_profile_id", "id"],
        unique=False,
    )

    if op.get_bind().dialect.name == "sqlite":
        # Let SQLite decide whether planner statistics need refreshing.
        op.execute(sa.text("PRAGMA optimize"))


def _downgrade_query_indexes() -> None:
    op.drop_index(
        "ix_media_downloads_local_profile_id",
        table_name="media_downloads",
    )
    op.drop_index(
        "ix_media_download_history_download_occurred_id",
        table_name="media_download_history",
    )
    op.drop_index(
        "ix_media_items_episode_unfinished_metadata_status",
        table_name="media_items_episode",
    )
    op.drop_index(
        "ix_media_items_episode_season_index_id",
        table_name="media_items_episode",
    )
    op.drop_index(
        "ix_media_items_episode_show_publish_status",
        table_name="media_items_episode",
    )
    op.drop_index(
        "ix_task_runs_definition_status_resource_started_id",
        table_name="task_runs",
    )
    op.drop_index(
        "ix_media_items_episode_show_published_id",
        table_name="media_items_episode",
    )


# Release migration ---------------------------------------------------------


def upgrade() -> None:
    """Upgrade a shipped WireLoft 1.2 database directly to WireLoft 1.2.1."""
    _upgrade_show_assets()
    _upgrade_metadata_mode()
    _upgrade_operation_dependencies()
    _upgrade_download_assets()
    _upgrade_query_indexes()


def downgrade() -> None:
    """Return the WireLoft 1.2.1 schema to the shipped WireLoft 1.2 schema."""
    _downgrade_query_indexes()
    _downgrade_download_assets()
    _downgrade_operation_dependencies()
    _downgrade_metadata_mode()
    _downgrade_show_assets()
