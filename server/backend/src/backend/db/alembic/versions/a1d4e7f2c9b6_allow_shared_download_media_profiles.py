"""Allow Download Profiles to share a Local Media Profile.

Revision ID: a1d4e7f2c9b6
Revises: e5b7c9d1f3a2
Create Date: 2026-09-01

"""
from typing import Sequence, Union

from alembic import op


revision: str = "a1d4e7f2c9b6"
down_revision: Union[str, None] = "e5b7c9d1f3a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("download_profiles", schema=None) as batch_op:
        batch_op.drop_constraint("uq_unique_media_profile_per_show", type_="unique")


def downgrade() -> None:
    with op.batch_alter_table("download_profiles", schema=None) as batch_op:
        batch_op.create_unique_constraint(
            "uq_unique_media_profile_per_show",
            ["show_id", "local_media_profile_id"],
        )
