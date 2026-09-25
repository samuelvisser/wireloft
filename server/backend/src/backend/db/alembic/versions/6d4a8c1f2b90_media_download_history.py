"""Restore persistent media download action history.

Revision ID: 6d4a8c1f2b90
Revises: 6d1e8f2a4c73
"""

from __future__ import annotations

import json
from typing import Any, Mapping

from alembic import op
import sqlalchemy as sa


revision = "6d4a8c1f2b90"
down_revision = "6d1e8f2a4c73"
branch_labels = None
depends_on = None


_DOWNLOAD_TASK_KEYS = ("download_episode", "download_movie")
_MEDIA_DOWNLOAD_RESOURCE_VALUE = "MEDIA_DOWNLOAD"


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _is_redownload(meta: Any, result: Any) -> bool:
    inputs = _json_object(_json_object(meta).get("inputs"))
    value = inputs.get("is_redownload")
    if isinstance(value, bool):
        return value

    data = _json_object(_json_object(result).get("data"))
    value = data.get("is_redownload")
    return value if isinstance(value, bool) else False


def _terminal_metadata(row: Mapping[str, Any]) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "is_redownload": _is_redownload(row["meta"], row["result"]),
        "migrated_task_run_id": row["id"],
    }
    if row["runtime_ms"] is not None:
        metadata["duration_ms"] = int(row["runtime_ms"])

    result_data = _json_object(_json_object(row["result"]).get("data"))
    for key in (
        "downloaded_bytes",
        "format_downloaded",
        "file_path",
        "thumbnail_path",
    ):
        value = result_data.get(key)
        if value is not None:
            metadata[key] = value
    return metadata


def _backfill_task_history(connection, history_table) -> None:
    inspector = sa.inspect(connection)
    table_names = set(inspector.get_table_names())
    if not {"task_runs", "task_definitions", "media_downloads"}.issubset(table_names):
        return

    metadata = sa.MetaData()
    task_runs = sa.Table("task_runs", metadata, autoload_with=connection)
    task_definitions = sa.Table("task_definitions", metadata, autoload_with=connection)
    media_downloads = sa.Table("media_downloads", metadata, autoload_with=connection)

    rows = connection.execute(
        sa.select(
            task_runs.c.id,
            task_runs.c.resource_id,
            task_runs.c.status,
            task_runs.c.meta,
            task_runs.c.result,
            task_runs.c.message,
            task_runs.c.last_error,
            task_runs.c.started_at,
            task_runs.c.finished_at,
            task_runs.c.runtime_ms,
            task_runs.c.created_at,
            task_runs.c.updated_at,
        )
        .select_from(
            task_runs
            .join(
                task_definitions,
                task_definitions.c.id == task_runs.c.definition_id,
            )
            .join(
                media_downloads,
                media_downloads.c.id == task_runs.c.resource_id,
            )
        )
        .where(
            task_definitions.c.key.in_(_DOWNLOAD_TASK_KEYS),
            task_runs.c.resource_type == _MEDIA_DOWNLOAD_RESOURCE_VALUE,
            task_runs.c.resource_id.is_not(None),
        )
        .order_by(task_runs.c.id)
    ).mappings()

    inserts: list[dict[str, Any]] = []
    for row in rows:
        is_redownload = _is_redownload(row["meta"], row["result"])
        started_at = row["started_at"]
        if started_at is not None:
            inserts.append({
                "media_download_id": row["resource_id"],
                "action": "started",
                "metadata": {
                    "is_redownload": is_redownload,
                    "migrated_task_run_id": row["id"],
                },
                "occurred_at": started_at,
            })

        status = str(row["status"])
        # Reflected enum columns can return either the raw string or an Enum.
        if "." in status:
            status = status.rsplit(".", 1)[-1]
        status = status.upper()

        action = None
        terminal_metadata = _terminal_metadata(row)
        if status == "SUCCEEDED":
            action = "completed"
        elif status == "FAILED":
            action = "failed"
            error = row["last_error"] or row["message"]
            if error:
                terminal_metadata["error"] = str(error)
        elif status in {"CANCELED", "CANCELLED"}:
            action = "cancelled"
            reason = row["message"] or row["last_error"]
            if reason:
                terminal_metadata["reason"] = str(reason)

        if action is None:
            continue

        occurred_at = (
            row["finished_at"]
            or row["updated_at"]
            or row["started_at"]
            or row["created_at"]
        )
        inserts.append({
            "media_download_id": row["resource_id"],
            "action": action,
            "metadata": terminal_metadata,
            "occurred_at": occurred_at,
        })

    if inserts:
        connection.execute(history_table.insert(), inserts)


def upgrade() -> None:
    op.create_table(
        "media_download_history",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("media_download_id", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["media_download_id"],
            ["media_downloads.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_media_download_history_media_download_id",
        "media_download_history",
        ["media_download_id"],
        unique=False,
    )
    op.create_index(
        "ix_media_download_history_action",
        "media_download_history",
        ["action"],
        unique=False,
    )
    op.create_index(
        "ix_media_download_history_occurred_at",
        "media_download_history",
        ["occurred_at"],
        unique=False,
    )

    connection = op.get_bind()
    history_table = sa.Table(
        "media_download_history",
        sa.MetaData(),
        autoload_with=connection,
    )
    _backfill_task_history(connection, history_table)


def downgrade() -> None:
    op.drop_index(
        "ix_media_download_history_occurred_at",
        table_name="media_download_history",
    )
    op.drop_index(
        "ix_media_download_history_action",
        table_name="media_download_history",
    )
    op.drop_index(
        "ix_media_download_history_media_download_id",
        table_name="media_download_history",
    )
    op.drop_table("media_download_history")
