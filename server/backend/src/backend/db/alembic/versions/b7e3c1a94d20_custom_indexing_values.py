"""Add persistent custom indexing.

Revision ID: b7e3c1a94d20
Revises: 3f7b6a2c9d10
"""

from alembic import op
import sqlalchemy as sa


revision = "b7e3c1a94d20"
down_revision = "3f7b6a2c9d10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "custom_index_states",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("show_id", sa.Integer(), nullable=False),
        sa.Column("local_media_profile_id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("next_value", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["show_id"], ["shows.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["local_media_profile_id"],
            ["local_media_profiles.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "show_id",
            "local_media_profile_id",
            "key",
            name="uq_custom_index_state_scope_key",
        ),
    )
    op.create_index(
        "ix_custom_index_states_show_id",
        "custom_index_states",
        ["show_id"],
        unique=False,
    )
    op.create_index(
        "ix_custom_index_states_local_media_profile_id",
        "custom_index_states",
        ["local_media_profile_id"],
        unique=False,
    )


def downgrade() -> None:
    op.execute(sa.text(
        "DELETE FROM metadata "
        "WHERE key LIKE 'custom\\_index.%' ESCAPE '\\'"
    ))
    op.drop_index(
        "ix_custom_index_states_local_media_profile_id",
        table_name="custom_index_states",
    )
    op.drop_index(
        "ix_custom_index_states_show_id",
        table_name="custom_index_states",
    )
    op.drop_table("custom_index_states")
