"""Rebuild episode identifiers from authoritative Daily Wire numbering.

Revision ID: e4c91a7b2d30
Revises: 9b1f4e7c2d6a
"""
from __future__ import annotations

from collections import defaultdict
from datetime import timezone
import re
from urllib.parse import urlparse

from alembic import op
import sqlalchemy as sa


revision = "e4c91a7b2d30"
down_revision = "9b1f4e7c2d6a"
branch_labels = None
depends_on = None


_EXTRAS_RE = re.compile(r"\bextras?\b", re.IGNORECASE)
_TRAILER_RE = re.compile(r"\btrailer\b", re.IGNORECASE)
_OFFICIAL_TRAILER_RE = re.compile(r"\bofficial\s+trailer\b", re.IGNORECASE)
_GENERATED_RE = re.compile(r"^(aux|trailer)\.(\d+)$")
_LEGACY_NUMBERED_MAIN_RE = re.compile(r"^ep\.(\d+)$")
_LEGACY_SEASONAL_MAIN_RE = re.compile(r"^ep\.S\d+E(\d+)$")
_PREVIOUS_IDENTIFIER_KEY = "no_usable_media.previous_identifier"


def _is_dailywire_url(value: str) -> bool:
    host = (urlparse(value).hostname or "").lower()
    return host == "dailywire.com" or host.endswith(".dailywire.com")


def _season_type(name: str) -> str:
    return "extra" if _EXTRAS_RE.search(name or "") else "normal"


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


def _is_trailer(record) -> bool:
    # The Daily Wire has false-negative isTrailer values for records explicitly
    # titled "Official Trailer". Treat either affirmative signal as sufficient.
    return (
        bool(_OFFICIAL_TRAILER_RE.search(record.title or ""))
        or record.is_trailer is True
    )


def _date_identifier(record) -> str:
    published = record.published_date.astimezone(timezone.utc)
    return "ep." + published.strftime("%Y-%m-%dT%H:%M:%S.%f")


def _direct_identifier(
    identifier_mode: str,
    *,
    season_type: str,
    season_number: int,
    record,
) -> tuple[str | None, str | None]:
    """Return (identifier, source_slot); standalone content returns (None, None)."""
    if season_type == "extra":
        return None, None

    if identifier_mode == "date_based":
        if _is_trailer(record):
            return None, None
        identifier = _date_identifier(record)
        return identifier, "identifier:" + identifier

    number, segment = _dw_number(record.episode_number)
    if number is None:
        return None, None

    trailer = _is_trailer(record)
    if segment == 0:
        if trailer:
            return None, None
        if identifier_mode == "numbered":
            return f"ep.{number}", f"{number}.0"
        if identifier_mode == "seasonal":
            return (
                f"ep.S{season_number:02d}E{number:02d}",
                f"S{season_number:02d}E{number:02d}.0",
            )

    if segment > 0:
        extra_type = "trailer" if trailer else "other"
        if identifier_mode == "numbered":
            return (
                f"ep-extra.{extra_type}.{number}.{segment}",
                f"{number}.{segment}",
            )
        if identifier_mode == "seasonal":
            return (
                f"ep-extra.{extra_type}.S{season_number:02d}E{number:02d}.{segment}",
                f"S{season_number:02d}E{number:02d}.{segment}",
            )

    return None, None


def _generated_type(
    identifier_mode: str,
    *,
    season_type: str,
    record,
) -> str | None:
    if season_type == "extra":
        return "trailer" if _is_trailer(record) else "aux"

    if identifier_mode == "date_based":
        return "trailer" if _is_trailer(record) else None

    number, segment = _dw_number(record.episode_number)
    if number is None:
        return "trailer" if _is_trailer(record) else "aux"
    if segment == 0 and _is_trailer(record):
        return "trailer"
    return None


def _legacy_fallback_identifier(
    identifier_mode: str,
    *,
    season_number: int,
    current_identifier: str,
) -> str | None:
    """Recover only semantics that the old database stored without ambiguity."""
    if current_identifier.startswith("aux.") or current_identifier.startswith("trailer."):
        return current_identifier
    if identifier_mode == "numbered":
        match = _LEGACY_NUMBERED_MAIN_RE.fullmatch(current_identifier)
        if match:
            return f"ep.{int(match.group(1))}"
    if identifier_mode == "seasonal":
        match = _LEGACY_SEASONAL_MAIN_RE.fullmatch(current_identifier)
        if match:
            return f"ep.S{season_number:02d}E{int(match.group(1)):02d}"
    if identifier_mode == "date_based" and current_identifier.startswith("ep."):
        return current_identifier
    return None


def _fetch_full_season(client, show_slug: str, membership_plan: str, season_dw_id: str):
    from dailywire_api.dw_api.client import ByNextPage, ByShowSeason

    items, next_url, has_next = client.get_episodes_paginated(
        show_slug,
        ByShowSeason(
            season_dw_id=season_dw_id,
            membership_plan=membership_plan,
            page_size=50,
            order_by="CreatedAt_ASC",
        ),
    )
    records = list(items or [])
    while has_next and next_url:
        items, next_url, has_next = client.get_episodes_paginated(
            show_slug,
            ByNextPage(next_page_url=next_url),
        )
        records.extend(items or [])
    return list(dict.fromkeys(records))


def _resolve_possible_trailer(
    client,
    record,
    *,
    require_member_exclusive: bool,
):
    from dailywire_api.dw_api.client import MiddlewareAPIError

    if record.is_trailer is True:
        return record
    if _OFFICIAL_TRAILER_RE.search(record.title or ""):
        return record
    if not _TRAILER_RE.search(record.title or ""):
        return record
    try:
        return client.get_episode_details(
            record.slug,
            require_member_exclusive=require_member_exclusive,
        )
    except MiddlewareAPIError as exc:
        if exc.status_code == 404:
            return record
        raise


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


def _previous_identifiers(connection, metadata_table) -> dict[int, str]:
    rows = connection.execute(
        sa.select(metadata_table.c.parent_id, metadata_table.c.value).where(
            metadata_table.c.parent_table == "media_items_episode",
            metadata_table.c.key == _PREVIOUS_IDENTIFIER_KEY,
        )
    ).all()
    return {int(parent_id): str(value) for parent_id, value in rows}


def _update_previous_identifier(
    connection,
    metadata_table,
    episode_id: int,
    identifier: str,
) -> None:
    connection.execute(
        sa.update(metadata_table)
        .where(
            metadata_table.c.parent_table == "media_items_episode",
            metadata_table.c.parent_id == episode_id,
            metadata_table.c.key == _PREVIOUS_IDENTIFIER_KEY,
        )
        .values(value=identifier)
    )


def _generated_number(identifier: str, expected_type: str) -> int | None:
    match = _GENERATED_RE.fullmatch(identifier)
    if not match or match.group(1) != expected_type:
        return None
    return int(match.group(2))


def _upgrade_schema() -> None:
    with op.batch_alter_table("seasons") as batch:
        batch.add_column(
            sa.Column(
                "season_type",
                sa.String(),
                nullable=False,
                server_default="normal",
            )
        )
        batch.add_column(
            sa.Column(
                "season_number",
                sa.Integer(),
                nullable=False,
                server_default="1",
            )
        )

    with op.batch_alter_table("media_items_episode") as batch:
        batch.add_column(sa.Column("dw_episode_number", sa.String(), nullable=True))


def _downgrade_schema() -> None:
    with op.batch_alter_table("media_items_episode") as batch:
        batch.drop_column("dw_episode_number")
    with op.batch_alter_table("seasons") as batch:
        batch.drop_column("season_number")
        batch.drop_column("season_type")


def upgrade() -> None:
    _upgrade_schema()
    connection = op.get_bind()
    metadata = sa.MetaData()
    shows = sa.Table("shows", metadata, autoload_with=connection)
    seasons = sa.Table("seasons", metadata, autoload_with=connection)
    episodes = sa.Table("media_items_episode", metadata, autoload_with=connection)
    metadata_table = sa.Table("metadata", metadata, autoload_with=connection)

    show_rows = connection.execute(
        sa.select(
            shows.c.id,
            shows.c.slug,
            shows.c.membership_level,
            shows.c.episode_identifier,
            shows.c.sharing_url,
        ).order_by(shows.c.id)
    ).mappings().all()
    if not show_rows:
        return

    season_rows = connection.execute(
        sa.select(
            seasons.c.id,
            seasons.c.show_id,
            seasons.c.index,
            seasons.c.slug,
            seasons.c.name,
        ).order_by(seasons.c.show_id, seasons.c.index)
    ).mappings().all()
    seasons_by_show: dict[int, list[dict]] = defaultdict(list)
    season_semantics: dict[int, tuple[str, int]] = {}
    for row in season_rows:
        seasons_by_show[int(row["show_id"])].append(row)

    for show_id, rows in seasons_by_show.items():
        regular_number = 0
        for row in rows:
            kind = _season_type(str(row["name"]))
            if kind == "normal":
                regular_number += 1
                number = regular_number
            else:
                number = 0
            season_semantics[int(row["id"])] = (kind, number)

    local_episode_rows = connection.execute(
        sa.select(
            episodes.c.id,
            episodes.c.show_id,
            episodes.c.season_id,
            episodes.c.index,
            episodes.c.slug,
            episodes.c.episode_identifier,
        ).order_by(episodes.c.show_id, episodes.c.index, episodes.c.id)
    ).mappings().all()
    episodes_by_show: dict[int, list[dict]] = defaultdict(list)
    episodes_by_season: dict[int, list[dict]] = defaultdict(list)
    for row in local_episode_rows:
        episodes_by_show[int(row["show_id"])].append(row)
        episodes_by_season[int(row["season_id"])].append(row)

    # Fetch every authoritative snapshot before mutating season/episode data.
    dailywire_show_rows = [
        row
        for row in show_rows
        if _is_dailywire_url(str(row["sharing_url"]))
    ]
    if dailywire_show_rows:
        from dailywire_api.dw_api.client import MiddlewareAPIError, MiddlewareClient
        from dailywire_authorisation import DeviceAuthClient

        tokens = DeviceAuthClient().get_token()
        requires_token = any(
            str(row["membership_level"]) not in {"FREE", "WL_ANY"}
            for row in dailywire_show_rows
        )
        if requires_token and tokens is None:
            raise RuntimeError(
                "A Daily Wire access token is required to rebuild member-only "
                "episode identifiers during this migration"
            )
        client = MiddlewareClient(access_token=tokens.access_token if tokens else None)
    else:
        MiddlewareAPIError = RuntimeError
        client = None

    remote_by_show_and_season: dict[tuple[int, int], dict[str, object]] = {}

    for show in show_rows:
        is_dailywire_show = _is_dailywire_url(str(show["sharing_url"]))
        if not is_dailywire_show:
            continue
        assert client is not None
        show_id = int(show["id"])
        membership_plan = str(show["membership_level"])
        if membership_plan == "WL_ANY":
            membership_plan = "FREE"
        require_member_exclusive = membership_plan != "FREE"

        dw_show = client.get_show_page(str(show["slug"]), membership_plan=membership_plan)
        remote_seasons = {season.slug: season for season in dw_show.seasons}

        for local_season in seasons_by_show.get(show_id, []):
            season_id = int(local_season["id"])
            remote_season = remote_seasons.get(str(local_season["slug"]))
            remote_records = []
            if remote_season is not None:
                remote_records = _fetch_full_season(
                    client,
                    str(show["slug"]),
                    membership_plan,
                    remote_season.dw_id,
                )
            # The client intentionally represents a failed initial season request
            # as an empty page. Resolve missing local slugs individually below:
            # real request/auth failures then propagate, while genuinely removed
            # episodes may return 404 and retain only migration-safe legacy data.
            records_by_slug = {record.slug: record for record in remote_records}
            for local_episode in episodes_by_season.get(season_id, []):
                slug = str(local_episode["slug"])
                record = records_by_slug.get(slug)
                if record is None:
                    try:
                        record = client.get_episode_details(
                            slug,
                            require_member_exclusive=require_member_exclusive,
                        )
                    except MiddlewareAPIError as exc:
                        if exc.status_code != 404:
                            raise
                        continue
                record = _resolve_possible_trailer(
                    client,
                    record,
                    require_member_exclusive=require_member_exclusive,
                )
                records_by_slug[slug] = record

            remote_by_show_and_season[(show_id, season_id)] = records_by_slug

    # Persist season semantics only after all network reads succeeded.
    for season_id, (kind, number) in season_semantics.items():
        connection.execute(
            sa.update(seasons)
            .where(seasons.c.id == season_id)
            .values(season_type=kind, season_number=number)
        )

    previous_by_episode = _previous_identifiers(connection, metadata_table)

    for show in show_rows:
        show_id = int(show["id"])
        identifier_mode = str(show["episode_identifier"])
        local_rows = episodes_by_show.get(show_id, [])

        counters = {"aux": 0, "trailer": 0}
        for row in local_rows:
            current = str(row["episode_identifier"])
            for kind in counters:
                number = _generated_number(current, kind)
                if number is not None:
                    counters[kind] = max(counters[kind], number)
            previous = previous_by_episode.get(int(row["id"]))
            if previous:
                for kind in counters:
                    number = _generated_number(previous, kind)
                    if number is not None:
                        counters[kind] = max(counters[kind], number)

        used_slots: set[str] = set()
        used_identifiers: set[str] = set()
        current_by_id = {
            int(row["id"]): str(row["episode_identifier"])
            for row in local_rows
        }
        planned: dict[int, str] = {}
        planned_previous: dict[int, str] = {}
        raw_numbers: dict[int, str | None] = {}

        def allocate(kind: str) -> str:
            while True:
                counters[kind] += 1
                candidate = f"{kind}.{counters[kind]}"
                if candidate not in used_identifiers:
                    used_identifiers.add(candidate)
                    return candidate

        for row in local_rows:
            episode_id = int(row["id"])
            season_id = int(row["season_id"])
            current = str(row["episode_identifier"])
            quarantined = current.startswith("not-usable.")
            effective_current = previous_by_episode.get(episode_id, current)
            season_kind, season_number = season_semantics[season_id]
            records = remote_by_show_and_season.get((show_id, season_id), {})
            record = records.get(str(row["slug"]))

            raw_numbers[episode_id] = (
                (record.episode_number or None) if record is not None else None
            )

            desired: str | None = None
            source_slot: str | None = None
            generated_kind: str | None = None
            if record is not None:
                desired, source_slot = _direct_identifier(
                    identifier_mode,
                    season_type=season_kind,
                    season_number=season_number,
                    record=record,
                )
                generated_kind = _generated_type(
                    identifier_mode,
                    season_type=season_kind,
                    record=record,
                )
            else:
                desired = _legacy_fallback_identifier(
                    identifier_mode,
                    season_number=season_number,
                    current_identifier=effective_current,
                )
                if desired is not None and desired.startswith("ep."):
                    source_slot = "legacy:" + desired

            # Quarantine deliberately vacates source-backed identifiers so a
            # replacement can claim them. Keep the repaired previous identifier,
            # but do not reserve its direct source slot during this migration.
            direct_candidate = desired is not None and source_slot is not None
            quarantined_direct = quarantined and direct_candidate

            if desired is not None and not quarantined_direct:
                if source_slot in used_slots or desired in used_identifiers:
                    desired = None
                    generated_kind = "aux"
                else:
                    if source_slot is not None:
                        used_slots.add(source_slot)
                    used_identifiers.add(desired)

            if desired is None:
                if generated_kind is None:
                    if _generated_number(effective_current, "aux") is not None:
                        generated_kind = "aux"
                    elif _generated_number(effective_current, "trailer") is not None:
                        generated_kind = "trailer"
                generated_kind = generated_kind or "aux"
                preserved = _generated_number(effective_current, generated_kind)
                if preserved is not None and effective_current not in used_identifiers:
                    desired = effective_current
                    used_identifiers.add(desired)
                else:
                    desired = allocate(generated_kind)

            if quarantined:
                planned_previous[episode_id] = desired
            else:
                planned[episode_id] = desired

        # Free the unique identifier namespace before assigning repaired values.
        changed_ids = [
            episode_id
            for episode_id, desired in planned.items()
            if current_by_id[episode_id] != desired
        ]
        for episode_id in changed_ids:
            connection.execute(
                sa.update(episodes)
                .where(episodes.c.id == episode_id)
                .values(episode_identifier=f"migration-reindex.{episode_id}")
            )

        for row in local_rows:
            episode_id = int(row["id"])
            values = {"dw_episode_number": raw_numbers[episode_id]}
            if episode_id in planned:
                values["episode_identifier"] = planned[episode_id]
            connection.execute(
                sa.update(episodes)
                .where(episodes.c.id == episode_id)
                .values(**values)
            )

        for episode_id, identifier in planned_previous.items():
            _update_previous_identifier(
                connection,
                metadata_table,
                episode_id,
                identifier,
            )

        # Numbered/seasonal high-water values belonged to the retired allocator.
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
        _set_show_meta(
            connection,
            metadata_table,
            show_id,
            "ep_id.latest_aux_num",
            counters["aux"],
        )
        _set_show_meta(
            connection,
            metadata_table,
            show_id,
            "ep_id.latest_trailer_num",
            counters["trailer"],
        )


_CANONICAL_NUMBERED_EXTRA_RE = re.compile(
    r"^ep-extra[.](?:other|trailer)[.]([0-9]+)[.]([0-9]+)$"
)
_CANONICAL_SEASONAL_MAIN_RE = re.compile(r"^ep[.]S[0-9]+E([0-9]+)$")
_CANONICAL_SEASONAL_EXTRA_RE = re.compile(
    r"^ep-extra[.](?:other|trailer)[.]S[0-9]+E([0-9]+)[.]([0-9]+)$"
)
_LEGACY_NUMBERED_EXTRA_RE = re.compile(r"^ep-extra[.]([0-9]+)[.]([0-9]+)$")
_LEGACY_SEASONAL_MAIN_WITH_SEASON_RE = re.compile(
    r"^ep[.]S([0-9]+)E([0-9]+)$"
)
_LEGACY_SEASONAL_EXTRA_RE = re.compile(
    r"^ep-extra[.]S([0-9]+)E([0-9]+)[.]([0-9]+)$"
)

def _identifier_for_previous_release(
    identifier_mode: str,
    *,
    season_index: int,
    identifier: str,
) -> str:
    """Translate canonical identifiers back to the grammar used by 1.1.0."""
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
            if match := _LEGACY_NUMBERED_MAIN_RE.fullmatch(identifier):
                latest = max(latest, int(match.group(1)))
            elif match := _LEGACY_NUMBERED_EXTRA_RE.fullmatch(identifier):
                parent = int(match.group(1))
                latest = max(latest, parent)
                extras_by_parent[parent] = max(
                    extras_by_parent.get(parent, 0),
                    int(match.group(2)),
                )
        _set_show_meta(connection, metadata_table, show_id, "ep_id.latest_ep_num", latest)
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
        for identifier in identifiers:
            if match := _LEGACY_SEASONAL_MAIN_WITH_SEASON_RE.fullmatch(identifier):
                season_number = int(match.group(1))
                latest_by_season[season_number] = max(
                    latest_by_season.get(season_number, 0),
                    int(match.group(2)),
                )
            elif match := _LEGACY_SEASONAL_EXTRA_RE.fullmatch(identifier):
                season_number = int(match.group(1))
                episode_number = int(match.group(2))
                latest_by_season[season_number] = max(
                    latest_by_season.get(season_number, 0),
                    episode_number,
                )
                latest_extra = max(latest_extra, int(match.group(3)))
        for season_number, latest in latest_by_season.items():
            _set_show_meta(
                connection,
                metadata_table,
                show_id,
                f"ep_id.latest_season_{season_number}_ep",
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
    """Restore the 1.1.0 identifier grammar, then remove the new columns."""
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

    identifiers_by_show: dict[int, list[str]] = defaultdict(list)
    planned: dict[int, str] = {}
    for row in episode_rows:
        show_id = int(row["show_id"])
        desired = _identifier_for_previous_release(
            show_modes[show_id],
            season_index=season_indices[int(row["season_id"])],
            identifier=str(row["episode_identifier"]),
        )
        planned[int(row["id"])] = desired
        identifiers_by_show[show_id].append(desired)

    changed = [
        row
        for row in episode_rows
        if planned[int(row["id"])] != str(row["episode_identifier"])
    ]
    for row in changed:
        episode_id = int(row["id"])
        connection.execute(
            sa.update(episodes)
            .where(episodes.c.id == episode_id)
            .values(episode_identifier=f"migration-downgrade.{episode_id}")
        )
    for row in changed:
        episode_id = int(row["id"])
        connection.execute(
            sa.update(episodes)
            .where(episodes.c.id == episode_id)
            .values(episode_identifier=planned[episode_id])
        )

    previous_by_episode = _previous_identifiers(connection, metadata_table)
    rows_by_id = {int(row["id"]): row for row in episode_rows}
    for episode_id, identifier in previous_by_episode.items():
        row = rows_by_id.get(episode_id)
        if row is None:
            continue
        desired = _identifier_for_previous_release(
            show_modes[int(row["show_id"])],
            season_index=season_indices[int(row["season_id"])],
            identifier=identifier,
        )
        _update_previous_identifier(
            connection,
            metadata_table,
            episode_id,
            desired,
        )

    for show_id, identifier_mode in show_modes.items():
        _restore_previous_allocator_metadata(
            connection,
            metadata_table=metadata_table,
            show_id=show_id,
            identifier_mode=identifier_mode,
            identifiers=identifiers_by_show.get(show_id, []),
        )

    _downgrade_schema()
