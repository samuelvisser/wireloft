"""Track shared show artwork and per-profile enablement.

Revision ID: a9d73b8e5f21
Revises: 6d4a8c1f2b90
"""
from alembic import op
import sqlalchemy as sa

revision = "a9d73b8e5f21"
down_revision = "6d4a8c1f2b90"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("local_media_profiles_show", sa.Column("download_show_assets", sa.Boolean(), nullable=True))

    # Existing profiles predate this setting, so keep their upgrade behavior
    # opt-in. New profiles remain NULL and inherit the enabled system default.
    show_profiles = sa.table(
        "local_media_profiles_show",
        sa.column("download_show_assets", sa.Boolean()),
    )
    op.execute(show_profiles.update().values(download_show_assets=False))

    op.create_table(
        "show_local_assets",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("show_id", sa.Integer(), sa.ForeignKey("shows.id", ondelete="CASCADE"), nullable=False),
        sa.Column("local_media_profile_id", sa.Integer(), sa.ForeignKey("local_media_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("asset_type", sa.String(16), nullable=False),
        sa.Column("file_path", sa.String(), nullable=False),
        sa.Column("source_url", sa.String(), nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=True),
        sa.Column("pending_hash", sa.String(64), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("show_id", "local_media_profile_id", "asset_type", "file_path", name="uq_show_local_asset_target"),
    )
    op.create_index("ix_show_local_assets_show_id", "show_local_assets", ["show_id"])
    op.create_index("ix_show_local_assets_local_media_profile_id", "show_local_assets", ["local_media_profile_id"])


def downgrade():
    # Filesystem work deliberately belongs to the runtime reconciler, not Alembic.
    op.drop_table("show_local_assets")
    with op.batch_alter_table("local_media_profiles_show") as batch:
        batch.drop_column("download_show_assets")
