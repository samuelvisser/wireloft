"""Add durable opt-in Web Push subscriptions and notification delivery records.

Revision ID: e35bd80af19c
Revises: a4e7c19b2d53
"""
from alembic import op
import sqlalchemy as sa

revision = "e35bd80af19c"
down_revision = "a4e7c19b2d53"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "push_vapid_keys",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("encrypted_private_key", sa.Text(), nullable=False),
    )
    op.create_table(
        "push_subscriptions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("endpoint_hash", sa.String(length=64), nullable=False),
        sa.Column("encrypted_subscription", sa.Text(), nullable=False),
        sa.Column("categories", sa.JSON(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("enabled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("endpoint_hash", name="uq_push_subscriptions_endpoint_hash"),
    )
    op.create_table(
        "push_deliveries",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("operation_id", sa.String(length=36), sa.ForeignKey("task_operations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("subscription_id", sa.Integer(), sa.ForeignKey("push_subscriptions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("operation_finished_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("operation_id", "subscription_id", "operation_finished_at", name="uq_push_delivery_operation_device"),
    )
    op.create_index("ix_push_delivery_pending", "push_deliveries", ["status", "next_attempt_at"])
    op.add_column("task_operations", sa.Column("push_notified_at", sa.DateTime(timezone=True)))


def downgrade() -> None:
    op.drop_column("task_operations", "push_notified_at")
    op.drop_index("ix_push_delivery_pending", table_name="push_deliveries")
    op.drop_table("push_deliveries")
    op.drop_table("push_subscriptions")
    op.drop_table("push_vapid_keys")
