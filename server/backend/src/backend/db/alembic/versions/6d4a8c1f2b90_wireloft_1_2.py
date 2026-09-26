"""Upgrade the shipped WireLoft 1.1 schema to WireLoft 1.2.

Revision ID: 6d4a8c1f2b90
Revises: d8b4a1f6c203
Create Date: 2026-09-26

This is the single release migration from the schema shipped in WireLoft 1.1
to WireLoft 1.2. Schema and local-data changes developed for 1.2 are
consolidated here so transient prerelease revisions do not become part of the
permanent migration history.
"""
from __future__ import annotations

from collections import defaultdict
import json
import re
from typing import Any, Mapping
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from alembic import op
import sqlalchemy as sa


revision = "6d4a8c1f2b90"
down_revision = "d8b4a1f6c203"
branch_labels = None
depends_on = None


def _upgrade_media_thumbnails() -> None:
    with op.batch_alter_table("local_media_profiles") as batch_op:
        batch_op.add_column(
            sa.Column(
                "thumbnail_mode",
                sa.String(length=24),
                nullable=False,
                server_default="system",
            )
        )

    with op.batch_alter_table("media_downloads") as batch_op:
        batch_op.add_column(sa.Column("thumbnail_path", sa.String(), nullable=True))


def _downgrade_media_thumbnails() -> None:
    with op.batch_alter_table("media_downloads") as batch_op:
        batch_op.drop_column("thumbnail_path")

    with op.batch_alter_table("local_media_profiles") as batch_op:
        batch_op.drop_column("thumbnail_mode")


# -------------------------------------------------------------------------

# HasTaskResourcesMixin owns these polymorphic resource keys. They cannot use a
# normal database foreign key because one resource_id column points at multiple
# domain tables, so legacy cleanup must mirror that ownership explicitly.
_TASK_RESOURCE_TABLES = {
    "show": "shows",
    "season": "seasons",
    "episode": "media_items_episode",
    "movie": "media_items_movie",
    "movie_extra": "media_items_movie_extra",
    "media_download": "media_downloads",
    "download_profile": "download_profiles",
    "download_profile_series": "download_profiles",
}


def _delete_broken_scheduler_foreign_keys(connection) -> None:
    # Historical SQLite connections did not enable foreign-key enforcement, so
    # rows that should have been removed by ON DELETE CASCADE can survive their
    # parent operation/run/target. Remove the deepest link rows first.
    connection.execute(sa.text("""
        DELETE FROM task_operation_runs
        WHERE NOT EXISTS (
            SELECT 1
            FROM task_operation_targets
            WHERE task_operation_targets.id = task_operation_runs.target_id
        )
        OR NOT EXISTS (
            SELECT 1
            FROM task_runs
            WHERE task_runs.id = task_operation_runs.task_run_id
        )
        OR NOT EXISTS (
            SELECT 1
            FROM task_operations
            WHERE task_operations.id = task_operation_runs.operation_id
        )
    """))
    connection.execute(sa.text("""
        DELETE FROM task_operation_targets
        WHERE NOT EXISTS (
            SELECT 1
            FROM task_operations
            WHERE task_operations.id = task_operation_targets.operation_id
        )
    """))


def _missing_resource_query(*, scheduler_table: str, resource_key: str, resource_table: str) -> str:
    return f"""
        SELECT id
        FROM {scheduler_table}
        WHERE lower(resource_type) = '{resource_key}'
          AND resource_id IS NOT NULL
          AND NOT EXISTS (
              SELECT 1
              FROM {resource_table}
              WHERE {resource_table}.id = {scheduler_table}.resource_id
          )
    """


def _delete_orphaned_polymorphic_resources(connection) -> None:
    # HasTaskResourcesMixin says scheduler history belongs to the resource and is
    # deleted with it. Clean rows left by pre-enforcement/legacy delete paths so
    # recycled integer ids cannot inherit another resource's old task history.
    for resource_key, resource_table in _TASK_RESOURCE_TABLES.items():
        stale_targets = _missing_resource_query(
            scheduler_table="task_operation_targets",
            resource_key=resource_key,
            resource_table=resource_table,
        )
        connection.execute(sa.text(f"""
            DELETE FROM task_operation_runs
            WHERE target_id IN ({stale_targets})
        """))
        connection.execute(sa.text(f"""
            DELETE FROM task_operation_targets
            WHERE id IN ({stale_targets})
        """))

        stale_runs = _missing_resource_query(
            scheduler_table="task_runs",
            resource_key=resource_key,
            resource_table=resource_table,
        )
        connection.execute(sa.text(f"""
            DELETE FROM task_operation_runs
            WHERE task_run_id IN ({stale_runs})
        """))
        connection.execute(sa.text(f"""
            DELETE FROM task_runs
            WHERE id IN ({stale_runs})
        """))

        stale_operations = _missing_resource_query(
            scheduler_table="task_operations",
            resource_key=resource_key,
            resource_table=resource_table,
        )
        connection.execute(sa.text(f"""
            DELETE FROM task_operation_runs
            WHERE operation_id IN ({stale_operations})
        """))
        connection.execute(sa.text(f"""
            DELETE FROM task_operation_targets
            WHERE operation_id IN ({stale_operations})
        """))
        connection.execute(sa.text(f"""
            DELETE FROM task_operations
            WHERE id IN ({stale_operations})
        """))

        connection.execute(sa.text(f"""
            DELETE FROM task_schedules
            WHERE lower(resource_type) = '{resource_key}'
              AND resource_id IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1
                  FROM {resource_table}
                  WHERE {resource_table}.id = task_schedules.resource_id
              )
        """))


def _delete_orphaned_media_download_subtypes(connection) -> None:
    for table_name in (
        "media_downloads_episode",
        "media_downloads_movie",
        "media_downloads_movie_extra",
    ):
        connection.execute(sa.text(f"""
            DELETE FROM {table_name}
            WHERE NOT EXISTS (
                SELECT 1
                FROM media_downloads
                WHERE media_downloads.id = {table_name}.id
            )
        """))


def _upgrade_sqlite_foreign_key_integrity() -> None:
    connection = op.get_bind()
    if connection.dialect.name != "sqlite":
        return

    _delete_broken_scheduler_foreign_keys(connection)
    _delete_orphaned_polymorphic_resources(connection)
    _delete_orphaned_media_download_subtypes(connection)


def _downgrade_sqlite_foreign_key_integrity() -> None:
    # Deleted rows had no owning parent and cannot be reconstructed safely.
    pass


# -------------------------------------------------------------------------

_END_RAW_RE = re.compile(r"{%[-]?\s*endraw\s*[-]?%}")


def _statement_keyword(source: str) -> str:
    body = source[2:-2] if source.startswith("{%") and source.endswith("%}") else source
    match = re.match(r"\s*-?\s*([A-Za-z_][A-Za-z0-9_]*)", body)
    return match.group(1) if match else ""


def _find_tag_end(source: str, start: int, end_delimiter: str) -> int:
    if end_delimiter == "#}":
        return source.find(end_delimiter, start + 2)

    quote: str | None = None
    escaped = False
    index = start + 2
    while index < len(source) - 1:
        character = source[index]
        if quote:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == quote:
                quote = None
            index += 1
            continue

        if character in {"'", '"'}:
            quote = character
            index += 1
            continue

        if source.startswith(end_delimiter, index):
            return index
        index += 1
    return -1


def _next_tag(source: str, cursor: int) -> tuple[int, str, str, str] | None:
    candidates = []
    for start_delimiter, end_delimiter, tag_type in (
        ("{{", "}}", "expression"),
        ("{%", "%}", "statement"),
        ("{#", "#}", "comment"),
    ):
        index = source.find(start_delimiter, cursor)
        if index >= 0:
            candidates.append((index, start_delimiter, end_delimiter, tag_type))
    return min(candidates, default=None, key=lambda candidate: candidate[0])


def _normalize_output_template_expression_spacing(output_template: str) -> str:
    pieces: list[str] = []
    cursor = 0
    raw = False

    while cursor < len(output_template):
        if raw:
            match = _END_RAW_RE.search(output_template, cursor)
            if not match:
                pieces.append(output_template[cursor:])
                break
            pieces.append(output_template[cursor:match.end()])
            cursor = match.end()
            raw = False
            continue

        next_tag = _next_tag(output_template, cursor)
        if next_tag is None:
            pieces.append(output_template[cursor:])
            break

        start, _start_delimiter, end_delimiter, tag_type = next_tag
        pieces.append(output_template[cursor:start])
        end = _find_tag_end(output_template, start, end_delimiter)
        if end < 0:
            pieces.append(output_template[start:])
            break

        token_end = end + len(end_delimiter)
        token = output_template[start:token_end]
        if tag_type == "expression" and not (token.startswith("{{-") or token.endswith("-}}")):
            body = token[2:-2].strip()
            pieces.append(f"{{{{ {body} }}}}" if body else token)
        else:
            pieces.append(token)

        if tag_type == "statement" and _statement_keyword(token) == "raw":
            raw = True
        cursor = token_end

    return "".join(pieces)


def _upgrade_output_template_spacing() -> None:
    bind = op.get_bind()
    profiles = sa.table(
        "local_media_profiles",
        sa.column("id", sa.Integer),
        sa.column("type", sa.String),
        sa.column("output_template", sa.String),
        sa.column("preferred_format", sa.String),
    )

    rows = list(bind.execute(sa.select(
        profiles.c.id,
        profiles.c.type,
        profiles.c.output_template,
        profiles.c.preferred_format,
    )).mappings())

    normalized_keys: dict[tuple[str, str, str], int] = {}
    updates: list[tuple[int, str]] = []
    for row in rows:
        normalized = _normalize_output_template_expression_spacing(row["output_template"])
        key = (row["type"], normalized, row["preferred_format"])
        existing_id = normalized_keys.get(key)
        if existing_id is not None and existing_id != row["id"]:
            raise RuntimeError(
                "Cannot normalize Local Media Profile output templates because profiles "
                f"{existing_id} and {row['id']} would become duplicates. Delete or change "
                "one of those profiles before upgrading."
            )
        normalized_keys[key] = row["id"]
        if normalized != row["output_template"]:
            updates.append((row["id"], normalized))

    for profile_id, normalized in updates:
        bind.execute(
            sa.update(profiles)
            .where(profiles.c.id == profile_id)
            .values(output_template=normalized)
        )


def _downgrade_output_template_spacing() -> None:
    # Spacing normalization is semantically neutral and intentionally retained.
    pass


# -------------------------------------------------------------------------

def _column_names(connection, table_name: str) -> set[str]:
    return {
        str(column["name"])
        for column in sa.inspect(connection).get_columns(table_name)
    }


def _upgrade_episode_indexing_schema() -> None:
    connection = op.get_bind()

    season_columns = _column_names(connection, "seasons")
    missing_season_columns = []
    if "season_type" not in season_columns:
        missing_season_columns.append(
            sa.Column(
                "season_type",
                sa.String(),
                nullable=False,
                server_default="normal",
            )
        )
    if "season_number" not in season_columns:
        missing_season_columns.append(
            sa.Column(
                "season_number",
                sa.Integer(),
                nullable=False,
                server_default="1",
            )
        )
    if missing_season_columns:
        with op.batch_alter_table("seasons") as batch_op:
            for column in missing_season_columns:
                batch_op.add_column(column)

    if "dw_episode_number" not in _column_names(connection, "media_items_episode"):
        with op.batch_alter_table("media_items_episode") as batch_op:
            batch_op.add_column(
                sa.Column("dw_episode_number", sa.String(), nullable=True)
            )


def _downgrade_episode_indexing_schema() -> None:
    connection = op.get_bind()

    if "dw_episode_number" in _column_names(connection, "media_items_episode"):
        with op.batch_alter_table("media_items_episode") as batch_op:
            batch_op.drop_column("dw_episode_number")

    season_columns = _column_names(connection, "seasons")
    if "season_number" in season_columns or "season_type" in season_columns:
        with op.batch_alter_table("seasons") as batch_op:
            if "season_number" in season_columns:
                batch_op.drop_column("season_number")
            if "season_type" in season_columns:
                batch_op.drop_column("season_type")


# -------------------------------------------------------------------------

def _upgrade_background_migration_version() -> None:
    with op.batch_alter_table("settings") as batch_op:
        batch_op.add_column(
            sa.Column(
                "background_migration_version",
                sa.String(length=32),
                nullable=True,
            )
        )


def _downgrade_background_migration_version() -> None:
    with op.batch_alter_table("settings") as batch_op:
        batch_op.drop_column("background_migration_version")


# -------------------------------------------------------------------------

_EXTRAS_RE = re.compile(r"\bextras?\b", re.IGNORECASE)
_OFFICIAL_TRAILER_RE = re.compile(r"\bofficial\s+trailer\b", re.IGNORECASE)
_GENERATED_RE = re.compile(r"^(aux|trailer)\.(\d+)$")
_NUMBERED_MAIN_RE = re.compile(r"^ep\.(\d+)$")
_LEGACY_NUMBERED_EXTRA_RE = re.compile(r"^ep-extra\.(\d+)\.(\d+)$")
_LEGACY_SEASONAL_MAIN_RE = re.compile(r"^ep\.S\d+E(\d+)$")
_LEGACY_SEASONAL_EXTRA_RE = re.compile(
    r"^ep-extra\.S\d+E(\d+)\.(\d+)$"
)
_CANONICAL_NUMBERED_EXTRA_RE = re.compile(
    r"^ep-extra\.(?:other|trailer)\.(\d+)\.(\d+)$"
)
_CANONICAL_SEASONAL_MAIN_RE = re.compile(r"^ep\.S\d+E(\d+)$")
_CANONICAL_SEASONAL_EXTRA_RE = re.compile(
    r"^ep-extra\.(?:other|trailer)\.S\d+E(\d+)\.(\d+)$"
)
_PREVIOUS_IDENTIFIER_KEY = "no_usable_media.previous_identifier"




def _season_type(name: str) -> str:
    return "extra" if _EXTRAS_RE.search(name or "") else "normal"


def _column_names(connection, table_name: str) -> set[str]:
    return {
        str(column["name"])
        for column in sa.inspect(connection).get_columns(table_name)
    }


def _generated_number(identifier: str, expected_type: str) -> int | None:
    match = _GENERATED_RE.fullmatch(identifier)
    if not match or match.group(1) != expected_type:
        return None
    return int(match.group(2))


def _set_show_meta(
    connection,
    metadata_table,
    show_id: int,
    key: str,
    value: int,
) -> None:
    row_id = connection.execute(
        sa.select(metadata_table.c.id).where(
            metadata_table.c.parent_table == "shows",
            metadata_table.c.parent_id == show_id,
            metadata_table.c.key == key,
        )
    ).scalar_one_or_none()
    if row_id is None:
        connection.execute(
            sa.insert(metadata_table).values(
                parent_table="shows",
                parent_id=show_id,
                key=key,
                value=str(value),
            )
        )
    else:
        connection.execute(
            sa.update(metadata_table)
            .where(metadata_table.c.id == row_id)
            .values(value=str(value))
        )


def _canonical_source_identifier(
    *,
    identifier_mode: str,
    season_type: str,
    season_number: int,
    title: str,
    identifier: str,
) -> tuple[str | None, str | None]:
    """Return a locally knowable canonical identifier and generated fallback type.

    API-derived episode numbers are intentionally not invented here. This migration
    only rewrites the legacy grammar and season numbering so current application
    code can safely read the database while the authoritative background migration
    refreshes The Daily Wire data.
    """
    official_trailer = bool(_OFFICIAL_TRAILER_RE.search(title or ""))

    generated = _GENERATED_RE.fullmatch(identifier)
    if generated:
        current_type = generated.group(1)
        if official_trailer and current_type == "aux":
            return None, "trailer"
        return identifier, None

    if season_type == "extra":
        return None, "trailer" if official_trailer else "aux"

    if identifier_mode == "date_based":
        if official_trailer:
            return None, "trailer"
        return identifier, None

    if identifier_mode == "numbered":
        if match := _NUMBERED_MAIN_RE.fullmatch(identifier):
            if official_trailer:
                return None, "trailer"
            return f"ep.{int(match.group(1))}", None
        if match := _LEGACY_NUMBERED_EXTRA_RE.fullmatch(identifier):
            extra_type = "trailer" if official_trailer else "other"
            return (
                f"ep-extra.{extra_type}.{int(match.group(1))}.{int(match.group(2))}",
                None,
            )
        if _CANONICAL_NUMBERED_EXTRA_RE.fullmatch(identifier):
            return identifier, None

    if identifier_mode == "seasonal":
        if match := _LEGACY_SEASONAL_MAIN_RE.fullmatch(identifier):
            if official_trailer:
                return None, "trailer"
            return f"ep.S{season_number:02d}E{int(match.group(1)):02d}", None
        if match := _LEGACY_SEASONAL_EXTRA_RE.fullmatch(identifier):
            extra_type = "trailer" if official_trailer else "other"
            return (
                f"ep-extra.{extra_type}.S{season_number:02d}E"
                f"{int(match.group(1)):02d}.{int(match.group(2))}",
                None,
            )
        if match := _CANONICAL_SEASONAL_EXTRA_RE.fullmatch(identifier):
            extra_type = "trailer" if ".trailer." in identifier else "other"
            return (
                f"ep-extra.{extra_type}.S{season_number:02d}E"
                f"{int(match.group(1)):02d}.{int(match.group(2))}",
                None,
            )

    return identifier, None


def _previous_identifier_rows(connection, metadata_table) -> dict[int, tuple[int, str]]:
    rows = connection.execute(
        sa.select(
            metadata_table.c.id,
            metadata_table.c.parent_id,
            metadata_table.c.value,
        ).where(
            metadata_table.c.parent_table == "media_items_episode",
            metadata_table.c.key == _PREVIOUS_IDENTIFIER_KEY,
        )
    ).mappings()
    return {
        int(row["parent_id"]): (int(row["id"]), str(row["value"]))
        for row in rows
    }


def _upgrade_episode_identifiers() -> None:
    connection = op.get_bind()

    metadata = sa.MetaData()
    shows = sa.Table("shows", metadata, autoload_with=connection)
    seasons = sa.Table("seasons", metadata, autoload_with=connection)
    episodes = sa.Table("media_items_episode", metadata, autoload_with=connection)
    metadata_table = sa.Table("metadata", metadata, autoload_with=connection)

    show_modes = {
        int(row["id"]): str(row["episode_identifier"])
        for row in connection.execute(
            sa.select(shows.c.id, shows.c.episode_identifier)
        ).mappings()
    }

    season_rows = connection.execute(
        sa.select(
            seasons.c.id,
            seasons.c.show_id,
            seasons.c.index,
            seasons.c.name,
        ).order_by(seasons.c.show_id, seasons.c.index)
    ).mappings().all()

    season_semantics: dict[int, tuple[str, int]] = {}
    seasons_by_show: dict[int, list] = defaultdict(list)
    for row in season_rows:
        seasons_by_show[int(row["show_id"])].append(row)

    for show_id, rows in seasons_by_show.items():
        normal_number = 0
        for row in rows:
            kind = _season_type(str(row["name"]))
            if kind == "normal":
                normal_number += 1
                number = normal_number
            else:
                number = 0
            season_semantics[int(row["id"])] = (kind, number)

    for season_id, (kind, number) in season_semantics.items():
        connection.execute(
            sa.update(seasons)
            .where(seasons.c.id == season_id)
            .values(season_type=kind, season_number=number)
        )

    episode_rows = connection.execute(
        sa.select(
            episodes.c.id,
            episodes.c.show_id,
            episodes.c.season_id,
            episodes.c.index,
            episodes.c.episode_identifier,
            episodes.c.title,
        )
        .order_by(episodes.c.show_id, episodes.c.index, episodes.c.id)
    ).mappings().all()
    rows_by_id = {int(row["id"]): row for row in episode_rows}
    episodes_by_show: dict[int, list] = defaultdict(list)
    for row in episode_rows:
        episodes_by_show[int(row["show_id"])].append(row)

    previous_by_episode = _previous_identifier_rows(connection, metadata_table)

    existing_meta = {
        (int(row["parent_id"]), str(row["key"])): int(row["value"])
        for row in connection.execute(
            sa.select(
                metadata_table.c.parent_id,
                metadata_table.c.key,
                metadata_table.c.value,
            ).where(
                metadata_table.c.parent_table == "shows",
                metadata_table.c.key.in_(
                    ("ep_id.latest_aux_num", "ep_id.latest_trailer_num")
                ),
            )
        ).mappings()
        if str(row["value"]).isdigit()
    }

    for show_id, rows in episodes_by_show.items():
        mode = show_modes[show_id]
        counters = {
            "aux": existing_meta.get((show_id, "ep_id.latest_aux_num"), 0),
            "trailer": existing_meta.get((show_id, "ep_id.latest_trailer_num"), 0),
        }
        reserved: set[str] = set()

        for row in rows:
            current = str(row["episode_identifier"])
            reserved.add(current)
            for kind in ("aux", "trailer"):
                number = _generated_number(current, kind)
                if number is not None:
                    counters[kind] = max(counters[kind], number)

            previous = previous_by_episode.get(int(row["id"]))
            if previous is not None:
                previous_identifier = previous[1]
                for kind in ("aux", "trailer"):
                    number = _generated_number(previous_identifier, kind)
                    if number is not None:
                        counters[kind] = max(counters[kind], number)

        planned_current: dict[int, str] = {}
        planned_previous: dict[int, str] = {}

        def allocate(kind: str) -> str:
            while True:
                counters[kind] += 1
                candidate = f"{kind}.{counters[kind]}"
                if candidate not in reserved:
                    reserved.add(candidate)
                    return candidate

        def canonicalize(row, identifier: str, *, active: bool) -> str:
            season_type, season_number = season_semantics[int(row["season_id"])]
            desired, generated_type = _canonical_source_identifier(
                identifier_mode=mode,
                season_type=season_type,
                season_number=season_number,
                title=str(row["title"] or ""),
                identifier=identifier,
            )

            if generated_type is not None:
                return allocate(generated_type)

            assert desired is not None
            if not active:
                return desired

            owner = next(
                (
                    episode_id
                    for episode_id, planned in planned_current.items()
                    if planned == desired
                ),
                None,
            )
            if owner is not None and owner != int(row["id"]):
                return allocate("aux")
            return desired

        for row in rows:
            episode_id = int(row["id"])
            current = str(row["episode_identifier"])
            if current.startswith("not-usable."):
                previous = previous_by_episode.get(episode_id)
                if previous is not None:
                    planned_previous[episode_id] = canonicalize(
                        row,
                        previous[1],
                        active=False,
                    )
                continue

            planned_current[episode_id] = canonicalize(
                row,
                current,
                active=True,
            )

        changed_ids = [
            episode_id
            for episode_id, desired in planned_current.items()
            if desired != str(rows_by_id[episode_id]["episode_identifier"])
        ]
        for episode_id in changed_ids:
            connection.execute(
                sa.update(episodes)
                .where(episodes.c.id == episode_id)
                .values(episode_identifier=f"local-indexing-migration.{episode_id}")
            )
        for episode_id in changed_ids:
            connection.execute(
                sa.update(episodes)
                .where(episodes.c.id == episode_id)
                .values(episode_identifier=planned_current[episode_id])
            )

        for episode_id, desired in planned_previous.items():
            metadata_id, current_previous = previous_by_episode[episode_id]
            if desired == current_previous:
                continue
            connection.execute(
                sa.update(metadata_table)
                .where(metadata_table.c.id == metadata_id)
                .values(value=desired)
            )

        connection.execute(
            sa.delete(metadata_table).where(
                metadata_table.c.parent_table == "shows",
                metadata_table.c.parent_id == show_id,
                sa.or_(
                    metadata_table.c.key == "ep_id.latest_ep_num",
                    metadata_table.c.key == "ep_id.latest_ep_extra_num",
                    metadata_table.c.key.like("ep_id.latest_season_%_ep"),
                ),
            )
        )
        if counters["aux"] > 0 or (show_id, "ep_id.latest_aux_num") in existing_meta:
            _set_show_meta(
                connection,
                metadata_table,
                show_id,
                "ep_id.latest_aux_num",
                counters["aux"],
            )
        if counters["trailer"] > 0 or (show_id, "ep_id.latest_trailer_num") in existing_meta:
            _set_show_meta(
                connection,
                metadata_table,
                show_id,
                "ep_id.latest_trailer_num",
                counters["trailer"],
            )


def _identifier_for_previous_release(
    identifier_mode: str,
    *,
    season_index: int,
    identifier: str,
) -> str:
    if identifier_mode == "numbered":
        match = _CANONICAL_NUMBERED_EXTRA_RE.fullmatch(identifier)
        if match:
            return f"ep-extra.{int(match.group(1))}.{int(match.group(2))}"
        return identifier

    if identifier_mode == "seasonal":
        match = _CANONICAL_SEASONAL_MAIN_RE.fullmatch(identifier)
        if match:
            return f"ep.S{season_index:02d}E{int(match.group(1)):02d}"
        match = _CANONICAL_SEASONAL_EXTRA_RE.fullmatch(identifier)
        if match:
            return (
                f"ep-extra.S{season_index:02d}E{int(match.group(1)):02d}."
                f"{int(match.group(2))}"
            )

    return identifier


def _restore_previous_allocator_metadata(
    connection,
    *,
    metadata_table,
    show_id: int,
    identifier_mode: str,
    identifiers: list[str],
) -> None:
    if identifier_mode == "numbered":
        latest = 0
        extras_by_parent: dict[int, int] = {}
        for identifier in identifiers:
            if match := _NUMBERED_MAIN_RE.fullmatch(identifier):
                latest = max(latest, int(match.group(1)))
            elif match := _LEGACY_NUMBERED_EXTRA_RE.fullmatch(identifier):
                parent = int(match.group(1))
                latest = max(latest, parent)
                extras_by_parent[parent] = max(
                    extras_by_parent.get(parent, 0),
                    int(match.group(2)),
                )
        _set_show_meta(
            connection,
            metadata_table,
            show_id,
            "ep_id.latest_ep_num",
            latest,
        )
        _set_show_meta(
            connection,
            metadata_table,
            show_id,
            "ep_id.latest_ep_extra_num",
            extras_by_parent.get(latest, 0),
        )
        return

    if identifier_mode == "seasonal":
        latest_by_season: dict[int, int] = {}
        latest_extra = 0
        legacy_seasonal_main = re.compile(r"^ep\.S(\d+)E(\d+)$")
        legacy_seasonal_extra = re.compile(
            r"^ep-extra\.S(\d+)E(\d+)\.(\d+)$"
        )
        for identifier in identifiers:
            if match := legacy_seasonal_main.fullmatch(identifier):
                season_index = int(match.group(1))
                latest_by_season[season_index] = max(
                    latest_by_season.get(season_index, 0),
                    int(match.group(2)),
                )
            elif match := legacy_seasonal_extra.fullmatch(identifier):
                season_index = int(match.group(1))
                episode_number = int(match.group(2))
                latest_by_season[season_index] = max(
                    latest_by_season.get(season_index, 0),
                    episode_number,
                )
                latest_extra = max(latest_extra, int(match.group(3)))

        for season_index, latest in latest_by_season.items():
            _set_show_meta(
                connection,
                metadata_table,
                show_id,
                f"ep_id.latest_season_{season_index}_ep",
                latest,
            )
        _set_show_meta(
            connection,
            metadata_table,
            show_id,
            "ep_id.latest_ep_extra_num",
            latest_extra,
        )


def _downgrade_episode_identifiers() -> None:
    connection = op.get_bind()

    metadata = sa.MetaData()
    shows = sa.Table("shows", metadata, autoload_with=connection)
    seasons = sa.Table("seasons", metadata, autoload_with=connection)
    episodes = sa.Table("media_items_episode", metadata, autoload_with=connection)
    metadata_table = sa.Table("metadata", metadata, autoload_with=connection)

    show_modes = {
        int(row["id"]): str(row["episode_identifier"])
        for row in connection.execute(
            sa.select(shows.c.id, shows.c.episode_identifier)
        ).mappings()
    }
    season_indices = {
        int(row["id"]): int(row["index"])
        for row in connection.execute(
            sa.select(seasons.c.id, seasons.c.index)
        ).mappings()
    }
    episode_rows = connection.execute(
        sa.select(
            episodes.c.id,
            episodes.c.show_id,
            episodes.c.season_id,
            episodes.c.episode_identifier,
        ).order_by(episodes.c.show_id, episodes.c.index, episodes.c.id)
    ).mappings().all()

    planned = {
        int(row["id"]): _identifier_for_previous_release(
            show_modes[int(row["show_id"])],
            season_index=season_indices[int(row["season_id"])],
            identifier=str(row["episode_identifier"]),
        )
        for row in episode_rows
        if not str(row["episode_identifier"]).startswith("not-usable.")
    }

    changed = [
        row
        for row in episode_rows
        if int(row["id"]) in planned
        and planned[int(row["id"])] != str(row["episode_identifier"])
    ]
    for row in changed:
        episode_id = int(row["id"])
        connection.execute(
            sa.update(episodes)
            .where(episodes.c.id == episode_id)
            .values(episode_identifier=f"local-indexing-downgrade.{episode_id}")
        )
    for row in changed:
        episode_id = int(row["id"])
        connection.execute(
            sa.update(episodes)
            .where(episodes.c.id == episode_id)
            .values(episode_identifier=planned[episode_id])
        )

    previous_by_episode = _previous_identifier_rows(connection, metadata_table)
    rows_by_id = {int(row["id"]): row for row in episode_rows}
    identifiers_by_show: dict[int, list[str]] = defaultdict(list)
    for row in episode_rows:
        episode_id = int(row["id"])
        identifier = planned.get(episode_id, str(row["episode_identifier"]))
        identifiers_by_show[int(row["show_id"])].append(identifier)

    for episode_id, (metadata_id, identifier) in previous_by_episode.items():
        row = rows_by_id.get(episode_id)
        if row is None:
            continue
        desired = _identifier_for_previous_release(
            show_modes[int(row["show_id"])],
            season_index=season_indices[int(row["season_id"])],
            identifier=identifier,
        )
        if desired != identifier:
            connection.execute(
                sa.update(metadata_table)
                .where(metadata_table.c.id == metadata_id)
                .values(value=desired)
            )

    for show_id, identifier_mode in show_modes.items():
        _restore_previous_allocator_metadata(
            connection,
            metadata_table=metadata_table,
            show_id=show_id,
            identifier_mode=identifier_mode,
            identifiers=identifiers_by_show.get(show_id, []),
        )

    # e4c91a7b2d30 owns the episode-indexing schema columns. They must remain
    # present when this revision is downgraded to e5f1a2c7d903; e4 removes them
    # when the migration chain is downgraded past that historical revision.


# -------------------------------------------------------------------------

def _thumbnail_table(table_name: str):
    return sa.table(
        table_name,
        sa.column("thumbnail_landscape_path", sa.String()),
        sa.column("thumbnail_portrait_path", sa.String()),
        sa.column("thumbnail_square_path", sa.String()),
    )


_THUMBNAIL_FIELDS = {
    "landscape": "thumbnail_landscape_path",
    "portrait": "thumbnail_portrait_path",
    "square": "thumbnail_square_path",
}


def _normalize_table_thumbnail_aliases(bind, table_name: str, *, default: str) -> None:
    thumbnails = _thumbnail_table(table_name)
    default_column = getattr(thumbnails.c, _THUMBNAIL_FIELDS[default])

    for orientation, field_name in _THUMBNAIL_FIELDS.items():
        if orientation == default:
            continue

        alternate_column = getattr(thumbnails.c, field_name)
        bind.execute(
            sa.update(thumbnails)
            .where(
                alternate_column.is_not(None),
                alternate_column == default_column,
            )
            .values({field_name: None})
        )


def _normalize_thumbnail_aliases(bind) -> None:
    _normalize_table_thumbnail_aliases(bind, "shows", default="portrait")
    _normalize_table_thumbnail_aliases(
        bind,
        "media_items_episode",
        default="landscape",
    )
    _normalize_table_thumbnail_aliases(bind, "media_items_movie", default="portrait")
    _normalize_table_thumbnail_aliases(
        bind,
        "movie_extra_sources",
        default="landscape",
    )


def _upgrade_thumbnail_aliases() -> None:
    _normalize_thumbnail_aliases(op.get_bind())


def _downgrade_thumbnail_aliases() -> None:
    # One-way cleanup: once a duplicate alias is cleared, it cannot be
    # distinguished from a thumbnail that was genuinely absent beforehand.
    pass


# -------------------------------------------------------------------------

_HLS_VIDEO_METHODS = (
    "stream_hls_download_m4a",
    "stream_hls_download_mp4",
)


def _upgrade_rss_live_episode_streaming() -> None:
    with op.batch_alter_table("stream_profiles_rss") as batch_op:
        batch_op.add_column(
            sa.Column(
                "stream_live_episodes",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )
        batch_op.add_column(
            sa.Column(
                "live_episode_handoff_ids",
                sa.JSON(),
                nullable=False,
                server_default="[]",
            )
        )

    # HLS video profiles using Daily Wire already exposed LIVE episodes before
    # this setting existed. Keep those existing profiles behaviorally unchanged;
    # newly created profiles still use the explicit opt-in default.
    connection = op.get_bind()
    rss = sa.table(
        "stream_profiles_rss",
        sa.column("id", sa.Integer()),
        sa.column("dw_video_method", sa.String()),
        sa.column("stream_live_episodes", sa.Boolean()),
    )
    base = sa.table(
        "stream_profiles",
        sa.column("id", sa.Integer()),
        sa.column("use_dw_stream", sa.Boolean()),
        sa.column("preferred_format", sa.String()),
    )
    existing_hls_profiles = (
        sa.select(rss.c.id)
        .select_from(rss.join(base, base.c.id == rss.c.id))
        .where(
            base.c.use_dw_stream.is_(True),
            base.c.preferred_format != "format_audio_only",
            rss.c.dw_video_method.in_(_HLS_VIDEO_METHODS),
        )
    )
    connection.execute(
        rss.update()
        .where(rss.c.id.in_(existing_hls_profiles))
        .values(stream_live_episodes=True)
    )


def _downgrade_rss_live_episode_streaming() -> None:
    with op.batch_alter_table("stream_profiles_rss") as batch_op:
        batch_op.drop_column("live_episode_handoff_ids")
        batch_op.drop_column("stream_live_episodes")


# -------------------------------------------------------------------------

_OLD_TO_NEW = {
    "stream_hls_download_m4a": "audio_hls",
    "stream_download_mp4": "mp4",
    "stream_hls_download_mp4": "mp4_hls",
}

_NEW_TO_OLD = {
    "audio_hls": "stream_hls_download_m4a",
    "audio_mp4": "stream_download_mp4",
    "mp4": "stream_download_mp4",
    "mp4_hls": "stream_hls_download_mp4",
}


def _without_legacy_method_query(feed_url: str) -> str:
    parts = urlsplit(feed_url)
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key != "dwVideoMethod"
    ]
    return urlunsplit((
        parts.scheme,
        parts.netloc,
        parts.path,
        urlencode(query),
        parts.fragment,
    ))



def _upgrade_rss_video_output_modes() -> None:
    connection = op.get_bind()
    rows = connection.execute(
        sa.text("SELECT id, dw_video_method, feed_url FROM stream_profiles_rss")
    ).mappings().all()

    for row in rows:
        connection.execute(
            sa.text(
                "UPDATE stream_profiles_rss "
                "SET dw_video_method = :mode, feed_url = :feed_url "
                "WHERE id = :id"
            ),
            {
                "id": row["id"],
                "mode": _OLD_TO_NEW.get(row["dw_video_method"], "audio_hls"),
                "feed_url": _without_legacy_method_query(row["feed_url"]),
            },
        )

    with op.batch_alter_table("stream_profiles_rss") as batch_op:
        batch_op.alter_column(
            "dw_video_method",
            new_column_name="video_output_mode",
            existing_type=sa.String(),
            existing_nullable=False,
            existing_server_default="stream_hls_download_m4a",
            nullable=True,
            server_default=None,
        )

    connection.execute(
        sa.text(
            "UPDATE stream_profiles_rss "
            "SET video_output_mode = NULL "
            "WHERE id IN ("
            "SELECT rss.id "
            "FROM stream_profiles_rss AS rss "
            "JOIN stream_profiles AS base ON base.id = rss.id "
            "WHERE base.preferred_format = :audio_only"
            ")"
        ),
        {"audio_only": "format_audio_only"},
    )


def _downgrade_rss_video_output_modes() -> None:
    connection = op.get_bind()
    connection.execute(
        sa.text(
            "UPDATE stream_profiles_rss "
            "SET video_output_mode = :default_mode "
            "WHERE video_output_mode IS NULL"
        ),
        {"default_mode": "audio_hls"},
    )

    rows = connection.execute(
        sa.text("SELECT id, video_output_mode FROM stream_profiles_rss")
    ).mappings().all()
    for row in rows:
        connection.execute(
            sa.text(
                "UPDATE stream_profiles_rss "
                "SET video_output_mode = :method "
                "WHERE id = :id"
            ),
            {
                "id": row["id"],
                "method": _NEW_TO_OLD.get(
                    row["video_output_mode"],
                    "stream_hls_download_m4a",
                ),
            },
        )

    with op.batch_alter_table("stream_profiles_rss") as batch_op:
        batch_op.alter_column(
            "video_output_mode",
            new_column_name="dw_video_method",
            existing_type=sa.String(),
            existing_nullable=True,
            nullable=False,
            server_default="stream_hls_download_m4a",
        )


# -------------------------------------------------------------------------

def _upgrade_prefer_exact_match() -> None:
    with op.batch_alter_table("stream_profiles") as batch_op:
        batch_op.alter_column(
            "require_exact_match",
            new_column_name="prefer_exact_match",
            existing_type=sa.Boolean(),
            existing_nullable=False,
        )


def _downgrade_prefer_exact_match() -> None:
    with op.batch_alter_table("stream_profiles") as batch_op:
        batch_op.alter_column(
            "prefer_exact_match",
            new_column_name="require_exact_match",
            existing_type=sa.Boolean(),
            existing_nullable=False,
        )


# -------------------------------------------------------------------------


def _upgrade_custom_indexing() -> None:
    op.execute(sa.text(
        "DELETE FROM metadata WHERE key LIKE 'custom\\_index.%' ESCAPE '\\'"
    ))
    op.create_table(
        "custom_index_states",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("show_id", sa.Integer(), sa.ForeignKey("shows.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "local_media_profile_id",
            sa.Integer(),
            sa.ForeignKey("local_media_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("requested_generation", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("completed_generation", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("show_id", "local_media_profile_id", name="uq_custom_index_state_scope"),
    )
    op.create_index("ix_custom_index_states_show_id", "custom_index_states", ["show_id"])
    op.create_index(
        "ix_custom_index_states_local_media_profile_id",
        "custom_index_states",
        ["local_media_profile_id"],
    )


def _downgrade_custom_indexing() -> None:
    op.execute(sa.text(
        "DELETE FROM metadata WHERE key LIKE 'custom\\_index.%' ESCAPE '\\'"
    ))
    op.drop_index("ix_custom_index_states_local_media_profile_id", table_name="custom_index_states")
    op.drop_index("ix_custom_index_states_show_id", table_name="custom_index_states")
    op.drop_table("custom_index_states")


# -------------------------------------------------------------------------

def _upgrade_stream_profile_title_override() -> None:
    with op.batch_alter_table("stream_profiles") as batch_op:
        batch_op.add_column(
            sa.Column("overwrite_show_title", sa.String(), nullable=True)
        )


def _downgrade_stream_profile_title_override() -> None:
    with op.batch_alter_table("stream_profiles") as batch_op:
        batch_op.drop_column("overwrite_show_title")


# -------------------------------------------------------------------------

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


def _upgrade_media_download_history() -> None:
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


def _downgrade_media_download_history() -> None:
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


# Release migration ---------------------------------------------------------


def upgrade() -> None:
    """Upgrade a shipped WireLoft 1.1 database directly to WireLoft 1.2."""
    _upgrade_media_thumbnails()
    _upgrade_sqlite_foreign_key_integrity()
    _upgrade_output_template_spacing()
    _upgrade_episode_indexing_schema()
    _upgrade_background_migration_version()
    _upgrade_episode_identifiers()
    _upgrade_thumbnail_aliases()
    _upgrade_rss_live_episode_streaming()
    _upgrade_rss_video_output_modes()
    _upgrade_prefer_exact_match()
    _upgrade_custom_indexing()
    _upgrade_stream_profile_title_override()
    _upgrade_media_download_history()


def downgrade() -> None:
    """Return the WireLoft 1.2 schema to the shipped WireLoft 1.1 schema."""
    _downgrade_media_download_history()
    _downgrade_stream_profile_title_override()
    _downgrade_custom_indexing()
    _downgrade_prefer_exact_match()
    _downgrade_rss_video_output_modes()
    _downgrade_rss_live_episode_streaming()
    _downgrade_thumbnail_aliases()
    _downgrade_episode_identifiers()
    _downgrade_background_migration_version()
    _downgrade_episode_indexing_schema()
    _downgrade_output_template_spacing()
    _downgrade_sqlite_foreign_key_integrity()
    _downgrade_media_thumbnails()
