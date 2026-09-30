"""Store download auxiliary files and generic operation dependencies.

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


def _upgrade_operation_dependencies() -> None:
    op.add_column(
        "task_operations",
        sa.Column(
            "completion_progress",
            sa.Integer(),
            nullable=True,
            server_default=sa.text("0"),
        ),
    )
    op.execute(sa.text("""
        UPDATE task_operations
        SET completion_progress = CASE
            WHEN status IN ('SUCCEEDED', 'FAILED', 'PARTIAL', 'CANCELED') THEN 100
            ELSE COALESCE(progress, 0)
        END
    """))

    op.create_table(
        "task_operation_dependencies",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "parent_operation_id",
            sa.String(length=36),
            sa.ForeignKey("task_operations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "child_operation_id",
            sa.String(length=36),
            sa.ForeignKey("task_operations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("slot_key", sa.String(length=255), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False, server_default=sa.text("1")),
        sa.Column("required", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("cancel_policy", sa.String(length=32), nullable=False, server_default="detach"),
        sa.Column("context", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint(
            "parent_operation_id",
            "slot_key",
            name="uq_task_operation_dependencies_parent_slot",
        ),
        sa.UniqueConstraint(
            "parent_operation_id",
            "child_operation_id",
            name="uq_task_operation_dependencies_parent_child",
        ),
    )
    op.create_index(
        "ix_task_operation_dependencies_parent_operation_id",
        "task_operation_dependencies",
        ["parent_operation_id"],
    )
    op.create_index(
        "ix_task_operation_dependencies_child_operation_id",
        "task_operation_dependencies",
        ["child_operation_id"],
    )


def upgrade():
    _upgrade_operation_dependencies()

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
    with op.batch_alter_table("media_downloads") as batch:
        batch.add_column(sa.Column("thumbnail_path", sa.String(), nullable=True))
        batch.add_column(sa.Column("nfo_path", sa.String(), nullable=True))
    op.execute(sa.text("UPDATE media_downloads SET thumbnail_path = (SELECT path FROM media_download_assets WHERE media_download_id = media_downloads.id AND asset_key = 'artwork'), nfo_path = (SELECT path FROM media_download_assets WHERE media_download_id = media_downloads.id AND asset_key = 'nfo')"))
    op.drop_table("media_download_assets")

    op.drop_index(
        "ix_task_operation_dependencies_child_operation_id",
        table_name="task_operation_dependencies",
    )
    op.drop_index(
        "ix_task_operation_dependencies_parent_operation_id",
        table_name="task_operation_dependencies",
    )
    op.drop_table("task_operation_dependencies")
    with op.batch_alter_table("task_operations") as batch:
        batch.drop_column("completion_progress")
