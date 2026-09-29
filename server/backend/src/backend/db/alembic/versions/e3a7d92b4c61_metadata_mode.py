"""Replace metadata flags with one Local Media Profile mode.

Revision ID: e3a7d92b4c61
Revises: b7e1c4a92d6f
"""
from alembic import op
import sqlalchemy as sa


revision = "e3a7d92b4c61"
down_revision = "b7e1c4a92d6f"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("local_media_profiles") as batch:
        batch.add_column(
            sa.Column(
                "metadata_mode",
                sa.String(length=24),
                nullable=False,
                server_default="system",
            )
        )

    profiles = sa.table(
        "local_media_profiles",
        sa.column("embed_metadata", sa.Boolean()),
        sa.column("download_nfo", sa.Boolean()),
        sa.column("metadata_mode", sa.String(length=24)),
    )
    # The previous metadata flags were introduced only by the in-development
    # version of this feature. False/false therefore represents profiles that
    # never opted into a metadata behavior; migrate those to System so they
    # inherit the new system default. Preserve every enabled combination.
    op.execute(
        profiles.update().values(
            metadata_mode=sa.case(
                (
                    sa.and_(
                        profiles.c.embed_metadata.is_(True),
                        profiles.c.download_nfo.is_(True),
                    ),
                    "embed_and_nfo",
                ),
                (profiles.c.embed_metadata.is_(True), "embed"),
                (profiles.c.download_nfo.is_(True), "nfo"),
                else_="system",
            )
        )
    )

    with op.batch_alter_table("local_media_profiles") as batch:
        batch.drop_column("download_nfo")
        batch.drop_column("embed_metadata")


def downgrade():
    with op.batch_alter_table("local_media_profiles") as batch:
        batch.add_column(
            sa.Column(
                "embed_metadata",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )
        batch.add_column(
            sa.Column(
                "download_nfo",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )

    profiles = sa.table(
        "local_media_profiles",
        sa.column("embed_metadata", sa.Boolean()),
        sa.column("download_nfo", sa.Boolean()),
        sa.column("metadata_mode", sa.String(length=24)),
    )
    op.execute(
        profiles.update().values(
            embed_metadata=profiles.c.metadata_mode.in_(("embed", "embed_and_nfo")),
            download_nfo=profiles.c.metadata_mode.in_(("nfo", "embed_and_nfo")),
        )
    )

    with op.batch_alter_table("local_media_profiles") as batch:
        batch.drop_column("metadata_mode")
