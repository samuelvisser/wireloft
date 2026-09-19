"""Correct false-negative trailer classifications from explicit titles.

Revision ID: 7c2a9e5d4b10
Revises: e4c91a7b2d30
"""
from __future__ import annotations

from collections import defaultdict
import re

from alembic import op
import sqlalchemy as sa


revision = "7c2a9e5d4b10"
down_revision = "e4c91a7b2d30"
branch_labels = None
depends_on = None


_OFFICIAL_TRAILER_RE = re.compile(r"\bofficial\s+trailer\b", re.IGNORECASE)
_TRAILER_IDENTIFIER_RE = re.compile(r"^trailer\.(\d+)$")
_NUMBERED_MAIN_RE = re.compile(r"^ep\.(\d+)$")
_NUMBERED_EXTRA_RE = re.compile(
    r"^ep-extra\.(?:other|trailer)\.(\d+)\.(\d+)$"
)
_SEASONAL_MAIN_RE = re.compile(r"^ep\.(S\d+E\d+)$")
_SEASONAL_EXTRA_RE = re.compile(
    r"^ep-extra\.(?:other|trailer)\.(S\d+E\d+)\.(\d+)$"
)
_PREVIOUS_IDENTIFIER_KEY = "no_usable_media.previous_identifier"


def _dw_number(raw: str | None) -> tuple[int | None, int]:
    value = (raw or "").strip()
    if not value:
        return None, 0
    whole, separator, fractional = value.partition(".")
    try:
        number = int(whole)
    except ValueError:
        return None, 0
    if not separator:
        return number, 0
    try:
        return number, int(fractional)
    except ValueError:
        return number, 0


def _source_slot(identifier: str) -> str | None:
    if match := _NUMBERED_MAIN_RE.fullmatch(identifier):
        return f"{int(match.group(1))}.0"
    if match := _NUMBERED_EXTRA_RE.fullmatch(identifier):
        return f"{int(match.group(1))}.{int(match.group(2))}"
    if match := _SEASONAL_MAIN_RE.fullmatch(identifier):
        return match.group(1) + ".0"
    if match := _SEASONAL_EXTRA_RE.fullmatch(identifier):
        return f"{match.group(1)}.{int(match.group(2))}"
    return None


def _trailer_number(identifier: str) -> int | None:
    match = _TRAILER_IDENTIFIER_RE.fullmatch(identifier)
    return int(match.group(1)) if match else None


def _set_show_meta(connection, metadata_table, show_id: int, key: str, value: int) -> None:
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


def upgrade() -> None:
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
    season_info = {
        int(row["id"]): (str(row["season_type"]), int(row["season_number"]))
        for row in connection.execute(
            sa.select(
                seasons.c.id,
                seasons.c.season_type,
                seasons.c.season_number,
            )
        ).mappings()
    }
    episode_rows = connection.execute(
        sa.select(
            episodes.c.id,
            episodes.c.show_id,
            episodes.c.season_id,
            episodes.c.index,
            episodes.c.title,
            episodes.c.dw_episode_number,
            episodes.c.episode_identifier,
        ).order_by(episodes.c.show_id, episodes.c.index, episodes.c.id)
    ).mappings().all()

    previous_rows = connection.execute(
        sa.select(
            metadata_table.c.id,
            metadata_table.c.parent_id,
            metadata_table.c.value,
        ).where(
            metadata_table.c.parent_table == "media_items_episode",
            metadata_table.c.key == _PREVIOUS_IDENTIFIER_KEY,
        )
    ).mappings().all()
    previous_by_episode = {
        int(row["parent_id"]): (int(row["id"]), str(row["value"]))
        for row in previous_rows
    }
    rows_by_id = {int(row["id"]): row for row in episode_rows}

    used_identifiers: dict[int, dict[str, int]] = defaultdict(dict)
    source_owners: dict[int, dict[str, int]] = defaultdict(dict)
    trailer_numbers: dict[int, set[int]] = defaultdict(set)
    trailer_counters: dict[int, int] = defaultdict(int)

    for row in episode_rows:
        show_id = int(row["show_id"])
        episode_id = int(row["id"])
        identifier = str(row["episode_identifier"])
        used_identifiers[show_id][identifier] = episode_id
        if source_slot := _source_slot(identifier):
            source_owners[show_id][source_slot] = episode_id
        if number := _trailer_number(identifier):
            trailer_numbers[show_id].add(number)
            trailer_counters[show_id] = max(trailer_counters[show_id], number)

    for episode_id, (_metadata_id, identifier) in previous_by_episode.items():
        row = rows_by_id.get(episode_id)
        if row is None:
            continue
        show_id = int(row["show_id"])
        if number := _trailer_number(identifier):
            trailer_numbers[show_id].add(number)
            trailer_counters[show_id] = max(trailer_counters[show_id], number)

    for row in connection.execute(
        sa.select(
            metadata_table.c.parent_id,
            metadata_table.c.value,
        ).where(
            metadata_table.c.parent_table == "shows",
            metadata_table.c.key == "ep_id.latest_trailer_num",
        )
    ).mappings():
        show_id = int(row["parent_id"])
        try:
            value = int(row["value"])
        except (TypeError, ValueError):
            continue
        trailer_counters[show_id] = max(trailer_counters[show_id], value)

    def allocate_trailer(show_id: int) -> str:
        number = trailer_counters[show_id]
        while True:
            number += 1
            identifier = f"trailer.{number}"
            if (
                number not in trailer_numbers[show_id]
                and identifier not in used_identifiers[show_id]
            ):
                trailer_numbers[show_id].add(number)
                trailer_counters[show_id] = number
                return identifier

    def desired_identifier(row, effective_identifier: str, *, quarantined: bool) -> str:
        show_id = int(row["show_id"])
        season_type, season_number = season_info[int(row["season_id"])]
        mode = show_modes[show_id]

        if season_type == "extra" or mode == "date_based":
            if effective_identifier.startswith("trailer."):
                return effective_identifier
            return allocate_trailer(show_id)

        number, segment = _dw_number(row["dw_episode_number"])
        if number is None or segment == 0:
            if effective_identifier.startswith("trailer."):
                return effective_identifier
            return allocate_trailer(show_id)

        if mode == "numbered":
            candidate = f"ep-extra.trailer.{number}.{segment}"
            source_slot = f"{number}.{segment}"
        elif mode == "seasonal":
            label = f"S{season_number:02d}E{number:02d}"
            candidate = f"ep-extra.trailer.{label}.{segment}"
            source_slot = f"{label}.{segment}"
        else:
            return allocate_trailer(show_id)

        if quarantined:
            return candidate

        owner = source_owners[show_id].get(source_slot)
        if owner is not None and owner != int(row["id"]):
            return effective_identifier
        identifier_owner = used_identifiers[show_id].get(candidate)
        if identifier_owner is not None and identifier_owner != int(row["id"]):
            return effective_identifier
        return candidate

    planned_current: dict[int, str] = {}
    planned_previous: dict[int, tuple[int, str]] = {}

    for row in episode_rows:
        if not _OFFICIAL_TRAILER_RE.search(str(row["title"] or "")):
            continue

        episode_id = int(row["id"])
        show_id = int(row["show_id"])
        current = str(row["episode_identifier"])
        previous = previous_by_episode.get(episode_id)
        quarantined = current.startswith("not-usable.") and previous is not None
        effective = previous[1] if quarantined else current
        desired = desired_identifier(
            row,
            effective,
            quarantined=quarantined,
        )
        if desired == effective:
            continue

        if quarantined:
            planned_previous[episode_id] = (previous[0], desired)
            continue

        planned_current[episode_id] = desired
        used_identifiers[show_id].pop(current, None)
        used_identifiers[show_id][desired] = episode_id

        old_slot = _source_slot(current)
        new_slot = _source_slot(desired)
        if old_slot is not None and source_owners[show_id].get(old_slot) == episode_id:
            source_owners[show_id].pop(old_slot, None)
        if new_slot is not None:
            source_owners[show_id][new_slot] = episode_id

    for episode_id in planned_current:
        connection.execute(
            sa.update(episodes)
            .where(episodes.c.id == episode_id)
            .values(episode_identifier=f"official-trailer-fix.{episode_id}")
        )
    for episode_id, identifier in planned_current.items():
        connection.execute(
            sa.update(episodes)
            .where(episodes.c.id == episode_id)
            .values(episode_identifier=identifier)
        )

    for _episode_id, (metadata_id, identifier) in planned_previous.items():
        connection.execute(
            sa.update(metadata_table)
            .where(metadata_table.c.id == metadata_id)
            .values(value=identifier)
        )

    changed_show_ids = {
        int(row["show_id"])
        for row in episode_rows
        if int(row["id"]) in planned_current or int(row["id"]) in planned_previous
    }
    for show_id in changed_show_ids:
        _set_show_meta(
            connection,
            metadata_table,
            show_id,
            "ep_id.latest_trailer_num",
            trailer_counters[show_id],
        )


def downgrade() -> None:
    # This revision corrects semantic data that remains valid under the previous
    # schema. Re-introducing known false-negative trailer classifications would
    # be destructive, so the data correction is intentionally retained.
    pass
