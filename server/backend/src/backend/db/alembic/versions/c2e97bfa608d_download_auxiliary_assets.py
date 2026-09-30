"""Store published auxiliary files independently of their media type.

Revision ID: c2e97bfa608d
Revises: e3a7d92b4c61
"""
from pathlib import PurePath

from alembic import op
import sqlalchemy as sa

revision = "c2e97bfa608d"
down_revision = "e3a7d92b4c61"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "download_batch_items",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("owner_key", sa.String(80), nullable=False),
        sa.Column("owner_run_id", sa.Integer(), sa.ForeignKey("task_runs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("owner_operation_id", sa.String(), sa.ForeignKey("task_operations.id", ondelete="CASCADE"), nullable=True),
        sa.Column("media_download_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("weight", sa.BigInteger(), nullable=False),
        sa.Column("child_operation_id", sa.String(), sa.ForeignKey("task_operations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("owns_operation", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("prepared", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.UniqueConstraint("owner_key", "media_download_id", name="uq_download_batch_target"),
    )
    op.create_index("ix_download_batch_items_owner_key", "download_batch_items", ["owner_key"])
    op.create_index("ix_download_batch_items_owner_run_id", "download_batch_items", ["owner_run_id"])
    op.create_index("ix_download_batch_items_owner_operation_id", "download_batch_items", ["owner_operation_id"])
    assets = op.create_table(
        "media_download_assets",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("media_download_id", sa.Integer(), sa.ForeignKey("media_downloads.id", ondelete="CASCADE"), nullable=False),
        sa.Column("asset_key", sa.String(120), nullable=False),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("path", sa.String(), nullable=False),
        sa.Column("suffix", sa.String(120), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("fingerprint", sa.String(64), nullable=True),
        sa.UniqueConstraint("media_download_id", "asset_key", name="uq_download_asset_key"),
    )
    op.create_index("ix_media_download_assets_media_download_id", "media_download_assets", ["media_download_id"])
    connection = op.get_bind()
    # Existing paths are migrated without inspecting the filesystem. Identity is
    # populated on the next successful publication, never by a schema migration.
    for row in connection.execute(sa.text("SELECT id, thumbnail_path, nfo_path FROM media_downloads")).mappings():
        for key, kind, path in (("artwork", "thumbnail", row["thumbnail_path"]), ("nfo", "nfo", row["nfo_path"])):
            if path:
                connection.execute(assets.insert().values(
                    media_download_id=row["id"], asset_key=key, kind=kind,
                    path=path, suffix=PurePath(path).suffix or (".nfo" if key == "nfo" else ".jpg"),
                ))
    with op.batch_alter_table("media_downloads") as batch:
        batch.drop_column("thumbnail_path")
        batch.drop_column("nfo_path")


def downgrade():
    op.drop_table("download_batch_items")
    with op.batch_alter_table("media_downloads") as batch:
        batch.add_column(sa.Column("thumbnail_path", sa.String(), nullable=True))
        batch.add_column(sa.Column("nfo_path", sa.String(), nullable=True))
    op.execute(sa.text("UPDATE media_downloads SET thumbnail_path = (SELECT path FROM media_download_assets WHERE media_download_id = media_downloads.id AND asset_key = 'artwork'), nfo_path = (SELECT path FROM media_download_assets WHERE media_download_id = media_downloads.id AND asset_key = 'nfo')"))
    op.drop_table("media_download_assets")
