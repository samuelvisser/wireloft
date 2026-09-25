"""Replace download-time index allocation with Episode reconciliation generations.

Revision ID: c80e4d9a6b21
Revises: b7e3c1a94d20
"""

from alembic import op
import sqlalchemy as sa


revision = "c80e4d9a6b21"
down_revision = "b7e3c1a94d20"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The old definitions belonged to Shows and the old assignments to
    # MediaDownloads. Neither can be interpreted as the new LMP-owned rules.
    op.execute(sa.text("""
        DELETE FROM metadata WHERE key LIKE 'custom\\_index.%' ESCAPE '\\'
    """))
    op.drop_index("ix_custom_index_states_local_media_profile_id", table_name="custom_index_states")
    op.drop_index("ix_custom_index_states_show_id", table_name="custom_index_states")
    op.drop_table("custom_index_states")
    op.create_table(
        "custom_index_states",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("show_id", sa.Integer(), sa.ForeignKey("shows.id", ondelete="CASCADE"), nullable=False),
        sa.Column("local_media_profile_id", sa.Integer(), sa.ForeignKey("local_media_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("requested_generation", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("completed_generation", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("show_id", "local_media_profile_id", name="uq_custom_index_state_scope"),
    )
    op.create_index("ix_custom_index_states_show_id", "custom_index_states", ["show_id"])
    op.create_index("ix_custom_index_states_local_media_profile_id", "custom_index_states", ["local_media_profile_id"])


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM metadata WHERE key LIKE 'custom\\_index.%' ESCAPE '\\'"))
    op.drop_index("ix_custom_index_states_local_media_profile_id", table_name="custom_index_states")
    op.drop_index("ix_custom_index_states_show_id", table_name="custom_index_states")
    op.drop_table("custom_index_states")
    op.create_table(
        "custom_index_states",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("show_id", sa.Integer(), sa.ForeignKey("shows.id", ondelete="CASCADE"), nullable=False),
        sa.Column("local_media_profile_id", sa.Integer(), sa.ForeignKey("local_media_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("next_value", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("show_id", "local_media_profile_id", "key", name="uq_custom_index_state_scope_key"),
    )
    op.create_index("ix_custom_index_states_show_id", "custom_index_states", ["show_id"])
    op.create_index("ix_custom_index_states_local_media_profile_id", "custom_index_states", ["local_media_profile_id"])
