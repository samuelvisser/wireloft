"""Restore show-level auxiliary classification for Daily Wire segments .20+.

Revision ID: 9d4b7e2c1a63
Revises: f6a1c3d8b427
"""

from __future__ import annotations

import re

from sqlalchemy import select

from backend.db.core import get_session
from backend.db.models import Metadata, Show
from backend.db.models.media_item import Episode


revision = "9d4b7e2c1a63"
down_revision = "f6a1c3d8b427"
title = "Restore high-segment auxiliary episode classification"


_SHOW_AUX_SEGMENT_START = 20
_PREVIOUS_IDENTIFIER_KEY = "no_usable_media.previous_identifier"
_EP_EXTRA_RE = re.compile(r"^ep-extra\.(other|trailer)\.")
_GENERATED_RE = re.compile(r"^(aux|trailer)\.(\d+)$")


def _segment(raw_episode_number: str | None) -> int:
    value = (raw_episode_number or "").strip()
    if "." not in value:
        return 0
    try:
        return int(value.split(".", 1)[1])
    except ValueError:
        return 0


def _generated_type(identifier: str) -> str | None:
    match = _EP_EXTRA_RE.match(identifier)
    if match is None:
        return None
    return "trailer" if match.group(1) == "trailer" else "aux"


def _generated_number(identifier: str, expected_type: str) -> int | None:
    match = _GENERATED_RE.fullmatch(identifier)
    if match is None or match.group(1) != expected_type:
        return None
    return int(match.group(2))


def _show_ids() -> list[int]:
    session = get_session()
    try:
        return list(session.scalars(select(Show.id).order_by(Show.id)))
    finally:
        session.close()


def _repair_show(show_id: int) -> int:
    from task_manager.tasks.helpers.episodes.events import (
        queue_episode_identifier_changed_event,
    )

    session = get_session()
    try:
        show = session.get(Show, show_id)
        if show is None:
            return 0

        episodes = list(
            session.scalars(
                select(Episode)
                .where(Episode.show_id == show_id)
                .order_by(Episode.index, Episode.id)
            )
        )
        previous_items = {
            int(item.parent_id): item
            for item in session.scalars(
                select(Metadata).where(
                    Metadata.parent_table == "media_items_episode",
                    Metadata.parent_id.in_(
                        select(Episode.id).where(Episode.show_id == show_id)
                    ),
                    Metadata.key == _PREVIOUS_IDENTIFIER_KEY,
                )
            )
        }

        def meta_int(key: str) -> int:
            value = show.get_meta(key)
            try:
                return int(value) if value is not None else 0
            except ValueError:
                return 0

        counters = {
            "aux": meta_int("ep_id.latest_aux_num"),
            "trailer": meta_int("ep_id.latest_trailer_num"),
        }
        reserved = {episode.episode_identifier for episode in episodes}
        reserved.update(item.value for item in previous_items.values())

        for identifier in reserved:
            for generated_type in ("aux", "trailer"):
                number = _generated_number(identifier, generated_type)
                if number is not None:
                    counters[generated_type] = max(
                        counters[generated_type],
                        number,
                    )

        def allocate(generated_type: str) -> str:
            while True:
                counters[generated_type] += 1
                candidate = f"{generated_type}.{counters[generated_type]}"
                if candidate not in reserved:
                    reserved.add(candidate)
                    return candidate

        changed_active: list[tuple[Episode, str]] = []
        changed_count = 0

        for episode in episodes:
            if _segment(episode.dw_episode_number) < _SHOW_AUX_SEGMENT_START:
                continue

            if episode.episode_identifier.startswith("not-usable."):
                previous = previous_items.get(episode.id)
                if previous is None:
                    continue
                generated_type = _generated_type(previous.value)
                if generated_type is None:
                    continue
                previous.value = allocate(generated_type)
                changed_count += 1
                continue

            generated_type = _generated_type(episode.episode_identifier)
            if generated_type is None:
                continue

            old_identifier = episode.episode_identifier
            episode.episode_identifier = allocate(generated_type)
            changed_active.append((episode, old_identifier))
            changed_count += 1

        if changed_count == 0:
            return 0

        session.flush()

        for episode, old_identifier in changed_active:
            queue_episode_identifier_changed_event(
                session,
                episode=episode,
                old_episode_identifier=old_identifier,
            )

        show.set_meta("ep_id.latest_aux_num", str(counters["aux"]))
        show.set_meta("ep_id.latest_trailer_num", str(counters["trailer"]))
        session.commit()
        return changed_count
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def migrate(context) -> None:
    show_ids = _show_ids()
    total = len(show_ids)
    if total == 0:
        return

    for index, show_id in enumerate(show_ids, start=1):
        context.raise_if_cancelled()
        context.update_progress(
            index - 1,
            total,
            f"Repairing high-segment auxiliary content for show {show_id}",
        )
        _repair_show(show_id)
        context.update_progress(
            index,
            total,
            f"Repaired high-segment auxiliary content for show {show_id}",
        )
