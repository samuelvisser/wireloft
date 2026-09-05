"""Drop the legacy MediaDownloadAttempt ledger.

Revision ID: b7e2c4d9a601
Revises: f2c7a4e8b901
"""

from alembic import op
import sqlalchemy as sa


revision = "b7e2c4d9a601"
down_revision = "f2c7a4e8b901"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("media_download_attempts")


def downgrade() -> None:
    op.create_table(
        "media_download_attempts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("media_download_id", sa.Integer(), nullable=False),
        sa.Column("is_redownload", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("error_message", sa.String(), nullable=True),
        sa.Column("downloaded_bytes", sa.Integer(), nullable=True),
        sa.Column("format_downloaded", sa.String(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["media_download_id"],
            ["media_downloads.id"],
            name=op.f("fk_media_download_attempts_media_download_id_media_downloads"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_media_download_attempts")),
    )
    op.create_index(
        op.f("ix_media_download_attempts_media_download_id"),
        "media_download_attempts",
        ["media_download_id"],
        unique=False,
    )
