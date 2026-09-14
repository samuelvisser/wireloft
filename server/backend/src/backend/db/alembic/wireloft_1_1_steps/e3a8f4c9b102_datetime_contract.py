"""Use one WireLoft timezone for task schedules.

Revision ID: e3a8f4c9b102
Revises: b7e2c4d9a601
"""

from alembic import op
import sqlalchemy as sa


revision = "e3a8f4c9b102"
down_revision = "b7e2c4d9a601"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("task_schedules") as batch:
        batch.drop_column("timezone")


def downgrade() -> None:
    with op.batch_alter_table("task_schedules") as batch:
        batch.add_column(sa.Column("timezone", sa.String(), nullable=True))
