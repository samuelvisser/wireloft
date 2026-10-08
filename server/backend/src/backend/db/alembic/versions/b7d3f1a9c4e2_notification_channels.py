"""Add Apprise notification channels, event routing and per-channel delivery records.

Web Push devices now pick from the same events as Apprise channels, so the four
legacy push categories are rewritten to the current events.

Revision ID: b7d3f1a9c4e2
Revises: e35bd80af19c
"""
import json

from alembic import op
import sqlalchemy as sa

revision = "b7d3f1a9c4e2"
down_revision = "e35bd80af19c"
branch_labels = None
depends_on = None

_CATEGORY_TO_EVENTS = {
    "downloads": ("download_completed",),
    "failures": ("download_failed", "task_failed"),
    "tasks": ("task_completed", "new_episodes"),
    "operations": ("operations",),
}
_EVENT_TO_CATEGORY = {
    event: category for category, events in _CATEGORY_TO_EVENTS.items() for event in events
}


def _rewrite_subscriptions(mapping: dict[str, tuple[str, ...]], column: str) -> None:
    connection = op.get_bind()
    table = sa.table("push_subscriptions", sa.column("id", sa.Integer), sa.column(column, sa.JSON))
    for row in connection.execute(sa.select(table.c.id, table.c[column])).all():
        stored = row[1]
        if isinstance(stored, str):
            stored = json.loads(stored)
        rewritten = sorted({new for old in stored for new in mapping.get(old, ())})
        connection.execute(
            sa.update(table).where(table.c.id == row[0]).values({column: rewritten})
        )


def upgrade() -> None:
    op.create_table(
        "notification_channels",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("service", sa.String(length=64), nullable=False),
        sa.Column("encrypted_url", sa.Text(), nullable=False),
        sa.Column("masked_url", sa.String(length=255), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("enabled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_status", sa.String(length=16)),
        sa.Column("last_error", sa.String(length=255)),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True)),
        sa.Column("last_success_at", sa.DateTime(timezone=True)),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("name", name="uq_notification_channels_name"),
    )
    op.create_table(
        "notification_routes",
        sa.Column(
            "channel_id", sa.Integer(),
            sa.ForeignKey("notification_channels.id", ondelete="CASCADE"), primary_key=True,
        ),
        sa.Column("event", sa.String(length=32), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "notification_deliveries",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "operation_id", sa.String(length=36),
            sa.ForeignKey("task_operations.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "channel_id", sa.Integer(),
            sa.ForeignKey("notification_channels.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("event", sa.String(length=32), nullable=False),
        sa.Column("operation_finished_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("error", sa.String(length=255)),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint(
            "operation_id", "channel_id", "operation_finished_at",
            name="uq_notification_delivery_operation_channel",
        ),
    )
    op.create_index(
        "ix_notification_delivery_pending", "notification_deliveries", ["status", "next_attempt_at"]
    )

    with op.batch_alter_table("push_subscriptions") as batch:
        batch.alter_column("categories", new_column_name="events")
    _rewrite_subscriptions(_CATEGORY_TO_EVENTS, "events")


def downgrade() -> None:
    _rewrite_subscriptions(
        {event: (category,) for event, category in _EVENT_TO_CATEGORY.items()}, "events"
    )
    with op.batch_alter_table("push_subscriptions") as batch:
        batch.alter_column("events", new_column_name="categories")

    op.drop_index("ix_notification_delivery_pending", table_name="notification_deliveries")
    op.drop_table("notification_deliveries")
    op.drop_table("notification_routes")
    op.drop_table("notification_channels")
