"""Add trailer download support

Revision ID: d2c4a7318b90
Revises: a59b07916fb6
Create Date: 2026-08-30

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d2c4a7318b90"
down_revision: Union[str, None] = "a59b07916fb6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("local_media_profiles", schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            "append_media_type_to_filename",
            sa.Boolean(),
            server_default=sa.true(),
            nullable=False,
        ))

    op.create_table(
        "media_downloads_trailer",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["id"],
            ["media_downloads.id"],
            name=op.f("fk_media_downloads_trailer_id_media_downloads"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_media_downloads_trailer")),
    )


def downgrade() -> None:
    op.drop_table("media_downloads_trailer")
    with op.batch_alter_table("local_media_profiles", schema=None) as batch_op:
        batch_op.drop_column("append_media_type_to_filename")
