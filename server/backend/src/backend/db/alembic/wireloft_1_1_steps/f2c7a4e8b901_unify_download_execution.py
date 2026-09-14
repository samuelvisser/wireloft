"""Move download execution state into TaskRun/TaskOperation.

Revision ID: f2c7a4e8b901
Revises: d4f0a9c2e713
"""

from alembic import op
import sqlalchemy as sa


revision = "f2c7a4e8b901"
down_revision = "d4f0a9c2e713"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("media_downloads") as batch:
        batch.add_column(sa.Column("artifact_status", sa.String(length=24), nullable=False, server_default="absent"))
        batch.add_column(sa.Column("artifact_error", sa.Text(), nullable=True))
        batch.add_column(sa.Column("automatic_retry_suppressed", sa.Boolean(), nullable=False, server_default=sa.text("0")))
        batch.add_column(sa.Column("downloaded_at", sa.DateTime(timezone=True), nullable=True))
        batch.create_index("ix_media_downloads_artifact_status", ["artifact_status"], unique=False)

    op.execute(
        sa.text(
            """
            UPDATE media_downloads
            SET artifact_status = CASE
                    WHEN download_status IN ('downloaded', 'redownloaded') THEN 'available'
                    WHEN download_status = 'missing' THEN 'missing'
                    WHEN download_status = 'corrupted' THEN 'corrupted'
                    ELSE 'absent'
                END,
                artifact_error = CASE
                    WHEN download_status IN ('missing', 'corrupted') THEN error_message
                    ELSE NULL
                END,
                automatic_retry_suppressed = CASE
                    WHEN download_status = 'cancelled' THEN 1
                    ELSE 0
                END,
                downloaded_at = CASE
                    WHEN download_status IN ('downloaded', 'redownloaded') THEN finished_at
                    ELSE NULL
                END
            """
        )
    )

    with op.batch_alter_table("media_downloads") as batch:
        batch.drop_column("download_status")
        batch.drop_column("progress")
        batch.drop_column("error_message")
        batch.drop_column("started_at")
        batch.drop_column("finished_at")
        batch.drop_column("attempt_generation")

    with op.batch_alter_table("media_downloads_episode") as batch:
        batch.drop_column("is_redownload_attempt")


def downgrade() -> None:
    with op.batch_alter_table("media_downloads") as batch:
        batch.add_column(sa.Column("download_status", sa.String(), nullable=True))
        batch.add_column(sa.Column("progress", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("error_message", sa.String(), nullable=True))
        batch.add_column(sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("attempt_generation", sa.Integer(), nullable=False, server_default="0"))

    op.execute(
        sa.text(
            """
            UPDATE media_downloads
            SET download_status = CASE
                    WHEN artifact_status = 'available' THEN 'downloaded'
                    WHEN artifact_status = 'missing' THEN 'missing'
                    WHEN artifact_status = 'corrupted' THEN 'corrupted'
                    WHEN automatic_retry_suppressed = 1 THEN 'cancelled'
                    ELSE 'error'
                END,
                progress = CASE WHEN artifact_status = 'available' THEN 100 ELSE 0 END,
                error_message = artifact_error,
                finished_at = downloaded_at,
                attempt_generation = 0
            """
        )
    )

    with op.batch_alter_table("media_downloads_episode") as batch:
        batch.add_column(sa.Column("is_redownload_attempt", sa.Boolean(), nullable=True))

    with op.batch_alter_table("media_downloads") as batch:
        batch.drop_index("ix_media_downloads_artifact_status")
        batch.drop_column("artifact_status")
        batch.drop_column("artifact_error")
        batch.drop_column("automatic_retry_suppressed")
        batch.drop_column("downloaded_at")
