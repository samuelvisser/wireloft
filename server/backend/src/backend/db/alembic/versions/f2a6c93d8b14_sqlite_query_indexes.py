"""Add high-value SQLite query indexes.

Revision ID: f2a6c93d8b14
Revises: c1f7a42d9e65
"""
from alembic import op
import sqlalchemy as sa


revision = "f2a6c93d8b14"
down_revision = "c1f7a42d9e65"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index(
        "ix_task_runs_definition_status_resource_started_id",
        "task_runs",
        ["definition_id", "status", "resource_type", "resource_id", "started_at", "id"],
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

    # Let SQLite update planner statistics after the schema changes. PRAGMA
    # optimize decides whether ANALYZE work is actually needed.
    op.execute(sa.text("PRAGMA optimize"))


def downgrade():
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
