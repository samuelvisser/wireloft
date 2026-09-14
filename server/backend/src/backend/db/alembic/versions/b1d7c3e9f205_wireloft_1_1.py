"""Upgrade the shipped WireLoft 1.0 schema to WireLoft 1.1.

Revision ID: b1d7c3e9f205
Revises: c8d4e2f1a7b9
Create Date: 2026-09-14

This is the single release migration from the schema shipped in WireLoft 1.0
to WireLoft 1.1. All schema and data changes developed for 1.1 are consolidated
here so no transient development revisions become part of the permanent
migration history.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
import re
import stat
from typing import BinaryIO
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from alembic import op
from alembic.runtime.migration import MigrationContext
from alembic.util import CommandError
import sqlalchemy as sa

from backend.db.alembic_version import (
    SETTINGS_VERSION_COLUMN,
    SETTINGS_VERSION_TABLE,
    apply_settings_version_table,
)


revision = "b1d7c3e9f205"
down_revision = "c8d4e2f1a7b9"
branch_labels = None
depends_on = None


_TASK_RENAMES = {
    "monitor_episode_worker": "monitor_pending_episode",
    "cleanup_episodes_stuck_without_media": "monitor_no_usable_media_episode",
    "refresh_episode_metadata_worker": "refresh_episode_metadata",
}
_NUMBERED_RE = re.compile(r"^ep\.(\d+)$")
_SEASONAL_RE = re.compile(r"^ep\.S(\d+)E(\d+)$")
_METADATA_RENAMES = {
    "dw_processing.reason": "no_usable_media.reason",
    "dw_processing.since": "no_usable_media.since",
}

_FINGERPRINT_SAMPLE_SIZE = 64 * 1024
_FINGERPRINT_VERSION = b"wireloft-artifact-v1\0"
_IDENTITY_CONSTRAINT = "ck_media_downloads_artifact_identity_complete"
_IDENTITY_CHECK = (
    "artifact_status IN ('absent', 'missing') OR ("
    "artifact_stat_dev IS NOT NULL AND length(artifact_stat_dev) > 0 AND "
    "artifact_stat_ino IS NOT NULL AND length(artifact_stat_ino) > 0 AND "
    "artifact_size_bytes IS NOT NULL AND artifact_size_bytes >= 0 AND "
    "artifact_fingerprint IS NOT NULL AND length(artifact_fingerprint) = 64"
    ")"
)

_LEGACY_VERSION_TABLE = "alembic_version"
_UNMANAGED_TABLES = {"apscheduler_jobs"}
_CONTENT_FIELDS = (
    "title",
    "description",
    "duration",
    "background_image_path",
    "thumbnail_landscape_path",
    "thumbnail_portrait_path",
    "thumbnail_square_path",
)
_SOURCE_FIELDS = (
    *_CONTENT_FIELDS,
    "sharing_url",
    "published_date",
    "available_for",
)

_DW_VIDEO_METHOD_QUERY_PARAMETER = "dwVideoMethod"
_LEGACY_TO_CANONICAL_METHOD = {
    "podcasting_2_0": "stream_hls_download_m4a",
    "cached_mp4": "stream_download_mp4",
    "podcasting_2_0_cached_mp4": "stream_hls_download_mp4",
}


def _column_names(bind, table_name: str) -> set[str]:
    inspector = sa.inspect(bind)
    if not inspector.has_table(table_name):
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def _legacy_version_table() -> sa.Table:
    return sa.Table(
        _LEGACY_VERSION_TABLE,
        sa.MetaData(),
        sa.Column("version_num", sa.String(32), primary_key=True, nullable=False),
    )


def _legacy_revisions(bind) -> tuple[str, ...]:
    return tuple(
        bind.execute(
            sa.select(_legacy_version_table().c.version_num)
        ).scalars()
    )


def _settings_version_rows(bind) -> list[dict]:
    return list(bind.execute(sa.text(
        f"SELECT id, {SETTINGS_VERSION_COLUMN} "
        f"FROM {SETTINGS_VERSION_TABLE} ORDER BY id"
    )).mappings())


def configure_version_storage_for_upgrade(context: MigrationContext) -> None:
    """Select version storage while upgrading across the 1.1 boundary."""
    connection = context.connection
    if connection is None:
        return

    inspector = sa.inspect(connection)
    tables = set(inspector.get_table_names())
    application_tables = tables - _UNMANAGED_TABLES

    if not application_tables:
        return

    settings_has_version = (
        SETTINGS_VERSION_TABLE in tables
        and SETTINGS_VERSION_COLUMN in _column_names(connection, SETTINGS_VERSION_TABLE)
    )
    legacy_exists = _LEGACY_VERSION_TABLE in tables

    if legacy_exists:
        return

    if not settings_has_version:
        raise CommandError(
            "Database contains tables but is not Alembic-managed by a supported WireLoft schema. "
            "Delete/recreate it, or manually stamp the correct Alembic revision before upgrading."
        )

    settings_rows = _settings_version_rows(connection)
    if len(settings_rows) != 1 or settings_rows[0][SETTINGS_VERSION_COLUMN] is None:
        raise CommandError(
            "settings.alembic_version_num must contain exactly one current revision before upgrading."
        )

    apply_settings_version_table(context)


def _handoff_version_storage(bind) -> None:
    """Move Alembic's live context from the 1.0 version table into Settings."""
    inspector = sa.inspect(bind)
    if not inspector.has_table(_LEGACY_VERSION_TABLE):
        apply_settings_version_table(op.get_context())
        return

    revisions = _legacy_revisions(bind)
    if len(revisions) != 1:
        raise RuntimeError(
            "Cannot move Alembic version tracking into settings unless the database "
            f"has exactly one current revision; found {revisions}."
        )

    current_revision = revisions[0]
    if current_revision != down_revision:
        raise RuntimeError(
            "The WireLoft 1.1 version-storage handoff can only run while upgrading "
            f"from {down_revision}; found {current_revision}."
        )

    settings_rows = _settings_version_rows(bind)
    if len(settings_rows) != 1:
        raise RuntimeError(
            "The settings table must contain exactly one row before Alembic "
            "version tracking can be moved into it."
        )

    stored_revision = settings_rows[0][SETTINGS_VERSION_COLUMN]
    if stored_revision not in (None, current_revision):
        raise RuntimeError(
            "settings.alembic_version_num disagrees with the legacy Alembic version table."
        )

    bind.execute(
        sa.text(
            f"UPDATE {SETTINGS_VERSION_TABLE} "
            f"SET {SETTINGS_VERSION_COLUMN} = :revision WHERE id = :settings_id"
        ),
        {
            "revision": current_revision,
            "settings_id": settings_rows[0]["id"],
        },
    )

    # Alembic records c8 -> b1 after upgrade() returns. Switch the live context
    # first so that update is written directly to Settings.
    _legacy_version_table().drop(bind)
    apply_settings_version_table(op.get_context())


# Task operations -----------------------------------------------------------


def _upgrade_task_operations() -> None:
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
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_task_operations")),
    )
    op.create_index(op.f("ix_task_operations_kind"), "task_operations", ["kind"], unique=False)
    op.create_index(op.f("ix_task_operations_source"), "task_operations", ["source"], unique=False)
    op.create_index(
        op.f("ix_task_operations_resource_type"),
        "task_operations",
        ["resource_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_task_operations_resource_id"),
        "task_operations",
        ["resource_id"],
        unique=False,
    )
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
    op.create_index(
        op.f("ix_task_operation_targets_operation_id"),
        "task_operation_targets",
        ["operation_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_task_operation_targets_task_key"),
        "task_operation_targets",
        ["task_key"],
        unique=False,
    )
    op.create_index(
        op.f("ix_task_operation_targets_resource_type"),
        "task_operation_targets",
        ["resource_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_task_operation_targets_resource_id"),
        "task_operation_targets",
        ["resource_id"],
        unique=False,
    )

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
        sa.PrimaryKeyConstraint(
            "target_id",
            "task_run_id",
            name=op.f("pk_task_operation_runs"),
        ),
    )
    op.create_index(
        op.f("ix_task_operation_runs_task_run_id"),
        "task_operation_runs",
        ["task_run_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_task_operation_runs_operation_id"),
        "task_operation_runs",
        ["operation_id"],
        unique=False,
    )


def _downgrade_task_operations() -> None:
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


# Download execution --------------------------------------------------------


def _upgrade_download_execution() -> None:
    with op.batch_alter_table("media_downloads") as batch:
        batch.add_column(
            sa.Column(
                "artifact_status",
                sa.String(length=24),
                nullable=False,
                server_default="absent",
            )
        )
        batch.add_column(sa.Column("artifact_error", sa.Text(), nullable=True))
        batch.add_column(
            sa.Column(
                "automatic_retry_suppressed",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("0"),
            )
        )
        batch.add_column(sa.Column("downloaded_at", sa.DateTime(timezone=True), nullable=True))
        batch.create_index(
            "ix_media_downloads_artifact_status",
            ["artifact_status"],
            unique=False,
        )

    op.execute(
        sa.text(
            """
            UPDATE media_downloads
            SET artifact_status = CASE
                    WHEN download_status IN ('downloaded', 'redownloaded') THEN 'available'
                    WHEN download_status = 'missing' THEN 'missing'
                    WHEN download_status = 'corrupted' THEN 'corrupted'
                    ELSE 'absent'
                END,
                artifact_error = CASE
                    WHEN download_status IN ('missing', 'corrupted') THEN error_message
                    ELSE NULL
                END,
                automatic_retry_suppressed = CASE
                    WHEN download_status = 'cancelled' THEN 1
                    ELSE 0
                END,
                downloaded_at = CASE
                    WHEN download_status IN ('downloaded', 'redownloaded') THEN finished_at
                    ELSE NULL
                END
            """
        )
    )

    with op.batch_alter_table("media_downloads") as batch:
        batch.drop_column("download_status")
        batch.drop_column("progress")
        batch.drop_column("error_message")
        batch.drop_column("started_at")
        batch.drop_column("finished_at")
        batch.drop_column("attempt_generation")

    with op.batch_alter_table("media_downloads_episode") as batch:
        batch.drop_column("is_redownload_attempt")


def _downgrade_download_execution() -> None:
    with op.batch_alter_table("media_downloads") as batch:
        batch.add_column(sa.Column("download_status", sa.String(), nullable=True))
        batch.add_column(
            sa.Column("progress", sa.Integer(), nullable=False, server_default="0")
        )
        batch.add_column(sa.Column("error_message", sa.String(), nullable=True))
        batch.add_column(sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(
            sa.Column(
                "attempt_generation",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )

    op.execute(
        sa.text(
            """
            UPDATE media_downloads
            SET download_status = CASE
                    WHEN artifact_status = 'available' THEN 'downloaded'
                    WHEN artifact_status = 'missing' THEN 'missing'
                    WHEN artifact_status = 'corrupted' THEN 'corrupted'
                    WHEN automatic_retry_suppressed = 1 THEN 'cancelled'
                    ELSE 'error'
                END,
                progress = CASE WHEN artifact_status = 'available' THEN 100 ELSE 0 END,
                error_message = artifact_error,
                finished_at = downloaded_at,
                attempt_generation = 0
            """
        )
    )

    with op.batch_alter_table("media_downloads_episode") as batch:
        batch.add_column(
            sa.Column("is_redownload_attempt", sa.Boolean(), nullable=True)
        )

    with op.batch_alter_table("media_downloads") as batch:
        batch.drop_index("ix_media_downloads_artifact_status")
        batch.drop_column("artifact_status")
        batch.drop_column("artifact_error")
        batch.drop_column("automatic_retry_suppressed")
        batch.drop_column("downloaded_at")


# Legacy download-attempt ledger -------------------------------------------


def _upgrade_drop_media_download_attempts() -> None:
    op.drop_table("media_download_attempts")


def _downgrade_drop_media_download_attempts() -> None:
    op.create_table(
        "media_download_attempts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("media_download_id", sa.Integer(), nullable=False),
        sa.Column("is_redownload", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("error_message", sa.String(), nullable=True),
        sa.Column("downloaded_bytes", sa.Integer(), nullable=True),
        sa.Column("format_downloaded", sa.String(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["media_download_id"],
            ["media_downloads.id"],
            name=op.f("fk_media_download_attempts_media_download_id_media_downloads"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_media_download_attempts")),
    )
    op.create_index(
        op.f("ix_media_download_attempts_media_download_id"),
        "media_download_attempts",
        ["media_download_id"],
        unique=False,
    )


# Datetime contract ---------------------------------------------------------


def _upgrade_datetime_contract() -> None:
    with op.batch_alter_table("task_schedules") as batch:
        batch.drop_column("timezone")


def _downgrade_datetime_contract() -> None:
    with op.batch_alter_table("task_schedules") as batch:
        batch.add_column(sa.Column("timezone", sa.String(), nullable=True))


# Episode release lifecycle ------------------------------------------------


def _as_datetime(value) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, datetime):
        try:
            value = datetime.fromisoformat(str(value))
        except ValueError:
            return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _meta_value(connection, parent_table: str, parent_id: int, key: str) -> str | None:
    return connection.execute(
        sa.text(
            "SELECT value FROM metadata "
            "WHERE parent_table=:table AND parent_id=:parent_id AND key=:key"
        ),
        {"table": parent_table, "parent_id": parent_id, "key": key},
    ).scalar_one_or_none()


def _set_meta(
    connection,
    parent_table: str,
    parent_id: int,
    key: str,
    value: str,
) -> None:
    existing = connection.execute(
        sa.text(
            "SELECT id FROM metadata "
            "WHERE parent_table=:table AND parent_id=:parent_id AND key=:key"
        ),
        {"table": parent_table, "parent_id": parent_id, "key": key},
    ).scalar_one_or_none()
    if existing is None:
        connection.execute(
            sa.text(
                "INSERT INTO metadata (parent_table,parent_id,key,value) "
                "VALUES (:table,:parent_id,:key,:value)"
            ),
            {
                "table": parent_table,
                "parent_id": parent_id,
                "key": key,
                "value": value,
            },
        )
    else:
        connection.execute(
            sa.text("UPDATE metadata SET value=:value WHERE id=:id"),
            {"value": value, "id": existing},
        )


def _remaining_identifiers(connection, show_id: int, exclude_id: int) -> list[str]:
    return [
        str(row[0])
        for row in connection.execute(
            sa.text(
                "SELECT episode_identifier FROM episodes "
                "WHERE show_id=:show_id AND id != :episode_id"
            ),
            {"show_id": show_id, "episode_id": exclude_id},
        )
    ]


def _rollback_head_for_quarantine(
    connection,
    *,
    episode_id: int,
    show_id: int,
    previous: str,
    show_type: str,
    season_id: int,
) -> None:
    identifiers = _remaining_identifiers(connection, show_id, episode_id)
    if show_type == "numbered":
        match = _NUMBERED_RE.fullmatch(previous)
        if not match:
            return
        number = int(match.group(1))
        if int(_meta_value(connection, "shows", show_id, "ep_id.latest_ep_num") or 0) != number:
            return
        remaining = [
            int(m.group(1))
            for value in identifiers
            if (m := _NUMBERED_RE.fullmatch(value))
        ]
        new_head = max(remaining, default=0)
        _set_meta(connection, "shows", show_id, "ep_id.latest_ep_num", str(new_head))
        extra_re = (
            re.compile(rf"^ep-extra\.{new_head}\.(\d+)$")
            if new_head
            else re.compile(r"a^")
        )
        extras = [
            int(m.group(1))
            for value in identifiers
            if (m := extra_re.fullmatch(value))
        ]
        _set_meta(
            connection,
            "shows",
            show_id,
            "ep_id.latest_ep_extra_num",
            str(max(extras, default=0)),
        )
        return

    if show_type == "seasonal":
        match = _SEASONAL_RE.fullmatch(previous)
        if not match:
            return
        season_number, number = int(match.group(1)), int(match.group(2))
        actual_season = connection.execute(
            sa.text("SELECT `index` FROM seasons WHERE id=:season_id"),
            {"season_id": season_id},
        ).scalar_one_or_none()
        if actual_season != season_number:
            return
        key = f"ep_id.latest_season_{season_number}_ep"
        if int(_meta_value(connection, "shows", show_id, key) or 0) != number:
            return
        main_re = re.compile(rf"^ep\.S{season_number:02d}E(\d+)$")
        remaining = [
            int(m.group(1))
            for value in identifiers
            if (m := main_re.fullmatch(value))
        ]
        new_head = max(remaining, default=0)
        _set_meta(connection, "shows", show_id, key, str(new_head))
        extra_re = (
            re.compile(rf"^ep-extra\.S{season_number:02d}E{new_head:02d}\.(\d+)$")
            if new_head
            else re.compile(r"a^")
        )
        extras = [
            int(m.group(1))
            for value in identifiers
            if (m := extra_re.fullmatch(value))
        ]
        _set_meta(
            connection,
            "shows",
            show_id,
            "ep_id.latest_ep_extra_num",
            str(max(extras, default=0)),
        )
        return

    if show_type == "date_based":
        published = _as_datetime(
            connection.execute(
                sa.text("SELECT published_date FROM episodes WHERE id=:episode_id"),
                {"episode_id": episode_id},
            ).scalar_one_or_none()
        )
        if published is None:
            return
        timestamp = int(published.timestamp())
        if int(_meta_value(connection, "shows", show_id, "ep_id.latest_ep_date") or 0) != timestamp:
            return
        remaining_dates = [
            parsed
            for row in connection.execute(
                sa.text(
                    "SELECT published_date FROM episodes "
                    "WHERE show_id=:show_id AND id != :episode_id "
                    "AND episode_identifier LIKE 'ep.%' AND published_date IS NOT NULL"
                ),
                {"show_id": show_id, "episode_id": episode_id},
            )
            if (parsed := _as_datetime(row[0])) is not None
        ]
        new_head = max((int(value.timestamp()) for value in remaining_dates), default=0)
        _set_meta(connection, "shows", show_id, "ep_id.latest_ep_date", str(new_head))


def _task_definition_id(connection, key: str) -> int | None:
    return connection.execute(
        sa.text("SELECT id FROM task_definitions WHERE key=:key"),
        {"key": key},
    ).scalar_one_or_none()


def _migrate_task_key(connection, old: str, new: str) -> None:
    old_id = _task_definition_id(connection, old)
    new_id = _task_definition_id(connection, new)

    if old_id is not None:
        if new_id is not None and new_id != old_id:
            connection.execute(
                sa.text(
                    "UPDATE task_runs SET definition_id=:old_id "
                    "WHERE definition_id=:new_id"
                ),
                {"old_id": old_id, "new_id": new_id},
            )
            connection.execute(
                sa.text(
                    "UPDATE task_schedules SET definition_id=:old_id "
                    "WHERE definition_id=:new_id"
                ),
                {"old_id": old_id, "new_id": new_id},
            )
            connection.execute(
                sa.text("DELETE FROM task_definitions WHERE id=:new_id"),
                {"new_id": new_id},
            )
        connection.execute(
            sa.text("UPDATE task_definitions SET key=:new WHERE id=:old_id"),
            {"old_id": old_id, "new": new},
        )

    connection.execute(
        sa.text("UPDATE task_operation_targets SET task_key=:new WHERE task_key=:old"),
        {"old": old, "new": new},
    )
    connection.execute(
        sa.text(
            "UPDATE task_operation_targets "
            "SET slot_key=REPLACE(slot_key,:old,:new) "
            "WHERE slot_key LIKE :pattern"
        ),
        {"old": old, "new": new, "pattern": f"%{old}%"},
    )


def _quarantine_existing_no_usable_rows(connection) -> None:
    rows = list(
        connection.execute(
            sa.text(
                "SELECT e.id,e.show_id,e.season_id,e.episode_identifier,s.episode_identifier "
                "FROM episodes e JOIN shows s ON s.id=e.show_id "
                "WHERE e.publish_status='no_usable_media' "
                "AND e.episode_identifier NOT LIKE 'not-usable.%' "
                "ORDER BY e.show_id,e.id"
            )
        )
    )
    counters: dict[int, int] = {}
    for episode_id, show_id, season_id, previous, show_type in rows:
        counter = counters.get(show_id)
        if counter is None:
            counter = int(
                _meta_value(
                    connection,
                    "shows",
                    show_id,
                    "ep_id.latest_not_usable_num",
                )
                or 0
            )
        counter += 1
        counters[show_id] = counter
        _set_meta(
            connection,
            "episodes",
            episode_id,
            "no_usable_media.previous_identifier",
            str(previous),
        )
        connection.execute(
            sa.text(
                "UPDATE episodes SET episode_identifier=:identifier "
                "WHERE id=:episode_id"
            ),
            {
                "identifier": f"not-usable.{counter}",
                "episode_id": episode_id,
            },
        )
        _rollback_head_for_quarantine(
            connection,
            episode_id=episode_id,
            show_id=show_id,
            previous=str(previous),
            show_type=str(show_type),
            season_id=season_id,
        )
    for show_id, counter in counters.items():
        _set_meta(
            connection,
            "shows",
            show_id,
            "ep_id.latest_not_usable_num",
            str(counter),
        )


def _upgrade_episode_release_lifecycle() -> None:
    connection = op.get_bind()
    for old, new in _TASK_RENAMES.items():
        _migrate_task_key(connection, old, new)
    _quarantine_existing_no_usable_rows(connection)
    with op.batch_alter_table("episodes") as batch:
        batch.drop_column("is_no_show_today")


def _downgrade_episode_release_lifecycle() -> None:
    connection = op.get_bind()
    with op.batch_alter_table("episodes") as batch:
        batch.add_column(sa.Column("is_no_show_today", sa.Boolean(), nullable=True))
    connection.execute(
        sa.text(
            "UPDATE episodes SET is_no_show_today = CASE "
            "WHEN lower(slug) LIKE '%no-show-today%' THEN 1 ELSE 0 END"
        )
    )
    for old, new in _TASK_RENAMES.items():
        _migrate_task_key(connection, new, old)


# Episode lifecycle metadata ------------------------------------------------


def _migrate_metadata_key(connection, old: str, new: str) -> None:
    rows = list(
        connection.execute(
            sa.text(
                "SELECT id,parent_id FROM metadata "
                "WHERE parent_table='episodes' AND key=:old"
            ),
            {"old": old},
        )
    )

    for legacy_id, episode_id in rows:
        canonical_id = connection.execute(
            sa.text(
                "SELECT id FROM metadata "
                "WHERE parent_table='episodes' "
                "AND parent_id=:episode_id AND key=:new"
            ),
            {"episode_id": episode_id, "new": new},
        ).scalar_one_or_none()

        if canonical_id is None:
            connection.execute(
                sa.text("UPDATE metadata SET key=:new WHERE id=:legacy_id"),
                {"new": new, "legacy_id": legacy_id},
            )
        else:
            connection.execute(
                sa.text("DELETE FROM metadata WHERE id=:legacy_id"),
                {"legacy_id": legacy_id},
            )


def _upgrade_episode_lifecycle_metadata() -> None:
    connection = op.get_bind()
    for old, new in _METADATA_RENAMES.items():
        _migrate_metadata_key(connection, old, new)


def _downgrade_episode_lifecycle_metadata() -> None:
    connection = op.get_bind()
    for old, new in reversed(tuple(_METADATA_RENAMES.items())):
        _migrate_metadata_key(connection, new, old)


# Show Local Media Profile scope -------------------------------------------


def _upgrade_show_local_media_profile_scope() -> None:
    op.add_column(
        "local_media_profiles_show",
        sa.Column(
            "show_scope",
            sa.String(),
            server_default="both",
            nullable=False,
        ),
    )


def _downgrade_show_local_media_profile_scope() -> None:
    op.drop_column("local_media_profiles_show", "show_scope")


# Artifact identity ---------------------------------------------------------


def _sampled_fingerprint(file: BinaryIO, size_bytes: int) -> str:
    digest = hashlib.sha256()
    digest.update(_FINGERPRINT_VERSION)
    digest.update(size_bytes.to_bytes(16, "big", signed=False))

    if size_bytes <= _FINGERPRINT_SAMPLE_SIZE * 3:
        offsets = (0,)
        read_sizes = (size_bytes,)
    else:
        middle_offset = max(0, (size_bytes - _FINGERPRINT_SAMPLE_SIZE) // 2)
        offsets = (0, middle_offset, size_bytes - _FINGERPRINT_SAMPLE_SIZE)
        read_sizes = (_FINGERPRINT_SAMPLE_SIZE,) * 3

    for offset, read_size in zip(offsets, read_sizes, strict=True):
        file.seek(offset)
        chunk = file.read(read_size)
        if len(chunk) != read_size:
            raise OSError(
                f"artifact changed while fingerprinting: expected {read_size} bytes "
                f"at offset {offset}, read {len(chunk)}"
            )
        digest.update(offset.to_bytes(16, "big", signed=False))
        digest.update(read_size.to_bytes(8, "big", signed=False))
        digest.update(chunk)

    return digest.hexdigest()


def _inspect_artifact(path: str) -> tuple[str, str, int, str]:
    with open(path, "rb") as file:
        file_stat = os.fstat(file.fileno())
        if not stat.S_ISREG(file_stat.st_mode):
            raise ValueError("path is not a regular file")
        return (
            str(file_stat.st_dev),
            str(file_stat.st_ino),
            file_stat.st_size,
            _sampled_fingerprint(file, file_stat.st_size),
        )


def _missing_error(path: str, exc: OSError | ValueError) -> str:
    if isinstance(exc, FileNotFoundError):
        return f"File not found at '{path}'"
    return f"Could not check '{path}': {exc}"


def _upgrade_artifact_identity() -> None:
    connection = op.get_bind()
    downloads = connection.execute(
        sa.text(
            "SELECT id, file_path FROM media_downloads "
            "WHERE artifact_status != 'absent' ORDER BY id"
        )
    ).mappings().all()

    identities: list[tuple[int, str, str, int, str]] = []
    missing_artifacts: list[tuple[int, str]] = []
    for download in downloads:
        download_id = download["id"]
        path = download["file_path"]
        try:
            stat_dev, stat_ino, size_bytes, fingerprint = _inspect_artifact(path)
        except (OSError, ValueError) as exc:
            missing_artifacts.append((download_id, _missing_error(path, exc)))
            continue
        identities.append(
            (download_id, stat_dev, stat_ino, size_bytes, fingerprint)
        )

    with op.batch_alter_table("media_downloads") as batch:
        batch.add_column(
            sa.Column("artifact_stat_dev", sa.String(length=32), nullable=True)
        )
        batch.add_column(
            sa.Column("artifact_stat_ino", sa.String(length=32), nullable=True)
        )
        batch.add_column(sa.Column("artifact_size_bytes", sa.BigInteger(), nullable=True))
        batch.add_column(
            sa.Column("artifact_fingerprint", sa.String(length=64), nullable=True)
        )

    for download_id, stat_dev, stat_ino, size_bytes, fingerprint in identities:
        connection.execute(
            sa.text(
                "UPDATE media_downloads SET "
                "artifact_stat_dev = :stat_dev, "
                "artifact_stat_ino = :stat_ino, "
                "artifact_size_bytes = :size_bytes, "
                "artifact_fingerprint = :fingerprint "
                "WHERE id = :download_id"
            ),
            {
                "stat_dev": stat_dev,
                "stat_ino": stat_ino,
                "size_bytes": size_bytes,
                "fingerprint": fingerprint,
                "download_id": download_id,
            },
        )

    for download_id, error in missing_artifacts:
        connection.execute(
            sa.text(
                "UPDATE media_downloads SET "
                "artifact_status = 'missing', "
                "artifact_error = :error "
                "WHERE id = :download_id"
            ),
            {"error": error, "download_id": download_id},
        )

    with op.batch_alter_table("media_downloads") as batch:
        batch.create_check_constraint(_IDENTITY_CONSTRAINT, _IDENTITY_CHECK)


def _downgrade_artifact_identity() -> None:
    with op.batch_alter_table("media_downloads") as batch:
        batch.drop_constraint(_IDENTITY_CONSTRAINT, type_="check")
        batch.drop_column("artifact_fingerprint")
        batch.drop_column("artifact_size_bytes")
        batch.drop_column("artifact_stat_ino")
        batch.drop_column("artifact_stat_dev")


# Media database refactor ---------------------------------------------------


def _add_movie_page_metadata() -> None:
    with op.batch_alter_table("movies") as batch:
        batch.add_column(
            sa.Column(
                "has_video",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )
        batch.add_column(sa.Column("status", sa.String(), nullable=True))
        batch.add_column(
            sa.Column("published_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch.add_column(sa.Column("background", sa.String(), nullable=True))
        batch.add_column(sa.Column("byline", sa.String(), nullable=True))
        batch.add_column(sa.Column("language", sa.String(), nullable=True))
        batch.add_column(sa.Column("origin_country", sa.String(), nullable=True))
        batch.add_column(
            sa.Column("images", sa.JSON(), nullable=False, server_default="{}")
        )
        batch.add_column(
            sa.Column("cast_and_crew", sa.JSON(), nullable=False, server_default="[]")
        )
        batch.add_column(
            sa.Column("directed_by", sa.JSON(), nullable=False, server_default="[]")
        )
        batch.add_column(
            sa.Column("genres", sa.JSON(), nullable=False, server_default="[]")
        )
        batch.add_column(
            sa.Column("hosts", sa.JSON(), nullable=False, server_default="[]")
        )
        batch.add_column(
            sa.Column("more_like_this", sa.JSON(), nullable=False, server_default="[]")
        )
        batch.add_column(
            sa.Column(
                "production_companies",
                sa.JSON(),
                nullable=False,
                server_default="[]",
            )
        )
        batch.add_column(
            sa.Column("shop_items", sa.JSON(), nullable=False, server_default="[]")
        )
        batch.add_column(
            sa.Column("starring", sa.JSON(), nullable=False, server_default="[]")
        )
        batch.add_column(
            sa.Column("written_by", sa.JSON(), nullable=False, server_default="[]")
        )

    with op.batch_alter_table("movie_extras") as batch:
        batch.add_column(
            sa.Column("available_for", sa.JSON(), nullable=False, server_default="[]")
        )


def _remove_movie_page_metadata() -> None:
    with op.batch_alter_table("movie_extras") as batch:
        batch.drop_column("available_for")

    with op.batch_alter_table("movies") as batch:
        batch.drop_column("written_by")
        batch.drop_column("starring")
        batch.drop_column("shop_items")
        batch.drop_column("production_companies")
        batch.drop_column("more_like_this")
        batch.drop_column("hosts")
        batch.drop_column("genres")
        batch.drop_column("directed_by")
        batch.drop_column("cast_and_crew")
        batch.drop_column("images")
        batch.drop_column("origin_country")
        batch.drop_column("language")
        batch.drop_column("byline")
        batch.drop_column("background")
        batch.drop_column("published_at")
        batch.drop_column("status")
        batch.drop_column("has_video")


def _scope_movie_extra_identity() -> None:
    with op.batch_alter_table("movie_extras") as batch:
        batch.drop_index("ix_movie_extras_dw_id")
        batch.drop_index("ix_movie_extras_slug")
        batch.create_index("ix_movie_extras_dw_id", ["dw_id"], unique=False)
        batch.create_index("ix_movie_extras_slug", ["slug"], unique=False)
        batch.create_unique_constraint(
            "uq_movie_extras_movie_id_dw_id",
            ["movie_id", "dw_id"],
        )
        batch.create_unique_constraint(
            "uq_movie_extras_movie_id_slug",
            ["movie_id", "slug"],
        )


def _restore_global_movie_extra_identity() -> None:
    bind = op.get_bind()
    duplicate_dw_id = bind.execute(
        sa.text(
            "SELECT dw_id FROM movie_extras "
            "WHERE dw_id IS NOT NULL "
            "GROUP BY dw_id HAVING COUNT(*) > 1 LIMIT 1"
        )
    ).scalar_one_or_none()
    duplicate_slug = bind.execute(
        sa.text(
            "SELECT slug FROM movie_extras "
            "GROUP BY slug HAVING COUNT(*) > 1 LIMIT 1"
        )
    ).scalar_one_or_none()
    if duplicate_dw_id is not None or duplicate_slug is not None:
        raise RuntimeError(
            "Cannot downgrade movie-extra identity constraints because Daily Wire "
            "clips are currently shared by multiple movies. The older schema "
            "requires globally unique movie-extra IDs and slugs."
        )

    with op.batch_alter_table("movie_extras") as batch:
        batch.drop_constraint("uq_movie_extras_movie_id_slug", type_="unique")
        batch.drop_constraint("uq_movie_extras_movie_id_dw_id", type_="unique")
        batch.drop_index("ix_movie_extras_slug")
        batch.drop_index("ix_movie_extras_dw_id")
        batch.create_index("ix_movie_extras_dw_id", ["dw_id"], unique=True)
        batch.create_index("ix_movie_extras_slug", ["slug"], unique=True)


def _official_trailer_links(bind) -> list[tuple[int, int]]:
    """Snapshot links SQLite may null while batch-rebuilding movie extras."""
    return [
        (int(row.id), int(row.official_trailer_id))
        for row in bind.execute(
            sa.text(
                "SELECT id, official_trailer_id FROM movies "
                "WHERE official_trailer_id IS NOT NULL"
            )
        )
    ]


def _restore_official_trailer_links(
    bind,
    links: list[tuple[int, int]],
) -> None:
    for movie_id, movie_extra_id in links:
        bind.execute(
            sa.text(
                "UPDATE movies SET official_trailer_id = :movie_extra_id "
                "WHERE id = :movie_id"
            ),
            {"movie_id": movie_id, "movie_extra_id": movie_extra_id},
        )


def _as_list(value) -> list[str]:
    if isinstance(value, list):
        return list(value)
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except (TypeError, ValueError):
            return []
        return list(decoded) if isinstance(decoded, list) else []
    return []


def _drop_dailywire_ids(bind) -> None:
    duplicate_movie_slug = bind.execute(
        sa.text("SELECT slug FROM movies GROUP BY slug HAVING COUNT(*) > 1 LIMIT 1")
    ).scalar_one_or_none()
    if duplicate_movie_slug is not None:
        raise RuntimeError(
            "Cannot make movie slugs the canonical identity because duplicate "
            f"movie slug {duplicate_movie_slug!r} already exists"
        )

    bind.execute(
        sa.text(
            "UPDATE movies SET release_date_source_id = NULL "
            "WHERE release_date_source = 'dailywire'"
        )
    )

    official_trailer_links = _official_trailer_links(bind)
    with op.batch_alter_table("movie_extras") as batch:
        batch.drop_constraint("uq_movie_extras_movie_id_dw_id", type_="unique")
        batch.drop_index("ix_movie_extras_dw_id")
        batch.drop_column("dw_id")

    with op.batch_alter_table("movies") as batch:
        batch.drop_index("ix_movies_dw_id")
        batch.drop_column("dw_id")
        batch.create_index("ix_movies_slug", ["slug"], unique=True)
    _restore_official_trailer_links(bind, official_trailer_links)


def _restore_dailywire_id_columns(bind) -> None:
    official_trailer_links = _official_trailer_links(bind)
    with op.batch_alter_table("movies") as batch:
        batch.drop_index("ix_movies_slug")
        batch.add_column(sa.Column("dw_id", sa.String(), nullable=True))
        batch.create_index("ix_movies_dw_id", ["dw_id"], unique=True)

    with op.batch_alter_table("movie_extras") as batch:
        batch.add_column(sa.Column("dw_id", sa.String(), nullable=True))
        batch.create_index("ix_movie_extras_dw_id", ["dw_id"], unique=False)
        batch.create_unique_constraint(
            "uq_movie_extras_movie_id_dw_id",
            ["movie_id", "dw_id"],
        )
    _restore_official_trailer_links(bind, official_trailer_links)


def _normalize_movie_extra_sources(bind) -> None:
    official_trailer_links = _official_trailer_links(bind)

    op.create_table(
        "movie_extra_sources",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("slug", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_movie_extra_sources")),
        sa.UniqueConstraint("slug", name="uq_movie_extra_sources_slug"),
    )
    bind.execute(
        sa.text(
            "INSERT INTO movie_extra_sources (slug) "
            "SELECT DISTINCT slug FROM movie_extras"
        )
    )

    with op.batch_alter_table("movie_extras") as batch:
        batch.add_column(sa.Column("source_id", sa.Integer(), nullable=True))

    bind.execute(
        sa.text(
            "UPDATE movie_extras SET source_id = ("
            "SELECT movie_extra_sources.id FROM movie_extra_sources "
            "WHERE movie_extra_sources.slug = movie_extras.slug"
            ")"
        )
    )
    unresolved = bind.execute(
        sa.text("SELECT COUNT(*) FROM movie_extras WHERE source_id IS NULL")
    ).scalar_one()
    if unresolved:
        raise RuntimeError(
            "Could not resolve every existing movie extra to its immutable slug source"
        )

    with op.batch_alter_table("movie_extras") as batch:
        batch.drop_constraint("uq_movie_extras_movie_id_slug", type_="unique")
        batch.drop_index("ix_movie_extras_slug")
        batch.create_index("ix_movie_extras_source_id", ["source_id"], unique=False)
        batch.create_unique_constraint(
            "uq_movie_extras_movie_id_source_id",
            ["movie_id", "source_id"],
        )
        batch.create_foreign_key(
            "fk_movie_extras_source_id_movie_extra_sources",
            "movie_extra_sources",
            ["source_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch.alter_column(
            "source_id",
            existing_type=sa.Integer(),
            nullable=False,
        )
        batch.drop_column("slug")

    _restore_official_trailer_links(bind, official_trailer_links)


def _denormalize_movie_extra_sources(bind) -> None:
    official_trailer_links = _official_trailer_links(bind)

    with op.batch_alter_table("movie_extras") as batch:
        batch.add_column(sa.Column("slug", sa.String(), nullable=True))

    bind.execute(
        sa.text(
            "UPDATE movie_extras SET slug = ("
            "SELECT movie_extra_sources.slug FROM movie_extra_sources "
            "WHERE movie_extra_sources.id = movie_extras.source_id"
            ")"
        )
    )
    unresolved = bind.execute(
        sa.text("SELECT COUNT(*) FROM movie_extras WHERE slug IS NULL")
    ).scalar_one()
    if unresolved:
        raise RuntimeError(
            "Cannot downgrade movie-extra sources because one or more source slugs are missing"
        )

    with op.batch_alter_table("movie_extras") as batch:
        batch.alter_column(
            "slug",
            existing_type=sa.String(),
            nullable=False,
        )
        batch.drop_constraint(
            "fk_movie_extras_source_id_movie_extra_sources",
            type_="foreignkey",
        )
        batch.drop_constraint(
            "uq_movie_extras_movie_id_source_id",
            type_="unique",
        )
        batch.drop_index("ix_movie_extras_source_id")
        batch.drop_column("source_id")
        batch.create_index("ix_movie_extras_slug", ["slug"], unique=False)
        batch.create_unique_constraint(
            "uq_movie_extras_movie_id_slug",
            ["movie_id", "slug"],
        )

    _restore_official_trailer_links(bind, official_trailer_links)
    op.drop_table("movie_extra_sources")


def _add_source_metadata_columns() -> None:
    op.add_column(
        "movie_extra_sources",
        sa.Column("title", sa.String(), nullable=False, server_default=""),
    )
    op.add_column(
        "movie_extra_sources",
        sa.Column("description", sa.String(), nullable=True),
    )
    op.add_column(
        "movie_extra_sources",
        sa.Column("duration", sa.Float(), nullable=False, server_default="0"),
    )
    op.add_column(
        "movie_extra_sources",
        sa.Column("background_image_path", sa.String(), nullable=True),
    )
    op.add_column(
        "movie_extra_sources",
        sa.Column("thumbnail_landscape_path", sa.String(), nullable=True),
    )
    op.add_column(
        "movie_extra_sources",
        sa.Column("thumbnail_portrait_path", sa.String(), nullable=True),
    )
    op.add_column(
        "movie_extra_sources",
        sa.Column("thumbnail_square_path", sa.String(), nullable=True),
    )
    op.add_column(
        "movie_extra_sources",
        sa.Column("sharing_url", sa.String(), nullable=True),
    )
    op.add_column(
        "movie_extra_sources",
        sa.Column("published_date", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "movie_extra_sources",
        sa.Column("available_for", sa.JSON(), nullable=False, server_default="[]"),
    )


def _backfill_source_metadata(bind) -> None:
    metadata = sa.MetaData()
    sources = sa.Table("movie_extra_sources", metadata, autoload_with=bind)
    extras = sa.Table("movie_extras", metadata, autoload_with=bind)
    media_items = sa.Table("media_items", metadata, autoload_with=bind)

    merged: dict[int, dict] = {
        int(row.id): {
            "slug": row.slug,
            "title": "",
            "description": None,
            "duration": 0.0,
            "background_image_path": None,
            "thumbnail_landscape_path": None,
            "thumbnail_portrait_path": None,
            "thumbnail_square_path": None,
            "sharing_url": None,
            "published_date": None,
            "available_for": [],
        }
        for row in bind.execute(sa.select(sources.c.id, sources.c.slug))
    }

    rows = bind.execute(
        sa.select(
            extras.c.source_id,
            extras.c.id.label("placement_id"),
            media_items.c.updated_at,
            media_items.c.title,
            media_items.c.description,
            media_items.c.duration,
            media_items.c.background_image_path,
            media_items.c.thumbnail_landscape_path,
            media_items.c.thumbnail_portrait_path,
            media_items.c.thumbnail_square_path,
            extras.c.sharing_url,
            extras.c.published_date,
            extras.c.available_for,
        )
        .select_from(extras.join(media_items, media_items.c.id == extras.c.id))
        .order_by(
            extras.c.source_id,
            media_items.c.updated_at.desc(),
            extras.c.id.desc(),
        )
    ).mappings()

    for row in rows:
        values = merged[int(row["source_id"])]
        if not values["title"] and row["title"]:
            values["title"] = row["title"]
        if values["description"] is None and row["description"] is not None:
            values["description"] = row["description"]
        if values["duration"] <= 0 and row["duration"] and row["duration"] > 0:
            values["duration"] = float(row["duration"])
        for field in (
            "background_image_path",
            "thumbnail_landscape_path",
            "thumbnail_portrait_path",
            "thumbnail_square_path",
            "sharing_url",
            "published_date",
        ):
            if values[field] is None and row[field] is not None:
                values[field] = row[field]
        if not values["available_for"]:
            values["available_for"] = _as_list(row["available_for"])

    for source_id, values in merged.items():
        values["title"] = values["title"] or values.pop("slug")
        bind.execute(
            sa.update(sources)
            .where(sources.c.id == source_id)
            .values(**{field: values[field] for field in _SOURCE_FIELDS})
        )

    bind.execute(
        sa.update(media_items)
        .where(media_items.c.type == "movie_extra")
        .values(
            title="",
            description=None,
            duration=0.0,
            background_image_path=None,
            thumbnail_landscape_path=None,
            thumbnail_portrait_path=None,
            thumbnail_square_path=None,
        )
    )


def _move_movie_extra_metadata_to_sources(bind) -> None:
    _add_source_metadata_columns()
    _backfill_source_metadata(bind)

    official_trailer_links = _official_trailer_links(bind)
    with op.batch_alter_table("movie_extras") as batch:
        batch.drop_column("available_for")
        batch.drop_column("published_date")
        batch.drop_column("sharing_url")
    _restore_official_trailer_links(bind, official_trailer_links)


def _restore_movie_extra_metadata_to_placements(bind) -> None:
    op.add_column(
        "movie_extras",
        sa.Column("sharing_url", sa.String(), nullable=True),
    )
    op.add_column(
        "movie_extras",
        sa.Column("published_date", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "movie_extras",
        sa.Column("available_for", sa.JSON(), nullable=False, server_default="[]"),
    )

    metadata = sa.MetaData()
    sources = sa.Table("movie_extra_sources", metadata, autoload_with=bind)
    extras = sa.Table("movie_extras", metadata, autoload_with=bind)
    media_items = sa.Table("media_items", metadata, autoload_with=bind)

    rows = bind.execute(
        sa.select(
            extras.c.id.label("placement_id"),
            sources.c.title,
            sources.c.description,
            sources.c.duration,
            sources.c.background_image_path,
            sources.c.thumbnail_landscape_path,
            sources.c.thumbnail_portrait_path,
            sources.c.thumbnail_square_path,
            sources.c.sharing_url,
            sources.c.published_date,
            sources.c.available_for,
        ).select_from(extras.join(sources, sources.c.id == extras.c.source_id))
    ).mappings()

    for row in rows:
        placement_id = int(row["placement_id"])
        bind.execute(
            sa.update(media_items)
            .where(media_items.c.id == placement_id)
            .values(
                title=row["title"],
                description=row["description"],
                duration=row["duration"],
                background_image_path=row["background_image_path"],
                thumbnail_landscape_path=row["thumbnail_landscape_path"],
                thumbnail_portrait_path=row["thumbnail_portrait_path"],
                thumbnail_square_path=row["thumbnail_square_path"],
            )
        )
        bind.execute(
            sa.update(extras)
            .where(extras.c.id == placement_id)
            .values(
                sharing_url=row["sharing_url"],
                published_date=row["published_date"],
                available_for=_as_list(row["available_for"]),
            )
        )

    for column in reversed(_SOURCE_FIELDS):
        op.drop_column("movie_extra_sources", column)


def _add_content_columns(table_name: str) -> None:
    op.add_column(
        table_name,
        sa.Column("title", sa.String(), nullable=False, server_default=""),
    )
    op.add_column(
        table_name,
        sa.Column("description", sa.String(), nullable=True),
    )
    op.add_column(
        table_name,
        sa.Column("duration", sa.Float(), nullable=False, server_default="0"),
    )
    op.add_column(
        table_name,
        sa.Column("background_image_path", sa.String(), nullable=True),
    )
    op.add_column(
        table_name,
        sa.Column("thumbnail_landscape_path", sa.String(), nullable=True),
    )
    op.add_column(
        table_name,
        sa.Column("thumbnail_portrait_path", sa.String(), nullable=True),
    )
    op.add_column(
        table_name,
        sa.Column("thumbnail_square_path", sa.String(), nullable=True),
    )


def _copy_content_metadata(
    bind,
    *,
    source_table_name: str,
    target_table_name: str,
) -> None:
    metadata = sa.MetaData()
    source = sa.Table(source_table_name, metadata, autoload_with=bind)
    target = sa.Table(target_table_name, metadata, autoload_with=bind)

    values = {
        field: (
            sa.select(source.c[field])
            .where(source.c.id == target.c.id)
            .scalar_subquery()
        )
        for field in _CONTENT_FIELDS
    }
    bind.execute(sa.update(target).values(**values))


def _move_content_metadata_to_owners(bind) -> None:
    _add_content_columns("episodes")
    _add_content_columns("movies")
    _copy_content_metadata(
        bind,
        source_table_name="media_items",
        target_table_name="episodes",
    )
    _copy_content_metadata(
        bind,
        source_table_name="media_items",
        target_table_name="movies",
    )

    for field in reversed(_CONTENT_FIELDS):
        op.drop_column("media_items", field)


def _restore_content_metadata_to_media_items(bind) -> None:
    _add_content_columns("media_items")

    metadata = sa.MetaData()
    media_items = sa.Table("media_items", metadata, autoload_with=bind)
    episodes = sa.Table("episodes", metadata, autoload_with=bind)
    movies = sa.Table("movies", metadata, autoload_with=bind)

    for concrete in (episodes, movies):
        bind.execute(
            sa.update(media_items)
            .where(media_items.c.id.in_(sa.select(concrete.c.id)))
            .values(
                **{
                    field: (
                        sa.select(concrete.c[field])
                        .where(concrete.c.id == media_items.c.id)
                        .scalar_subquery()
                    )
                    for field in _CONTENT_FIELDS
                }
            )
        )

    bind.execute(
        sa.update(media_items)
        .where(media_items.c.type == "movie_extra")
        .values(
            title="",
            description=None,
            duration=0.0,
            background_image_path=None,
            thumbnail_landscape_path=None,
            thumbnail_portrait_path=None,
            thumbnail_square_path=None,
        )
    )

    for field in reversed(_CONTENT_FIELDS):
        op.drop_column("movies", field)
        op.drop_column("episodes", field)


def _remove_promotional_movie_metadata() -> None:
    op.drop_column("movies", "shop_items")
    op.drop_column("movies", "more_like_this")


def _restore_promotional_movie_metadata() -> None:
    op.add_column(
        "movies",
        sa.Column("more_like_this", sa.JSON(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "movies",
        sa.Column("shop_items", sa.JSON(), nullable=False, server_default="[]"),
    )


def _rename_media_item_tables(bind) -> None:
    op.rename_table("episodes", "media_items_episodes")
    op.rename_table("movie_extras", "media_items_movie_extras")
    op.rename_table("movies", "media_items_movies")
    bind.execute(
        sa.text(
            "UPDATE metadata SET parent_table = 'media_items_episodes' "
            "WHERE parent_table = 'episodes'"
        )
    )


def _restore_legacy_media_item_table_names(bind) -> None:
    bind.execute(
        sa.text(
            "UPDATE metadata SET parent_table = 'episodes' "
            "WHERE parent_table = 'media_items_episodes'"
        )
    )
    op.rename_table("media_items_movie_extras", "movie_extras")
    op.rename_table("media_items_movies", "movies")
    op.rename_table("media_items_episodes", "episodes")


def _rename_series_profile_fk_column(old_name: str, new_name: str) -> None:
    bind = op.get_bind()
    columns = _column_names(bind, "download_profile_series_seasons")

    if new_name in columns:
        if old_name in columns:
            raise RuntimeError(
                "download_profile_series_seasons contains both the old and new "
                "series-profile foreign-key columns"
            )
        return
    if old_name not in columns:
        raise RuntimeError(
            "download_profile_series_seasons contains neither expected "
            f"series-profile foreign-key column ({old_name!r}, {new_name!r})"
        )

    with op.batch_alter_table("download_profile_series_seasons") as batch_op:
        batch_op.alter_column(
            old_name,
            new_column_name=new_name,
            existing_type=sa.Integer(),
            existing_nullable=True,
        )


def _rename_table_if_needed(bind, old_name: str, new_name: str) -> None:
    tables = set(sa.inspect(bind).get_table_names())
    old_exists = old_name in tables
    new_exists = new_name in tables

    if new_exists and not old_exists:
        return
    if old_exists and not new_exists:
        op.rename_table(old_name, new_name)
        return
    if old_exists and new_exists:
        raise RuntimeError(
            f"Cannot resume migration because both {old_name!r} and {new_name!r} exist"
        )
    raise RuntimeError(
        f"Cannot resume migration because neither {old_name!r} nor {new_name!r} exists"
    )


def _drop_column_if_present(bind, table_name: str, column_name: str) -> None:
    if column_name in _column_names(bind, table_name):
        op.drop_column(table_name, column_name)


def _add_column_if_missing(bind, table_name: str, column: sa.Column) -> None:
    if column.name not in _column_names(bind, table_name):
        op.add_column(table_name, column)


def _episode_table_name(bind) -> str:
    tables = set(sa.inspect(bind).get_table_names())
    old_exists = "media_items_episodes" in tables
    new_exists = "media_items_episode" in tables

    if old_exists == new_exists:
        raise RuntimeError(
            "Expected exactly one of 'media_items_episodes' or 'media_items_episode'"
        )
    return "media_items_episodes" if old_exists else "media_items_episode"


def _finalize_media_item_schema(bind) -> None:
    _add_column_if_missing(
        bind,
        SETTINGS_VERSION_TABLE,
        sa.Column(SETTINGS_VERSION_COLUMN, sa.String(length=32), nullable=True),
    )

    _rename_series_profile_fk_column(
        "series_download_profile_id",
        "download_profiles_series_id",
    )

    _drop_column_if_present(bind, "media_items", "downloaded_date")
    _drop_column_if_present(bind, _episode_table_name(bind), "redownloaded_date")

    _rename_table_if_needed(bind, "media_items_episodes", "media_items_episode")
    _rename_table_if_needed(bind, "media_items_movie_extras", "media_items_movie_extra")
    _rename_table_if_needed(bind, "media_items_movies", "media_items_movie")

    bind.execute(
        sa.text(
            "UPDATE metadata SET parent_table = 'media_items_episode' "
            "WHERE parent_table = 'media_items_episodes'"
        )
    )


def _restore_pre_refactor_media_item_schema(bind) -> None:
    bind.execute(
        sa.text(
            "UPDATE metadata SET parent_table = 'media_items_episodes' "
            "WHERE parent_table = 'media_items_episode'"
        )
    )

    _rename_table_if_needed(
        bind,
        "media_items_movie_extra",
        "media_items_movie_extras",
    )
    _rename_table_if_needed(bind, "media_items_movie", "media_items_movies")
    _rename_table_if_needed(bind, "media_items_episode", "media_items_episodes")

    _add_column_if_missing(
        bind,
        "media_items_episodes",
        sa.Column("redownloaded_date", sa.DateTime(), nullable=True),
    )
    _add_column_if_missing(
        bind,
        "media_items",
        sa.Column("downloaded_date", sa.DateTime(), nullable=True),
    )

    _rename_series_profile_fk_column(
        "download_profiles_series_id",
        "series_download_profile_id",
    )


def _repair_movie_extra_classifications(bind) -> None:
    bind.execute(
        sa.text(
            """
            UPDATE media_items_movie_extra
            SET movie_extra_type = 'trailer'
            WHERE id IN (
                SELECT official_trailer_id
                FROM media_items_movie
                WHERE official_trailer_id IS NOT NULL
            )
            """
        )
    )


def _upgrade_media_database_refactor() -> None:
    bind = op.get_bind()
    _add_movie_page_metadata()
    _scope_movie_extra_identity()
    _drop_dailywire_ids(bind)
    _normalize_movie_extra_sources(bind)
    _move_movie_extra_metadata_to_sources(bind)
    _move_content_metadata_to_owners(bind)
    _remove_promotional_movie_metadata()
    _rename_media_item_tables(bind)
    _finalize_media_item_schema(bind)
    _repair_movie_extra_classifications(bind)
    _handoff_version_storage(bind)


def _downgrade_media_database_refactor() -> None:
    bind = op.get_bind()
    _restore_pre_refactor_media_item_schema(bind)
    _restore_legacy_media_item_table_names(bind)
    _restore_promotional_movie_metadata()
    _restore_content_metadata_to_media_items(bind)
    _restore_movie_extra_metadata_to_placements(bind)
    _denormalize_movie_extra_sources(bind)
    _restore_dailywire_id_columns(bind)
    _restore_global_movie_extra_identity()
    _remove_movie_page_metadata()


# Season slug scope ---------------------------------------------------------


def _upgrade_season_slug_scope() -> None:
    with op.batch_alter_table("seasons") as batch:
        batch.drop_index("ix_seasons_slug")
        batch.create_index("ix_seasons_slug", ["slug"], unique=False)
        batch.create_unique_constraint(
            "uq_season_show_slug",
            ["show_id", "slug"],
        )


def _downgrade_season_slug_scope() -> None:
    duplicate = op.get_bind().execute(
        sa.text(
            "SELECT slug, COUNT(*) AS season_count "
            "FROM seasons "
            "GROUP BY slug "
            "HAVING COUNT(*) > 1 "
            "LIMIT 1"
        )
    ).mappings().first()
    if duplicate is not None:
        raise RuntimeError(
            "Cannot restore globally unique season slugs while multiple shows use "
            f"season slug '{duplicate['slug']}' ({duplicate['season_count']} rows)."
        )

    with op.batch_alter_table("seasons") as batch:
        batch.drop_constraint("uq_season_show_slug", type_="unique")
        batch.drop_index("ix_seasons_slug")
        batch.create_index("ix_seasons_slug", ["slug"], unique=True)


# Local Media Profile download mode ----------------------------------------


def _upgrade_download_mode() -> None:
    with op.batch_alter_table("local_media_profiles") as batch:
        batch.add_column(
            sa.Column(
                "download_mode",
                sa.String(length=16),
                nullable=False,
                server_default="system",
            )
        )


def _downgrade_download_mode() -> None:
    with op.batch_alter_table("local_media_profiles") as batch:
        batch.drop_column("download_mode")


# Queued download priority --------------------------------------------------


def _upgrade_queued_download_priority() -> None:
    op.add_column(
        "task_operations",
        sa.Column("prioritized_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        op.f("ix_task_operations_prioritized_at"),
        "task_operations",
        ["prioritized_at"],
        unique=False,
    )


def _downgrade_queued_download_priority() -> None:
    op.drop_index(
        op.f("ix_task_operations_prioritized_at"),
        table_name="task_operations",
    )
    op.drop_column("task_operations", "prioritized_at")


# RSS video-method canonicalization ----------------------------------------


def _canonicalize_feed_url(feed_url: str) -> str:
    parts = urlsplit(feed_url)
    query = parse_qsl(parts.query, keep_blank_values=True)
    changed = False
    updated_query: list[tuple[str, str]] = []

    for key, value in query:
        if key == _DW_VIDEO_METHOD_QUERY_PARAMETER:
            canonical_value = _LEGACY_TO_CANONICAL_METHOD.get(value)
            if canonical_value is not None:
                value = canonical_value
                changed = True
        updated_query.append((key, value))

    if not changed:
        return feed_url

    return urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            parts.path,
            urlencode(updated_query),
            parts.fragment,
        )
    )


def _upgrade_rss_video_methods() -> None:
    connection = op.get_bind()
    profiles = connection.execute(
        sa.text("SELECT id, dw_video_method, feed_url FROM stream_profiles_rss")
    ).mappings().all()

    for profile in profiles:
        current_method = profile["dw_video_method"]
        canonical_method = _LEGACY_TO_CANONICAL_METHOD.get(
            current_method,
            current_method,
        )
        current_feed_url = profile["feed_url"]
        canonical_feed_url = _canonicalize_feed_url(current_feed_url)

        if (
            canonical_method == current_method
            and canonical_feed_url == current_feed_url
        ):
            continue

        connection.execute(
            sa.text(
                "UPDATE stream_profiles_rss "
                "SET dw_video_method = :dw_video_method, feed_url = :feed_url "
                "WHERE id = :id"
            ),
            {
                "id": profile["id"],
                "dw_video_method": canonical_method,
                "feed_url": canonical_feed_url,
            },
        )


def _downgrade_rss_video_methods() -> None:
    # Intentionally one-way: do not reintroduce retired identifiers.
    pass


# Podcast download starting date -------------------------------------------


def _upgrade_podcast_download_starting_from() -> None:
    with op.batch_alter_table("download_profiles_podcast") as batch:
        batch.add_column(sa.Column("download_starting_from", sa.Date(), nullable=True))


def _downgrade_podcast_download_starting_from() -> None:
    with op.batch_alter_table("download_profiles_podcast") as batch:
        batch.drop_column("download_starting_from")


# Release migration ---------------------------------------------------------


def upgrade() -> None:
    """Upgrade a shipped WireLoft 1.0 database directly to WireLoft 1.1."""
    _upgrade_task_operations()
    _upgrade_download_execution()

    # WireLoft 1.1 deliberately replaces the dedicated 1.0 attempt ledger with
    # TaskRun/TaskOperation history. Existing attempt rows are not migrated.
    _upgrade_drop_media_download_attempts()

    _upgrade_datetime_contract()
    _upgrade_episode_release_lifecycle()
    _upgrade_episode_lifecycle_metadata()
    _upgrade_show_local_media_profile_scope()
    _upgrade_artifact_identity()
    _upgrade_media_database_refactor()
    _upgrade_season_slug_scope()

    # download_mode changes execution behavior, not Local Media Profile identity.
    # Keep only the existing stricter uniqueness constraint on
    # (type, output_template, preferred_format); no redundant mode-aware index.
    _upgrade_download_mode()

    _upgrade_queued_download_priority()
    _upgrade_rss_video_methods()
    _upgrade_podcast_download_starting_from()


def downgrade() -> None:
    """Return the 1.1 application schema to the shipped WireLoft 1.0 schema."""
    _downgrade_podcast_download_starting_from()
    _downgrade_rss_video_methods()
    _downgrade_queued_download_priority()
    _downgrade_download_mode()
    _downgrade_season_slug_scope()
    _downgrade_media_database_refactor()
    _downgrade_artifact_identity()
    _downgrade_show_local_media_profile_scope()
    _downgrade_episode_lifecycle_metadata()
    _downgrade_episode_release_lifecycle()
    _downgrade_datetime_contract()

    # The 1.0 ledger table is recreated empty. Its historical rows were
    # intentionally discarded by the 1.1 upgrade.
    _downgrade_drop_media_download_attempts()
    _downgrade_download_execution()
    _downgrade_task_operations()

    # Version tracking intentionally remains in Settings after the one-time
    # handoff, matching current WireLoft's migration-runner contract.
