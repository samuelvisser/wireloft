"""Normalize local episode indexing data.

Revision ID: 7c2a9e5d4b10
Revises: e5f1a2c7d903
"""
from __future__ import annotations

from collections import defaultdict
import re

from alembic import op
import sqlalchemy as sa


revision = "7c2a9e5d4b10"
down_revision = "e5f1a2c7d903"
branch_labels = None
depends_on = None


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
_BACKGROUND_MIGRATION_REVISION = "f6a1c3d8b427"
_LEGACY_BACKGROUND_MIGRATION_VERSION = "episode_indexing_semantics"


def _season_type(name: str) -> str:
    return "extra" if _EXTRAS_RE.search(name or "") else "normal"


def _column_names(connection, table_name: str) -> set[str]:
    return {
        str(column["name"])
        for column in sa.inspect(connection).get_columns(table_name)
    }


def _add_episode_indexing_columns(connection) -> None:
    """Ensure episode-indexing columns exist for historical development databases.

    Revision e4c91a7b2d30 originally introduced these columns, but it was briefly
    removed from the migration graph while e5f1a2c7d903 was already in use. A
    database stamped at e5 can therefore legitimately be missing them. SQLite can
    also persist individual ADD COLUMN statements after an interrupted migration,
    so this remains deliberately idempotent.
    """
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


def _normalize_background_migration_revision(connection) -> None:
    """Rewrite the prerelease descriptive ledger value to the opaque revision."""
    settings = sa.Table("settings", sa.MetaData(), autoload_with=connection)
    connection.execute(
        sa.update(settings)
        .where(
            settings.c.background_migration_version
            == _LEGACY_BACKGROUND_MIGRATION_VERSION
        )
        .values(background_migration_version=_BACKGROUND_MIGRATION_REVISION)
    )


def _reset_background_migration_revision_for_downgrade(connection) -> None:
    """Return the ledger to develop, which has no registered background revisions."""
    settings = sa.Table("settings", sa.MetaData(), autoload_with=connection)
    connection.execute(
        sa.update(settings)
        .where(
            settings.c.background_migration_version.in_(
                (
                    _BACKGROUND_MIGRATION_REVISION,
                    _LEGACY_BACKGROUND_MIGRATION_VERSION,
                )
            )
        )
        .values(background_migration_version=None)
    )


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


def upgrade() -> None:
    connection = op.get_bind()
    _add_episode_indexing_columns(connection)
    _normalize_background_migration_revision(connection)
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


def downgrade() -> None:
    connection = op.get_bind()
    _reset_background_migration_revision_for_downgrade(connection)
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
