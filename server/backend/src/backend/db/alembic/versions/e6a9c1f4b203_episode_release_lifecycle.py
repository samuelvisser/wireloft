"""Harden episode release lifecycle and rename lifecycle tasks.

Revision ID: e6a9c1f4b203
Revises: b7e2c4d9a601
"""

from __future__ import annotations

from datetime import datetime, timezone
import re

from alembic import op
import sqlalchemy as sa


revision = "e6a9c1f4b203"
down_revision = "b7e2c4d9a601"
branch_labels = None
depends_on = None

_TASK_RENAMES = {
    "monitor_episode_worker": "monitor_pending_episode",
    "cleanup_episodes_stuck_without_media": "monitor_no_usable_media_episode",
    "refresh_episode_metadata_worker": "refresh_episode_metadata",
}
_NUMBERED_RE = re.compile(r"^ep\.(\d+)$")
_SEASONAL_RE = re.compile(r"^ep\.S(\d+)E(\d+)$")


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
        sa.text("SELECT value FROM metadata WHERE parent_table=:table AND parent_id=:parent_id AND key=:key"),
        {"table": parent_table, "parent_id": parent_id, "key": key},
    ).scalar_one_or_none()


def _set_meta(connection, parent_table: str, parent_id: int, key: str, value: str) -> None:
    existing = connection.execute(
        sa.text("SELECT id FROM metadata WHERE parent_table=:table AND parent_id=:parent_id AND key=:key"),
        {"table": parent_table, "parent_id": parent_id, "key": key},
    ).scalar_one_or_none()
    if existing is None:
        connection.execute(
            sa.text("INSERT INTO metadata (parent_table,parent_id,key,value) VALUES (:table,:parent_id,:key,:value)"),
            {"table": parent_table, "parent_id": parent_id, "key": key, "value": value},
        )
    else:
        connection.execute(sa.text("UPDATE metadata SET value=:value WHERE id=:id"), {"value": value, "id": existing})


def _remaining_identifiers(connection, show_id: int, exclude_id: int) -> list[str]:
    return [
        str(row[0]) for row in connection.execute(
            sa.text("SELECT episode_identifier FROM episodes WHERE show_id=:show_id AND id != :episode_id"),
            {"show_id": show_id, "episode_id": exclude_id},
        )
    ]


def _rollback_head_for_quarantine(connection, *, episode_id: int, show_id: int, previous: str, show_type: str, season_id: int) -> None:
    identifiers = _remaining_identifiers(connection, show_id, episode_id)
    if show_type == "numbered":
        match = _NUMBERED_RE.fullmatch(previous)
        if not match:
            return
        number = int(match.group(1))
        if int(_meta_value(connection, "shows", show_id, "ep_id.latest_ep_num") or 0) != number:
            return
        remaining = [int(m.group(1)) for value in identifiers if (m := _NUMBERED_RE.fullmatch(value))]
        new_head = max(remaining, default=0)
        _set_meta(connection, "shows", show_id, "ep_id.latest_ep_num", str(new_head))
        extra_re = re.compile(rf"^ep-extra\.{new_head}\.(\d+)$") if new_head else re.compile(r"a^")
        extras = [int(m.group(1)) for value in identifiers if (m := extra_re.fullmatch(value))]
        _set_meta(connection, "shows", show_id, "ep_id.latest_ep_extra_num", str(max(extras, default=0)))
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
        remaining = [int(m.group(1)) for value in identifiers if (m := main_re.fullmatch(value))]
        new_head = max(remaining, default=0)
        _set_meta(connection, "shows", show_id, key, str(new_head))
        extra_re = re.compile(rf"^ep-extra\.S{season_number:02d}E{new_head:02d}\.(\d+)$") if new_head else re.compile(r"a^")
        extras = [int(m.group(1)) for value in identifiers if (m := extra_re.fullmatch(value))]
        _set_meta(connection, "shows", show_id, "ep_id.latest_ep_extra_num", str(max(extras, default=0)))
        return

    if show_type == "date_based":
        published = _as_datetime(connection.execute(
            sa.text("SELECT published_date FROM episodes WHERE id=:episode_id"),
            {"episode_id": episode_id},
        ).scalar_one_or_none())
        if published is None:
            return
        timestamp = int(published.timestamp())
        if int(_meta_value(connection, "shows", show_id, "ep_id.latest_ep_date") or 0) != timestamp:
            return
        remaining_dates = [
            parsed
            for row in connection.execute(
                sa.text(
                    "SELECT published_date FROM episodes WHERE show_id=:show_id AND id != :episode_id "
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
    """Rename one task key while preserving history if both definitions exist.

    A database can already contain the new definition when code using the renamed
    worker was started before this Alembic revision was applied. In that case a
    direct UPDATE violates task_definitions.key's unique constraint. Preserve the
    older/source definition id, move all runs and schedules from the duplicate new
    row onto it, remove the duplicate, then apply the canonical key.
    """
    old_id = _task_definition_id(connection, old)
    new_id = _task_definition_id(connection, new)

    if old_id is not None:
        if new_id is not None and new_id != old_id:
            connection.execute(
                sa.text("UPDATE task_runs SET definition_id=:old_id WHERE definition_id=:new_id"),
                {"old_id": old_id, "new_id": new_id},
            )
            connection.execute(
                sa.text("UPDATE task_schedules SET definition_id=:old_id WHERE definition_id=:new_id"),
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
        sa.text("UPDATE task_operation_targets SET slot_key=REPLACE(slot_key,:old,:new) WHERE slot_key LIKE :pattern"),
        {"old": old, "new": new, "pattern": f"%{old}%"},
    )


def _quarantine_existing_no_usable_rows(connection) -> None:
    rows = list(connection.execute(sa.text(
        "SELECT e.id,e.show_id,e.season_id,e.episode_identifier,s.episode_identifier "
        "FROM episodes e JOIN shows s ON s.id=e.show_id "
        "WHERE e.publish_status='no_usable_media' AND e.episode_identifier NOT LIKE 'not-usable.%' "
        "ORDER BY e.show_id,e.id"
    )))
    counters: dict[int, int] = {}
    for episode_id, show_id, season_id, previous, show_type in rows:
        counter = counters.get(show_id)
        if counter is None:
            counter = int(_meta_value(connection, "shows", show_id, "ep_id.latest_not_usable_num") or 0)
        counter += 1
        counters[show_id] = counter
        _set_meta(connection, "episodes", episode_id, "no_usable_media.previous_identifier", str(previous))
        connection.execute(
            sa.text("UPDATE episodes SET episode_identifier=:identifier WHERE id=:episode_id"),
            {"identifier": f"not-usable.{counter}", "episode_id": episode_id},
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
        _set_meta(connection, "shows", show_id, "ep_id.latest_not_usable_num", str(counter))


def upgrade() -> None:
    connection = op.get_bind()
    for old, new in _TASK_RENAMES.items():
        _migrate_task_key(connection, old, new)
    _quarantine_existing_no_usable_rows(connection)
    with op.batch_alter_table("episodes") as batch:
        batch.drop_column("is_no_show_today")


def downgrade() -> None:
    connection = op.get_bind()
    with op.batch_alter_table("episodes") as batch:
        batch.add_column(sa.Column("is_no_show_today", sa.Boolean(), nullable=True))
    connection.execute(sa.text(
        "UPDATE episodes SET is_no_show_today = CASE WHEN lower(slug) LIKE '%no-show-today%' THEN 1 ELSE 0 END"
    ))
    for old, new in _TASK_RENAMES.items():
        _migrate_task_key(connection, new, old)
