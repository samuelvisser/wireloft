"""Upgrade the shipped WireLoft 1.0 schema to WireLoft 1.1.

Revision ID: b1d7c3e9f205
Revises: c8d4e2f1a7b9
Create Date: 2026-09-14

This is the only durable Alembic boundary between the public 1.0 and 1.1
releases. The implementation modules under ``wireloft_1_1_steps`` preserve the
already-reviewed data transforms from development, but they are not Alembic
revisions and are executed only through this revision.
"""
from __future__ import annotations

from alembic import op
from alembic.runtime.migration import MigrationContext
import sqlalchemy as sa

from backend.db.alembic_version import (
    SETTINGS_VERSION_COLUMN,
    SETTINGS_VERSION_TABLE,
    apply_settings_version_table,
)
from backend.db.alembic.wireloft_1_1_steps import (
    a4d7c2e9f610_canonicalize_episode_lifecycle_metadata as episode_metadata,
    a7c5d9e2f401_prioritize_queued_downloads as queued_download_priority,
    a9c4e7b2d610_canonicalize_rss_video_methods as rss_video_methods,
    b7e2c4d9a601_drop_media_download_attempts as download_attempts,
    c1f7b9e4d205_artifact_identity as artifact_identity,
    d4f0a9c2e713_task_operations as task_operations,
    d8b4a1f6c203_podcast_download_starting_from as podcast_starting_from,
    e1c7a4b9d302_finalize_media_database_refactor as media_database_refactor,
    e3a1b5c7d902_show_local_media_profile_scope as show_profile_scope,
    e3a8f4c9b102_datetime_contract as datetime_contract,
    e6a9c1f4b203_episode_release_lifecycle as episode_lifecycle,
    f2c7a4e8b901_unify_download_execution as download_execution,
    f4d2a7b9c301_scope_season_slugs_to_show as season_slug_scope,
)


revision = "b1d7c3e9f205"
down_revision = "c8d4e2f1a7b9"
branch_labels = None
depends_on = None


def configure_version_storage_for_upgrade(context: MigrationContext) -> None:
    """Delegate legacy/current version-table detection to the 1.1 refactor step."""
    media_database_refactor.configure_version_storage_for_upgrade(context)


def _handoff_version_storage(bind) -> None:
    """Move the live Alembic context from 1.0's table into Settings.

    The media database refactor introduced Settings-backed Alembic version
    storage during 1.1 development. In the consolidated release migration the
    handoff happens directly from the shipped 1.0 revision instead of from an
    intermediate development revision.
    """
    inspector = sa.inspect(bind)
    if not inspector.has_table(media_database_refactor._LEGACY_VERSION_TABLE):
        apply_settings_version_table(op.get_context())
        return

    revisions = media_database_refactor._legacy_revisions(bind)
    if len(revisions) != 1:
        raise RuntimeError(
            "Cannot move Alembic version tracking into settings unless the database "
            f"has exactly one current revision; found {revisions}."
        )

    current_revision = revisions[0]
    if current_revision != down_revision:
        raise RuntimeError(
            "The WireLoft 1.1 version-storage handoff can only run while upgrading "
            f"from {down_revision}; found {current_revision}."
        )

    settings_rows = media_database_refactor._settings_version_rows(bind)
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

    # Alembic records c8 -> b1 after upgrade() returns. Switch the live context
    # first so that update is written directly to Settings.
    media_database_refactor._legacy_version_table().drop(bind)
    apply_settings_version_table(op.get_context())


def _upgrade_media_database_refactor() -> None:
    bind = op.get_bind()
    media_database_refactor._add_movie_page_metadata()
    media_database_refactor._scope_movie_extra_identity()
    media_database_refactor._drop_dailywire_ids(bind)
    media_database_refactor._normalize_movie_extra_sources(bind)
    media_database_refactor._move_movie_extra_metadata_to_sources(bind)
    media_database_refactor._move_content_metadata_to_owners(bind)
    media_database_refactor._remove_promotional_movie_metadata()
    media_database_refactor._rename_media_item_tables(bind)
    media_database_refactor._finalize_media_item_schema(bind)
    media_database_refactor._repair_movie_extra_classifications(bind)
    _handoff_version_storage(bind)


def _upgrade_download_mode() -> None:
    with op.batch_alter_table("local_media_profiles") as batch:
        batch.add_column(
            sa.Column(
                "download_mode",
                sa.String(length=16),
                nullable=False,
                server_default="system",
            )
        )


def _downgrade_download_mode() -> None:
    with op.batch_alter_table("local_media_profiles") as batch:
        batch.drop_column("download_mode")


def upgrade() -> None:
    """Upgrade a shipped WireLoft 1.0 database directly to WireLoft 1.1."""
    task_operations.upgrade()
    download_execution.upgrade()

    # WireLoft 1.1 deliberately replaces the dedicated 1.0 attempt ledger with
    # TaskRun/TaskOperation history. Existing attempt rows are not migrated.
    download_attempts.upgrade()

    datetime_contract.upgrade()
    episode_lifecycle.upgrade()
    episode_metadata.upgrade()
    show_profile_scope.upgrade()
    artifact_identity.upgrade()
    _upgrade_media_database_refactor()
    season_slug_scope.upgrade()

    # download_mode changes execution behavior, not Local Media Profile identity.
    # Keep only the existing stricter uniqueness constraint on
    # (type, output_template, preferred_format); no redundant mode-aware index.
    _upgrade_download_mode()

    queued_download_priority.upgrade()
    rss_video_methods.upgrade()
    podcast_starting_from.upgrade()


def downgrade() -> None:
    """Return the 1.1 application schema to the shipped WireLoft 1.0 schema."""
    podcast_starting_from.downgrade()
    rss_video_methods.downgrade()
    queued_download_priority.downgrade()
    _downgrade_download_mode()
    season_slug_scope.downgrade()
    media_database_refactor.downgrade()
    artifact_identity.downgrade()
    show_profile_scope.downgrade()
    episode_metadata.downgrade()
    episode_lifecycle.downgrade()
    datetime_contract.downgrade()

    # The 1.0 ledger table is recreated empty. Its historical rows were
    # intentionally discarded by the 1.1 upgrade.
    download_attempts.downgrade()
    download_execution.downgrade()
    task_operations.downgrade()

    # Version tracking intentionally remains in Settings after the one-time
    # handoff, matching current WireLoft's migration-runner contract.
