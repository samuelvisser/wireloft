"""Add persistent custom indexing and successful download history.

Revision ID: b7e3c1a94d20
Revises: 3f7b6a2c9d10
"""

from alembic import op
import sqlalchemy as sa


revision = "b7e3c1a94d20"
down_revision = "3f7b6a2c9d10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("media_downloads") as batch_op:
        batch_op.add_column(
            sa.Column(
                "first_successful_download_at",
                sa.DateTime(timezone=True),
                nullable=True,
            )
        )

    op.execute(
        sa.text(
            "UPDATE media_downloads "
            "SET first_successful_download_at = downloaded_at "
            "WHERE downloaded_at IS NOT NULL"
        )
    )
    op.execute(sa.text("""
        UPDATE media_downloads
        SET first_successful_download_at = (
            SELECT MIN(COALESCE(task_runs.finished_at, task_runs.created_at))
            FROM task_runs
            JOIN task_definitions
              ON task_definitions.id = task_runs.definition_id
            WHERE task_runs.resource_id = media_downloads.id
              AND task_runs.resource_type IN ('MEDIA_DOWNLOAD', 'media_download')
              AND task_runs.status IN ('SUCCEEDED', 'succeeded')
              AND task_definitions.key IN ('download_episode', 'download_movie')
        )
        WHERE first_successful_download_at IS NULL
          AND EXISTS (
            SELECT 1
            FROM task_runs
            JOIN task_definitions
              ON task_definitions.id = task_runs.definition_id
            WHERE task_runs.resource_id = media_downloads.id
              AND task_runs.resource_type IN ('MEDIA_DOWNLOAD', 'media_download')
              AND task_runs.status IN ('SUCCEEDED', 'succeeded')
              AND task_definitions.key IN ('download_episode', 'download_movie')
          )
    """))

    op.execute(sa.text(
        "UPDATE media_downloads "
        "SET first_successful_download_at = COALESCE(downloaded_at, updated_at, created_at, CURRENT_TIMESTAMP) "
        "WHERE first_successful_download_at IS NULL "
        "AND artifact_status = 'available'"
    ))

    op.create_table(
        "custom_index_states",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("show_id", sa.Integer(), nullable=False),
        sa.Column("local_media_profile_id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("next_value", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["show_id"], ["shows.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["local_media_profile_id"],
            ["local_media_profiles.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "show_id",
            "local_media_profile_id",
            "key",
            name="uq_custom_index_state_scope_key",
        ),
    )
    op.create_index(
        "ix_custom_index_states_show_id",
        "custom_index_states",
        ["show_id"],
        unique=False,
    )
    op.create_index(
        "ix_custom_index_states_local_media_profile_id",
        "custom_index_states",
        ["local_media_profile_id"],
        unique=False,
    )


def downgrade() -> None:
    op.execute(sa.text(
        "DELETE FROM metadata "
        "WHERE key LIKE 'custom\\_index.%' ESCAPE '\\'"
    ))
    op.drop_index(
        "ix_custom_index_states_local_media_profile_id",
        table_name="custom_index_states",
    )
    op.drop_index(
        "ix_custom_index_states_show_id",
        table_name="custom_index_states",
    )
    op.drop_table("custom_index_states")

    with op.batch_alter_table("media_downloads") as batch_op:
        batch_op.drop_column("first_successful_download_at")
