"""Upgrade the WireLoft 1.2.5 schema to WireLoft 1.3.0.

Revision ID: e566c9fe464d
Revises: c4e93f1a2b6d
Create Date: 2026-11-03

This is the single release migration from WireLoft 1.2.5 to 1.3.0. It adds
messages and actions (destinations, rules, push devices and what was sent),
gives existing installations the default rules that a new installation gets
from the initial seed, and moves the old show 0 runs of the global Find new
episodes scan to no resource.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "e566c9fe464d"
down_revision = "c4e93f1a2b6d"
branch_labels = None
depends_on = None


# Messages and actions --------------------------------------------------------

# The default rules as they were in this release: problems pushed to your devices, the daily summary off.
_DEFAULT_RULES = (
    ("download_failed", "download_failed", True, "now"),
    ("sign_in_needed", "sign_in_needed", True, "now"),
    ("disk_almost_full", "disk_almost_full", True, "now"),
    ("task_failing", "task_failing", True, "now"),
    ("update_available", "update_available", True, "now"),
    ("daily_summary", "everything", False, "daily"),
)


def _upgrade_messages_and_actions() -> None:
    op.create_table(
        "notification_destinations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("kind", sa.String(16), nullable=False, comment="apprise, jellyfin, emby, plex, webhook or script"),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("service", sa.String(64), nullable=False, comment="The Apprise service key, or the kind"),
        sa.Column("encrypted_config", sa.Text(), nullable=False, comment="The destination's settings as encrypted JSON"),
        sa.Column("masked", sa.String(255), nullable=False, comment="The destination, safe to show"),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("last_status", sa.String(16), nullable=True),
        sa.Column("last_error", sa.String(255), nullable=True),
        sa.Column("last_attempt_at", sa.DateTime(), nullable=True),
        sa.Column("last_success_at", sa.DateTime(), nullable=True),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_notification_destinations"),
        sa.UniqueConstraint("name", name="uq_notification_destinations_name"),
    )
    op.create_table(
        "notification_rules",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("default_key", sa.String(32), nullable=True, comment="Which default rule this is, if any"),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("event", sa.String(32), nullable=False),
        sa.Column("show_scope", sa.String(16), nullable=False, comment="any or chosen"),
        sa.Column("show_ids", sa.JSON(), nullable=False),
        sa.Column("push", sa.Boolean(), nullable=False, comment="Push to every device that turned push on"),
        sa.Column("destination_ids", sa.JSON(), nullable=False),
        sa.Column("delivery", sa.String(16), nullable=False, comment="now, grouped (per show) or daily"),
        sa.Column("summary_time", sa.String(5), nullable=False, comment="When a daily summary goes out"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_notification_rules"),
    )
    op.create_table(
        "notification_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("event", sa.String(32), nullable=False),
        sa.Column("occurred_at", sa.DateTime(), nullable=False),
        sa.Column("show_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("url", sa.String(512), nullable=True, comment="The page in WireLoft it is about"),
        sa.Column("data", sa.JSON(), nullable=False, comment="Details for actions, such as the file's folder"),
        sa.Column("dedupe_key", sa.String(255), nullable=True, comment="The same problem is sent again only after a day"),
        sa.ForeignKeyConstraint(
            ["show_id"], ["shows.id"], name="fk_notification_events_show_id_shows", ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_notification_events"),
    )
    op.create_index("ix_notification_events_event", "notification_events", ["event"])
    op.create_index("ix_notification_events_dedupe", "notification_events", ["dedupe_key", "occurred_at"])
    op.create_table(
        "push_vapid_keys",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("encrypted_private_key", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_push_vapid_keys"),
    )
    op.create_table(
        "push_subscriptions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("endpoint_hash", sa.String(64), nullable=False),
        sa.Column("encrypted_subscription", sa.Text(), nullable=False),
        sa.Column("device_name", sa.String(80), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_push_subscriptions"),
        sa.UniqueConstraint("endpoint_hash", name="uq_push_subscriptions_endpoint_hash"),
    )
    op.create_table(
        "notification_deliveries",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("rule_id", sa.Integer(), nullable=True),
        sa.Column("destination_id", sa.Integer(), nullable=True),
        sa.Column("subscription_id", sa.Integer(), nullable=True),
        sa.Column("group_key", sa.String(128), nullable=True, comment="Deliveries with the same key go out as one message"),
        sa.Column("status", sa.String(16), nullable=False, comment="PENDING, SENT, FAILED or CANCELED"),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(), nullable=False),
        sa.Column("error", sa.String(255), nullable=True),
        sa.Column("sent_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["event_id"], ["notification_events.id"],
            name="fk_notification_deliveries_event_id_notification_events", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["rule_id"], ["notification_rules.id"],
            name="fk_notification_deliveries_rule_id_notification_rules", ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["destination_id"], ["notification_destinations.id"],
            name="fk_notification_deliveries_destination_id_notification_destinations", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["subscription_id"], ["push_subscriptions.id"],
            name="fk_notification_deliveries_subscription_id_push_subscriptions", ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_notification_deliveries"),
    )
    op.create_index("ix_notification_deliveries_event_id", "notification_deliveries", ["event_id"])
    op.create_index("ix_notification_deliveries_pending", "notification_deliveries", ["status", "next_attempt_at"])

    rules = sa.table(
        "notification_rules",
        sa.column("position", sa.Integer), sa.column("default_key", sa.String), sa.column("enabled", sa.Boolean),
        sa.column("event", sa.String), sa.column("show_scope", sa.String), sa.column("show_ids", sa.JSON),
        sa.column("push", sa.Boolean), sa.column("destination_ids", sa.JSON), sa.column("delivery", sa.String),
        sa.column("summary_time", sa.String),
    )
    op.bulk_insert(rules, [
        {
            "position": position, "default_key": key, "enabled": enabled, "event": event, "show_scope": "any",
            "show_ids": [], "push": True, "destination_ids": [], "delivery": delivery, "summary_time": "08:00",
        }
        for position, (key, event, enabled, delivery) in enumerate(_DEFAULT_RULES, start=1)
    ])


def _downgrade_messages_and_actions() -> None:
    op.drop_table("notification_deliveries")
    op.drop_table("push_subscriptions")
    op.drop_table("push_vapid_keys")
    op.drop_table("notification_events")
    op.drop_table("notification_rules")
    op.drop_table("notification_destinations")


# Global episode scans --------------------------------------------------------
# Find new episodes used show 0 for "all shows"; it now runs without a resource.

def _set_global_scan_resource_id(old: str, new: str) -> None:
    op.execute(sa.text(f"""
        UPDATE task_runs
        SET resource_id = {new}
        WHERE resource_id {old}
          AND definition_id IN (SELECT id FROM task_definitions WHERE key = 'fetch_new_episodes')
    """))
    op.execute(sa.text(f"""
        UPDATE task_operation_targets
        SET resource_id = {new}
        WHERE resource_id {old} AND task_key = 'fetch_new_episodes'
    """))


# Release migration -----------------------------------------------------------


def upgrade() -> None:
    _upgrade_messages_and_actions()
    _set_global_scan_resource_id("= 0", "NULL")


def downgrade() -> None:
    _set_global_scan_resource_id("IS NULL", "0")
    _downgrade_messages_and_actions()
