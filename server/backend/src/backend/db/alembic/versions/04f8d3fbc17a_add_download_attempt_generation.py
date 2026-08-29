"""Add download attempt generation

Revision ID: 04f8d3fbc17a
Revises: a59b07916fb6
Create Date: 2026-08-29 22:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '04f8d3fbc17a'
down_revision: Union[str, None] = 'a59b07916fb6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('media_downloads', schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            'attempt_generation',
            sa.Integer(),
            server_default='0',
            nullable=False,
        ))


def downgrade() -> None:
    with op.batch_alter_table('media_downloads', schema=None) as batch_op:
        batch_op.drop_column('attempt_generation')
