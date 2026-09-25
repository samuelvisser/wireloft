"""Move final-redownload intent from podcast profiles onto episode downloads.

Revision ID: 6d3a9f1c2b7e
Revises: 3f7b6a2c9d10
"""

from alembic import op
import sqlalchemy as sa


revision = "6d3a9f1c2b7e"
down_revision = "3f7b6a2c9d10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("media_downloads_episode") as batch_op:
        batch_op.add_column(
            sa.Column(
                "redownload_when_final",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )

    connection = op.get_bind()
    connection.execute(
        sa.text(
            "UPDATE media_downloads_episode "
            "SET redownload_when_final = :enabled "
            "WHERE downloaded_publish_status = :countdown_status "
            "AND download_profile_id IN ("
            "SELECT id FROM download_profiles_podcast WHERE redownload_final = :enabled"
            ")"
        ),
        {
            "enabled": True,
            "countdown_status": "published_with_countdown",
        },
    )


def downgrade() -> None:
    with op.batch_alter_table("media_downloads_episode") as batch_op:
        batch_op.drop_column("redownload_when_final")
