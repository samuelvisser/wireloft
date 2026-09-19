"""Refresh historical episode identifiers from The Daily Wire."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass
import re
from urllib.parse import urlparse

from sqlalchemy import select

from backend.db.core import get_session
from backend.db.datetime_types import utc_datetime
from backend.db.models import Metadata, Show
from backend.db.models.media_item import Episode
from dailywire_api.dw_api.client import (
    ByNextPage,
    ByShowSeason,
    MiddlewareAPIError,
    MiddlewareClient,
)
from dailywire_api.records import DwEpisodeRecord
from dailywire_authorisation import DeviceAuthClient


key = "episode_indexing_semantics"
upstream_key = None
title = "Refresh episode indexing from The Daily Wire"


_OFFICIAL_TRAILER_RE = re.compile(r"\bofficial\s+trailer\b", re.IGNORECASE)
_TRAILER_RE = re.compile(r"\btrailer\b", re.IGNORECASE)
_GENERATED_RE = re.compile(r"^(aux|trailer)\.(\d+)$")
_NUMBERED_MAIN_RE = re.compile(r"^ep\.(\d+)$")
_NUMBERED_EXTRA_RE = re.compile(
    r"^ep-extra\.(?:other|trailer)\.(\d+)\.(\d+)$"
)
_SEASONAL_MAIN_RE = re.compile(r"^ep\.(S\d+E\d+)$")
_SEASONAL_EXTRA_RE = re.compile(
    r"^ep-extra\.(?:other|trailer)\.(S\d+E\d+)\.(\d+)$"
)
_PREVIOUS_IDENTIFIER_KEY = "no_usable_media.previous_identifier"


@dataclass(frozen=True)
class LocalSeason:
    id: int
    slug: str
    season_type: str
    season_number: int


@dataclass(frozen=True)
class LocalEpisode:
    id: int
    season_id: int
    index: int
    slug: str
    identifier: str
    previous_identifier: str | None


@dataclass(frozen=True)
class LocalShow:
    id: int
    slug: str
    sharing_url: str
    membership_level: str
    identifier_mode: str
    seasons: tuple[LocalSeason, ...]
    episodes: tuple[LocalEpisode, ...]
    latest_aux_num: int
    latest_trailer_num: int


@dataclass(frozen=True)
class EpisodePlan:
    episode_id: int
    identifier: str | None
    previous_identifier: str | None
    dw_episode_number: str | None
    update_dw_episode_number: bool


@dataclass(frozen=True)
class ShowPlan:
    show_id: int
    episodes: tuple[EpisodePlan, ...]
    latest_aux_num: int
    latest_trailer_num: int


def _is_dailywire_url(value: str) -> bool:
    host = (urlparse(value).hostname or "").lower()
    return host == "dailywire.com" or host.endswith(".dailywire.com")


def _membership_plan(value: str) -> str:
    return "FREE" if value == "WL_ANY" else value


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


def _is_trailer(record: DwEpisodeRecord) -> bool:
    return (
        record.is_trailer is True
        or bool(_OFFICIAL_TRAILER_RE.search(record.title or ""))
    )


def _resolve_possible_trailer(
    client: MiddlewareClient,
    record: DwEpisodeRecord,
    *,
    require_member_exclusive: bool,
) -> DwEpisodeRecord:
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


def _date_identifier(record: DwEpisodeRecord) -> str:
    published = utc_datetime(record.published_date)
    return "ep." + published.strftime("%Y-%m-%dT%H:%M:%S.%f")


def _direct_identifier(
    identifier_mode: str,
    *,
    season_type: str,
    season_number: int,
    record: DwEpisodeRecord,
) -> tuple[str | None, str | None]:
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

    if segment == 0:
        if _is_trailer(record):
            return None, None
        if identifier_mode == "numbered":
            return f"ep.{number}", f"{number}.0"
        if identifier_mode == "seasonal":
            return (
                f"ep.S{season_number:02d}E{number:02d}",
                f"S{season_number:02d}E{number:02d}.0",
            )

    if segment > 0:
        extra_type = "trailer" if _is_trailer(record) else "other"
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
    record: DwEpisodeRecord,
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


def _generated_number(identifier: str, expected_type: str) -> int | None:
    match = _GENERATED_RE.fullmatch(identifier)
    if not match or match.group(1) != expected_type:
        return None
    return int(match.group(2))


def _source_slot(identifier: str) -> str | None:
    if match := _NUMBERED_MAIN_RE.fullmatch(identifier):
        return f"{int(match.group(1))}.0"
    if match := _NUMBERED_EXTRA_RE.fullmatch(identifier):
        return f"{int(match.group(1))}.{int(match.group(2))}"
    if match := _SEASONAL_MAIN_RE.fullmatch(identifier):
        return match.group(1) + ".0"
    if match := _SEASONAL_EXTRA_RE.fullmatch(identifier):
        return f"{match.group(1)}.{int(match.group(2))}"
    if identifier.startswith("ep.") and "T" in identifier:
        return "identifier:" + identifier
    return None


def _show_ids() -> list[int]:
    session = get_session()
    try:
        return list(session.scalars(select(Show.id).order_by(Show.id)))
    finally:
        session.close()


def _load_show(show_id: int) -> LocalShow | None:
    session = get_session()
    try:
        show = session.get(Show, show_id)
        if show is None:
            return None

        seasons = tuple(
            LocalSeason(
                id=season.id,
                slug=season.slug,
                season_type=season.season_type,
                season_number=season.season_number,
            )
            for season in sorted(show.seasons, key=lambda value: value.index)
        )
        ordered_episodes = sorted(
            show.episodes,
            key=lambda value: (value.index, value.id),
        )
        previous_by_episode = {
            int(parent_id): str(value)
            for parent_id, value in session.execute(
                select(Metadata.parent_id, Metadata.value).where(
                    Metadata.parent_table == "media_items_episode",
                    Metadata.parent_id.in_(
                        select(Episode.id).where(Episode.show_id == show_id)
                    ),
                    Metadata.key == _PREVIOUS_IDENTIFIER_KEY,
                )
            )
        }
        episodes = tuple(
            LocalEpisode(
                id=episode.id,
                season_id=episode.season_id,
                index=episode.index,
                slug=episode.slug,
                identifier=episode.episode_identifier,
                previous_identifier=previous_by_episode.get(episode.id),
            )
            for episode in ordered_episodes
        )

        def meta_int(key_name: str) -> int:
            value = show.get_meta(key_name)
            try:
                return int(value) if value is not None else 0
            except ValueError:
                return 0

        return LocalShow(
            id=show.id,
            slug=show.slug,
            sharing_url=show.sharing_url,
            membership_level=show.membership_level,
            identifier_mode=show.episode_identifier,
            seasons=seasons,
            episodes=episodes,
            latest_aux_num=meta_int("ep_id.latest_aux_num"),
            latest_trailer_num=meta_int("ep_id.latest_trailer_num"),
        )
    finally:
        session.close()


def _fetch_full_season(
    client: MiddlewareClient,
    show_slug: str,
    membership_plan: str,
    season_dw_id: str,
) -> list[DwEpisodeRecord]:
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

    by_slug: dict[str, DwEpisodeRecord] = {}
    for record in records:
        by_slug.setdefault(record.slug, record)
    return list(by_slug.values())


def _fetch_remote_records(
    client: MiddlewareClient,
    local_show: LocalShow,
) -> dict[int, dict[str, DwEpisodeRecord]]:
    membership_plan = _membership_plan(local_show.membership_level)
    require_member_exclusive = membership_plan != "FREE"
    show_page = client.get_show_page(
        local_show.slug,
        membership_plan=membership_plan,
    )
    remote_seasons = {season.slug: season for season in show_page.seasons}
    local_episodes_by_season: dict[int, list[LocalEpisode]] = defaultdict(list)
    for episode in local_show.episodes:
        local_episodes_by_season[episode.season_id].append(episode)

    result: dict[int, dict[str, DwEpisodeRecord]] = {}
    for season in local_show.seasons:
        remote_season = remote_seasons.get(season.slug)
        records: list[DwEpisodeRecord] = []
        if remote_season is not None:
            records = _fetch_full_season(
                client,
                local_show.slug,
                membership_plan,
                remote_season.dw_id,
            )

        by_slug: dict[str, DwEpisodeRecord] = {}
        for record in records:
            by_slug[record.slug] = _resolve_possible_trailer(
                client,
                record,
                require_member_exclusive=require_member_exclusive,
            )

        for local_episode in local_episodes_by_season.get(season.id, []):
            if local_episode.slug in by_slug:
                continue
            try:
                by_slug[local_episode.slug] = client.get_episode_details(
                    local_episode.slug,
                    require_member_exclusive=require_member_exclusive,
                )
            except MiddlewareAPIError as exc:
                if exc.status_code != 404:
                    raise

        result[season.id] = by_slug

    return result


def _plan_show(
    local_show: LocalShow,
    remote_by_season: dict[int, dict[str, DwEpisodeRecord]],
) -> ShowPlan:
    season_by_id = {season.id: season for season in local_show.seasons}
    counters = {
        "aux": local_show.latest_aux_num,
        "trailer": local_show.latest_trailer_num,
    }
    reserved_generated: set[str] = set()

    for episode in local_show.episodes:
        for identifier in (episode.identifier, episode.previous_identifier):
            if not identifier:
                continue
            for kind in ("aux", "trailer"):
                number = _generated_number(identifier, kind)
                if number is not None:
                    counters[kind] = max(counters[kind], number)
                    reserved_generated.add(identifier)

    preplanned: dict[int, tuple[str, str | None, str | None, str | None]] = {}
    # tuple: (kind, desired_identifier, source_slot, generated_type)
    for episode in local_show.episodes:
        season = season_by_id[episode.season_id]
        record = remote_by_season.get(season.id, {}).get(episode.slug)
        effective = (
            episode.previous_identifier
            if episode.identifier.startswith("not-usable.")
            and episode.previous_identifier is not None
            else episode.identifier
        )

        if record is None:
            preplanned[episode.id] = ("preserve", effective, _source_slot(effective), None)
            continue

        desired, source_slot = _direct_identifier(
            local_show.identifier_mode,
            season_type=season.season_type,
            season_number=season.season_number,
            record=record,
        )
        generated_type = _generated_type(
            local_show.identifier_mode,
            season_type=season.season_type,
            record=record,
        )
        if desired is not None:
            preplanned[episode.id] = ("direct", desired, source_slot, None)
        else:
            preplanned[episode.id] = (
                "generated",
                None,
                None,
                generated_type or "aux",
            )

    final_source_owner: dict[str, int] = {}
    for episode in local_show.episodes:
        if episode.identifier.startswith("not-usable."):
            continue
        kind, desired, source_slot, _generated = preplanned[episode.id]
        current_slot = _source_slot(episode.identifier)
        if kind == "preserve" and current_slot is not None:
            final_source_owner.setdefault(current_slot, episode.id)
        elif kind == "direct" and source_slot is not None and current_slot == source_slot:
            final_source_owner.setdefault(source_slot, episode.id)

    for episode in local_show.episodes:
        if episode.identifier.startswith("not-usable."):
            continue
        kind, _desired, source_slot, _generated = preplanned[episode.id]
        if kind != "direct" or source_slot is None:
            continue
        final_source_owner.setdefault(source_slot, episode.id)

    final_identifiers: set[str] = {
        episode.identifier
        for episode in local_show.episodes
        if episode.identifier.startswith("not-usable.")
    }

    def allocate(kind: str) -> str:
        while True:
            counters[kind] += 1
            candidate = f"{kind}.{counters[kind]}"
            if candidate not in reserved_generated and candidate not in final_identifiers:
                reserved_generated.add(candidate)
                final_identifiers.add(candidate)
                return candidate

    plans: list[EpisodePlan] = []
    for episode in local_show.episodes:
        season = season_by_id[episode.season_id]
        record = remote_by_season.get(season.id, {}).get(episode.slug)
        quarantined = episode.identifier.startswith("not-usable.")
        effective = (
            episode.previous_identifier
            if quarantined and episode.previous_identifier is not None
            else episode.identifier
        )
        kind, desired, source_slot, generated_type = preplanned[episode.id]

        if kind == "preserve":
            final = effective
        elif kind == "direct":
            if (
                not quarantined
                and source_slot is not None
                and final_source_owner.get(source_slot) != episode.id
            ):
                final = allocate("aux")
            else:
                assert desired is not None
                final = desired
        else:
            generated_type = generated_type or "aux"
            preserved_number = _generated_number(effective, generated_type)
            if (
                preserved_number is not None
                and effective not in final_identifiers
            ):
                final = effective
                final_identifiers.add(final)
            else:
                final = allocate(generated_type)

        if not quarantined:
            if final in final_identifiers and final != episode.identifier:
                final = allocate("aux")
            final_identifiers.add(final)

        plans.append(
            EpisodePlan(
                episode_id=episode.id,
                identifier=None if quarantined else final,
                previous_identifier=final if quarantined else None,
                dw_episode_number=(
                    record.episode_number or None
                    if record is not None
                    else None
                ),
                update_dw_episode_number=record is not None,
            )
        )

    return ShowPlan(
        show_id=local_show.id,
        episodes=tuple(plans),
        latest_aux_num=counters["aux"],
        latest_trailer_num=counters["trailer"],
    )


def _remove_show_meta(show: Show, key: str) -> None:
    for item in list(show.meta_items):
        if item.key == key:
            show.meta_items.remove(item)


def _apply_show_plan(plan: ShowPlan) -> None:
    from task_manager.tasks.helpers.episodes.events import (
        queue_episode_identifier_changed_event,
    )

    session = get_session()
    try:
        show = session.get(Show, plan.show_id)
        if show is None:
            return

        episodes = {
            episode.id: episode
            for episode in session.scalars(
                select(Episode).where(Episode.show_id == plan.show_id)
            )
        }
        changed_identifiers: dict[int, str] = {}
        for episode_plan in plan.episodes:
            episode = episodes.get(episode_plan.episode_id)
            if episode is None:
                continue
            if episode_plan.identifier is not None and episode.episode_identifier != episode_plan.identifier:
                changed_identifiers[episode.id] = episode.episode_identifier
                episode.episode_identifier = f"background-indexing.{episode.id}"
            if episode_plan.update_dw_episode_number:
                episode.dw_episode_number = episode_plan.dw_episode_number

        session.flush()

        for episode_plan in plan.episodes:
            episode = episodes.get(episode_plan.episode_id)
            if episode is None:
                continue

            if episode_plan.identifier is not None and episode.id in changed_identifiers:
                episode.episode_identifier = episode_plan.identifier

            if episode_plan.previous_identifier is not None:
                episode.set_meta(
                    _PREVIOUS_IDENTIFIER_KEY,
                    episode_plan.previous_identifier,
                )

        session.flush()

        for episode_id, old_identifier in changed_identifiers.items():
            episode = episodes[episode_id]
            queue_episode_identifier_changed_event(
                session,
                episode=episode,
                old_episode_identifier=old_identifier,
            )

        for key_name in (
            "ep_id.latest_ep_num",
            "ep_id.latest_ep_extra_num",
        ):
            _remove_show_meta(show, key_name)
        for item in list(show.meta_items):
            if item.key.startswith("ep_id.latest_season_") and item.key.endswith("_ep"):
                show.meta_items.remove(item)

        show.set_meta("ep_id.latest_aux_num", str(plan.latest_aux_num))
        show.set_meta("ep_id.latest_trailer_num", str(plan.latest_trailer_num))
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _build_client(shows: list[LocalShow]) -> MiddlewareClient:
    tokens = DeviceAuthClient().get_token()
    requires_token = any(
        _membership_plan(show.membership_level) != "FREE"
        for show in shows
    )
    if requires_token and tokens is None:
        raise RuntimeError(
            "A Daily Wire access token is required to refresh member-only "
            "episode identifiers."
        )
    return MiddlewareClient(access_token=tokens.access_token if tokens else None)


async def migrate(context) -> None:
    shows = [
        show
        for show_id in _show_ids()
        if (show := _load_show(show_id)) is not None
        and _is_dailywire_url(show.sharing_url)
    ]
    if not shows:
        return

    client = _build_client(shows)
    total = len(shows)

    for index, local_show in enumerate(shows, start=1):
        context.raise_if_cancelled()
        context.update_progress(
            index - 1,
            total,
            f"Refreshing episode identifiers for {local_show.slug}",
        )

        remote_by_season = await asyncio.to_thread(
            _fetch_remote_records,
            client,
            local_show,
        )
        context.raise_if_cancelled()

        plan = _plan_show(local_show, remote_by_season)
        _apply_show_plan(plan)

        context.update_progress(
            index,
            total,
            f"Refreshed episode identifiers for {local_show.slug}",
        )
