"""Add durable task operations and structured task results.

Revision ID: d4f0a9c2e713
Revises: c8d4e2f1a7b9
Create Date: 2026-09-04
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d4f0a9c2e713"
down_revision: Union[str, None] = "c8d4e2f1a7b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("task_runs", sa.Column("result", sa.JSON(), nullable=True))

    op.create_table(
        "task_operations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=120), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("resource_type", sa.String(length=80), nullable=False),
        sa.Column("resource_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("context", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("notification_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_task_operations")),
    )
    op.create_index(op.f("ix_task_operations_kind"), "task_operations", ["kind"], unique=False)
    op.create_index(op.f("ix_task_operations_source"), "task_operations", ["source"], unique=False)
    op.create_index(op.f("ix_task_operations_resource_type"), "task_operations", ["resource_type"], unique=False)
    op.create_index(op.f("ix_task_operations_resource_id"), "task_operations", ["resource_id"], unique=False)
    op.create_index(op.f("ix_task_operations_status"), "task_operations", ["status"], unique=False)
    op.create_index(
        op.f("ix_task_operations_notification_seen_at"),
        "task_operations",
        ["notification_seen_at"],
        unique=False,
    )

    op.create_table(
        "task_operation_targets",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("operation_id", sa.String(length=36), nullable=False),
        sa.Column("task_key", sa.String(length=120), nullable=False),
        sa.Column("resource_type", sa.String(length=80), nullable=False),
        sa.Column("resource_id", sa.Integer(), nullable=True),
        sa.Column("slot_key", sa.String(length=255), nullable=False),
        sa.Column("task_kwargs", sa.JSON(), nullable=True),
        sa.Column("recover_on_restart", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.ForeignKeyConstraint(
            ["operation_id"],
            ["task_operations.id"],
            name=op.f("fk_task_operation_targets_operation_id_task_operations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_task_operation_targets")),
        sa.UniqueConstraint(
            "operation_id",
            "slot_key",
            name="uq_task_operation_targets_operation_slot",
        ),
    )
    op.create_index(op.f("ix_task_operation_targets_operation_id"), "task_operation_targets", ["operation_id"], unique=False)
    op.create_index(op.f("ix_task_operation_targets_task_key"), "task_operation_targets", ["task_key"], unique=False)
    op.create_index(op.f("ix_task_operation_targets_resource_type"), "task_operation_targets", ["resource_type"], unique=False)
    op.create_index(op.f("ix_task_operation_targets_resource_id"), "task_operation_targets", ["resource_id"], unique=False)

    op.create_table(
        "task_operation_runs",
        sa.Column("target_id", sa.Integer(), nullable=False),
        sa.Column("task_run_id", sa.Integer(), nullable=False),
        sa.Column("operation_id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(
            ["operation_id"],
            ["task_operations.id"],
            name=op.f("fk_task_operation_runs_operation_id_task_operations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["target_id"],
            ["task_operation_targets.id"],
            name=op.f("fk_task_operation_runs_target_id_task_operation_targets"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["task_run_id"],
            ["task_runs.id"],
            name=op.f("fk_task_operation_runs_task_run_id_task_runs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("target_id", "task_run_id", name=op.f("pk_task_operation_runs")),
    )
    op.create_index(op.f("ix_task_operation_runs_task_run_id"), "task_operation_runs", ["task_run_id"], unique=False)
    op.create_index(op.f("ix_task_operation_runs_operation_id"), "task_operation_runs", ["operation_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_task_operation_runs_operation_id"), table_name="task_operation_runs")
    op.drop_index(op.f("ix_task_operation_runs_task_run_id"), table_name="task_operation_runs")
    op.drop_table("task_operation_runs")

    op.drop_index(op.f("ix_task_operation_targets_resource_id"), table_name="task_operation_targets")
    op.drop_index(op.f("ix_task_operation_targets_resource_type"), table_name="task_operation_targets")
    op.drop_index(op.f("ix_task_operation_targets_task_key"), table_name="task_operation_targets")
    op.drop_index(op.f("ix_task_operation_targets_operation_id"), table_name="task_operation_targets")
    op.drop_table("task_operation_targets")

    op.drop_index(op.f("ix_task_operations_notification_seen_at"), table_name="task_operations")
    op.drop_index(op.f("ix_task_operations_status"), table_name="task_operations")
    op.drop_index(op.f("ix_task_operations_resource_id"), table_name="task_operations")
    op.drop_index(op.f("ix_task_operations_resource_type"), table_name="task_operations")
    op.drop_index(op.f("ix_task_operations_source"), table_name="task_operations")
    op.drop_index(op.f("ix_task_operations_kind"), table_name="task_operations")
    op.drop_table("task_operations")

    op.drop_column("task_runs", "result")
