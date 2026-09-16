"""Add durable media download lifecycle events.

Revision ID: 6b91c0f4d2aa
Revises: f2c6a9d41e7b
"""

from alembic import op
import sqlalchemy as sa


revision = "6b91c0f4d2aa"
down_revision = "f2c6a9d41e7b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "media_download_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("media_download_id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=24), nullable=False),
        sa.Column("file_path", sa.String(), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["media_download_id"],
            ["media_downloads.id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_media_download_events_media_download_id",
        "media_download_events",
        ["media_download_id"],
    )
    op.create_index(
        "ix_media_download_events_event_type",
        "media_download_events",
        ["event_type"],
    )
    op.create_index(
        "ix_media_download_events_occurred_at",
        "media_download_events",
        ["occurred_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_media_download_events_occurred_at", table_name="media_download_events")
    op.drop_index("ix_media_download_events_event_type", table_name="media_download_events")
    op.drop_index("ix_media_download_events_media_download_id", table_name="media_download_events")
    op.drop_table("media_download_events")
