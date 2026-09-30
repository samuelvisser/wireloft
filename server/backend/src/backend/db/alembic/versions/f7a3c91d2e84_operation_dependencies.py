"""Convert prerelease download batch storage to generic operation dependencies.

Revision ID: f7a3c91d2e84
Revises: c2e97bfa608d

This compatibility step exists only for development databases that already ran
an earlier form of c2e97bfa608d. Fresh databases receive the final schema from
that revision directly.
"""
import json

from alembic import op
import sqlalchemy as sa

revision = "f7a3c91d2e84"
down_revision = "c2e97bfa608d"
branch_labels = None
depends_on = None


def _table_names(connection) -> set[str]:
    return set(sa.inspect(connection).get_table_names())


def _column_names(connection, table: str) -> set[str]:
    return {
        column["name"]
        for column in sa.inspect(connection).get_columns(table)
    }


def _create_dependencies() -> None:
    op.create_table(
        "task_operation_dependencies",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "parent_operation_id",
            sa.String(length=36),
            sa.ForeignKey("task_operations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "child_operation_id",
            sa.String(length=36),
            sa.ForeignKey("task_operations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("slot_key", sa.String(length=255), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False, server_default=sa.text("1")),
        sa.Column("required", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("cancel_policy", sa.String(length=32), nullable=False, server_default="detach"),
        sa.Column("context", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint(
            "parent_operation_id",
            "slot_key",
            name="uq_task_operation_dependencies_parent_slot",
        ),
        sa.UniqueConstraint(
            "parent_operation_id",
            "child_operation_id",
            name="uq_task_operation_dependencies_parent_child",
        ),
    )
    op.create_index(
        "ix_task_operation_dependencies_parent_operation_id",
        "task_operation_dependencies",
        ["parent_operation_id"],
    )
    op.create_index(
        "ix_task_operation_dependencies_child_operation_id",
        "task_operation_dependencies",
        ["child_operation_id"],
    )


def _migrate_legacy_batch_items(connection) -> None:
    """Convert already-prepared prerelease batches without runtime compatibility.

    Database migrations cannot manufacture a new media.download operation for an
    item that had not reached that point yet. Such an interrupted parent is
    canceled and can be started again by the user. Fully prepared parents keep
    tracking their existing child operations through the generic dependency DAG.
    """
    rows = list(connection.execute(sa.text("""
        SELECT
            owner_operation_id,
            owner_run_id,
            media_download_id,
            weight,
            child_operation_id,
            owns_operation
        FROM download_batch_items
        WHERE owner_operation_id IS NOT NULL
        ORDER BY id
    """)).mappings())
    if not rows:
        return

    by_parent: dict[str, list[dict]] = {}
    for row in rows:
        by_parent.setdefault(str(row["owner_operation_id"]), []).append(dict(row))

    for parent_id, items in by_parent.items():
        complete_manifest = all(item["child_operation_id"] for item in items)
        for item in items:
            child_id = item["child_operation_id"]
            if not child_id:
                continue
            exists = connection.execute(sa.text("""
                SELECT 1
                FROM task_operation_dependencies
                WHERE parent_operation_id = :parent_id
                  AND child_operation_id = :child_id
                LIMIT 1
            """), {"parent_id": parent_id, "child_id": child_id}).first()
            if exists:
                continue
            connection.execute(sa.text("""
                INSERT INTO task_operation_dependencies (
                    parent_operation_id,
                    child_operation_id,
                    slot_key,
                    weight,
                    required,
                    cancel_policy,
                    context
                ) VALUES (
                    :parent_id,
                    :child_id,
                    :slot_key,
                    :weight,
                    1,
                    :cancel_policy,
                    :context
                )
            """), {
                "parent_id": parent_id,
                "child_id": child_id,
                "slot_key": f"media_download:{int(item['media_download_id'])}",
                "weight": float(item["weight"] or 1),
                "cancel_policy": (
                    "cancel_if_exclusive"
                    if item["owns_operation"]
                    else "detach"
                ),
                "context": json.dumps({
                    "media_download_id": int(item["media_download_id"]),
                    "captured_size_bytes": int(item["weight"] or 1),
                }),
            })

        # The coordinator target is no longer part of the final architecture.
        target_ids = [
            row[0]
            for row in connection.execute(sa.text("""
                SELECT id
                FROM task_operation_targets
                WHERE operation_id = :parent_id
                  AND task_key = 'media_download_bulk_action_worker'
            """), {"parent_id": parent_id})
        ]
        if target_ids:
            connection.execute(
                sa.text("DELETE FROM task_operation_runs WHERE target_id IN :target_ids")
                .bindparams(sa.bindparam("target_ids", expanding=True)),
                {"target_ids": target_ids},
            )
            connection.execute(
                sa.text("DELETE FROM task_operation_targets WHERE id IN :target_ids")
                .bindparams(sa.bindparam("target_ids", expanding=True)),
                {"target_ids": target_ids},
            )

        run_ids = {
            int(item["owner_run_id"])
            for item in items
            if item["owner_run_id"] is not None
        }
        if run_ids:
            connection.execute(
                sa.text("""
                    UPDATE task_runs
                    SET status = 'CANCELED',
                        message = 'Superseded by generic operation dependencies',
                        finished_at = CURRENT_TIMESTAMP,
                        next_retry_at = NULL
                    WHERE id IN :run_ids
                      AND status IN ('SCHEDULED', 'QUEUED', 'RUNNING', 'RETRY_SCHEDULED')
                """).bindparams(sa.bindparam("run_ids", expanding=True)),
                {"run_ids": sorted(run_ids)},
            )

        if not complete_manifest:
            connection.execute(sa.text("""
                UPDATE task_operations
                SET status = 'CANCELED',
                    message = 'Re-download must be started again after the operation dependency upgrade',
                    completion_progress = 100,
                    finished_at = CURRENT_TIMESTAMP
                WHERE id = :parent_id
                  AND status IN ('QUEUED', 'RUNNING', 'WAITING')
            """), {"parent_id": parent_id})


def upgrade():
    connection = op.get_bind()
    tables = _table_names(connection)

    if "completion_progress" not in _column_names(connection, "task_operations"):
        op.add_column(
            "task_operations",
            sa.Column(
                "completion_progress",
                sa.Integer(),
                nullable=True,
                server_default=sa.text("0"),
            ),
        )
        op.execute(sa.text("""
            UPDATE task_operations
            SET completion_progress = CASE
                WHEN status IN ('SUCCEEDED', 'FAILED', 'PARTIAL', 'CANCELED') THEN 100
                ELSE COALESCE(progress, 0)
            END
        """))

    if "task_operation_dependencies" not in tables:
        _create_dependencies()

    if "download_batch_items" in tables:
        _migrate_legacy_batch_items(connection)
        op.drop_table("download_batch_items")


def downgrade():
    # c2e97bfa608d now defines the final dependency schema itself. Keeping this
    # schema intact when stepping back to that revision makes development
    # databases match the revised c2 contract instead of recreating a removed
    # prerelease table.
    pass
