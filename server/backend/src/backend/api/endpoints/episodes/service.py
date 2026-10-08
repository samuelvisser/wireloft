from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Sequence

from sqlalchemy.orm import Session
from backend.services.custom_indexes import request_show_custom_index_reconciliation
from sqlalchemy import and_, case, func, or_, select

from fastapi import HTTPException

from backend.db.model_mapping import create_database_fields, update_database_fields
from backend.api.models.episode import *
from backend.api.pagination import InvalidCursorError, decode_cursor, encode_cursor, keyset_after, KeysetField
from backend.db.models import Show
from backend.db.models.media_item import Episode
from backend.db.models.media_download import EpisodeMediaDownload
from backend.types.episode_types import EpisodePublishStatus
from backend.services.episode_download_delay import episode_download_delay_ready_at
from backend.utils.episode_publication_timing import (
    record_publication_lifecycle_observation,
)
from task_manager.events.transactional import queue_event
from task_manager.scheduler.operations import (
    OperationTargetSpec,
    create_operation,
    queue_operation_target_dispatch,
)


@dataclass(frozen=True)
class _EpisodeAPIReadSource:
    episode: Episode
    download_delay_passed: bool
    download_delay_ready_at: datetime | None


METADATA_REFRESH_REQUESTED_EVENT = "episode.metadata_refresh_requested"
_METADATA_REFRESH_TASK_KEY = "refresh_episode_metadata"
_EARLY_DELETE_TASK_KEY = "monitor_no_usable_media_episode"


def _episode_api_read(episode: Episode) -> EpisodeAPIRead:
    ready_at = episode_download_delay_ready_at(episode)
    return EpisodeAPIRead.model_validate(_EpisodeAPIReadSource(
        episode=episode,
        download_delay_passed=(
            ready_at is None
            or ready_at <= datetime.now(timezone.utc)
        ),
        download_delay_ready_at=ready_at,
    ))


def _episodes_for_show_stmt(show_slug: str):
    return (
        select(Episode)
        .join(Show, Episode.show_id == Show.id)
        .where(Show.slug == show_slug)
        .order_by(Episode.published_date.desc())
    )


def get_episodes_by_show_list(s: Session, show_slug: str, limit: int | None = None) -> list[EpisodeAPIRead]:
    # Join directly through the indexed show slug rather than using Episode.show.has(), which
    # produces a correlated EXISTS predicate. This keeps the full-list query simple while
    # preserving the existing endpoint contract for callers that need complete episode records.
    stmt = _episodes_for_show_stmt(show_slug)
    if limit is not None:
        stmt = stmt.limit(limit)
    episodes: Sequence[Episode] = s.scalars(stmt).all()

    return [_episode_api_read(episode) for episode in episodes]


def _episode_view_stmt(show_slug: str, season_id: int | None = None):
    # The show grid needs only a small subset of Episode. Selecting those columns directly avoids
    # constructing full ORM entities (and their select-in metadata relationship), then sending and
    # validating descriptions/timestamps that the grid never renders.
    stmt = (
        select(
            Episode.id.label("id"),
            Episode.show_id.label("show_id"),
            Episode.season_id.label("season_id"),
            Episode.index.label("index"),
            Episode.episode_identifier.label("episode_identifier"),
            Episode.dw_episode_number.label("dw_episode_number"),
            Episode.publish_status.label("publish_status"),
            Episode.title.label("title"),
            Episode.slug.label("slug"),
            Episode.thumbnail_landscape_path.label("thumbnail_landscape_path"),
            Episode.thumbnail_portrait_path.label("thumbnail_portrait_path"),
            Episode.thumbnail_square_path.label("thumbnail_square_path"),
            Episode.published_date.label("published_date"),
        )
        .join(Show, Episode.show_id == Show.id)
        .where(Show.slug == show_slug)
    )
    if season_id is not None:
        stmt = stmt.where(Episode.season_id == season_id)
        return stmt.order_by(Episode.index.asc(), Episode.id.asc())
    return stmt.order_by(Episode.published_date.desc().nulls_last(), Episode.id.desc())


def get_episode_views_by_show_list(
        s: Session,
        show_slug: str,
        limit: int | None = None,
) -> list[EpisodeAPIReadView]:
    """Return compact rows for internal callers that still need a simple list."""
    stmt = _episode_view_stmt(show_slug)
    if limit is not None:
        stmt = stmt.limit(limit)

    return [
        EpisodeAPIReadView.model_validate(row)
        for row in s.execute(stmt).mappings().all()
    ]


def get_episode_views_by_show_page(
        s: Session,
        show_slug: str,
        *,
        cursor: str | None,
        limit: int,
        season_id: int | None = None,
) -> EpisodeAPIReadViewPage:
    """Return one stable cursor page of compact episodes for a show."""
    show_count_stmt = (
        select(func.count(Episode.id))
        .join(Show, Episode.show_id == Show.id)
        .where(Show.slug == show_slug)
    )
    show_total = int(s.scalar(show_count_stmt) or 0)
    total = (
        show_total
        if season_id is None
        else int(s.scalar(show_count_stmt.where(Episode.season_id == season_id)) or 0)
    )
    revision_stmt = (
        select(func.max(case(
            (Episode.updated_at > Episode.created_at, Episode.updated_at),
            else_=None,
        )))
        .join(Show, Episode.show_id == Show.id)
        .where(Show.slug == show_slug)
    )
    if season_id is not None:
        revision_stmt = revision_stmt.where(Episode.season_id == season_id)
    latest_ordering_change = s.scalar(revision_stmt)
    revision = (
        latest_ordering_change.isoformat()
        if latest_ordering_change is not None
        else ""
    )

    stmt = _episode_view_stmt(show_slug, season_id)
    if cursor:
        try:
            values = decode_cursor(cursor)
            if (
                values.get("kind") != "show-episodes"
                or values.get("show_slug") != show_slug
                or values.get("season_id") != season_id
            ):
                raise InvalidCursorError("Cursor does not match this episode collection")
            cursor_id = values.get("id")
            if not isinstance(cursor_id, int) or isinstance(cursor_id, bool):
                raise InvalidCursorError("Invalid episode cursor id")

            # Episode dates/indexes can be corrected by metadata refreshes. A
            # changed revision means the old sort boundary is no longer safe;
            # restart at the head and let the generic frontend replace the old
            # page chain immediately.
            if values.get("revision") == revision:
                if season_id is not None:
                    cursor_index = values.get("index")
                    if not isinstance(cursor_index, int) or isinstance(cursor_index, bool):
                        raise InvalidCursorError("Invalid episode cursor index")
                    stmt = stmt.where(keyset_after([
                        KeysetField(Episode.index, cursor_index),
                        KeysetField(Episode.id, cursor_id),
                    ]))
                else:
                    published_raw = values.get("published_at")
                    if published_raw is not None and not isinstance(published_raw, str):
                        raise InvalidCursorError("Invalid episode cursor date")
                    published_at = (
                        datetime.fromisoformat(published_raw)
                        if published_raw is not None
                        else None
                    )
                    if published_at is None:
                        stmt = stmt.where(
                            Episode.published_date.is_(None),
                            Episode.id < cursor_id,
                        )
                    else:
                        stmt = stmt.where(or_(
                            Episode.published_date < published_at,
                            and_(
                                Episode.published_date == published_at,
                                Episode.id < cursor_id,
                            ),
                            Episode.published_date.is_(None),
                        ))
        except (InvalidCursorError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    rows = s.execute(stmt.limit(limit + 1)).mappings().all()
    has_more = len(rows) > limit
    rows = rows[:limit]
    items = [EpisodeAPIReadView.model_validate(row) for row in rows]

    next_cursor = None
    if has_more and rows:
        last = rows[-1]
        values: dict[str, object] = {
            "kind": "show-episodes",
            "show_slug": show_slug,
            "season_id": season_id,
            "revision": revision,
            "id": last["id"],
        }
        if season_id is not None:
            values["index"] = last["index"]
        else:
            published_at = last["published_date"]
            values["published_at"] = (
                published_at.isoformat() if published_at is not None else None
            )
        next_cursor = encode_cursor(values)

    return EpisodeAPIReadViewPage(
        items=items,
        limit=limit,
        total=total,
        show_total=show_total,
        next_cursor=next_cursor,
        revision=revision,
    )


def get_recently_indexed_episodes(
        s: Session,
        *,
        limit: int,
) -> list[EpisodeIndexedActivityAPIRead]:
    """Return the newest episode records by the time WireLoft indexed them."""
    rows = s.execute(
        select(
            Episode.id.label("id"),
            Episode.title.label("title"),
            Episode.slug.label("slug"),
            Episode.created_at.label("indexed_at"),
            Show.title.label("show_title"),
            Show.slug.label("show_slug"),
        )
        .select_from(Episode)
        .join(Show, Episode.show_id == Show.id)
        .order_by(Episode.created_at.desc(), Episode.id.desc())
        .limit(limit)
    ).mappings().all()

    return [
        EpisodeIndexedActivityAPIRead.model_validate(row)
        for row in rows
    ]


def get_episode(s: Session, episode_slug: str) -> EpisodeAPIRead:
    episode = (
        s.query(Episode)
        .filter_by(slug=episode_slug)
        .one_or_none()
    )

    if episode is None:
        raise HTTPException(status_code=404, detail="Episode not found")

    return _episode_api_read(episode)


def queue_episode_metadata_refresh(
        s: Session,
        episode: Episode,
) -> None:
    """Persist unfinished metadata state and queue the normal refresh worker."""
    episode.metadata_is_final = False
    queue_event(s, METADATA_REFRESH_REQUESTED_EVENT, {
        "resource_id": episode.id,
        "id": episode.id,
        "slug": episode.slug,
        "show_id": episode.show_id,
        "refresh": True,
    })


def request_episode_metadata_refresh(
        s: Session,
        episode_slug: str,
) -> dict[str, bool | int | str]:
    episode = (
        s.query(Episode)
        .filter_by(slug=episode_slug)
        .one_or_none()
    )
    if episode is None:
        raise HTTPException(status_code=404, detail="Episode not found")

    target = OperationTargetSpec(
        task_key=_METADATA_REFRESH_TASK_KEY,
        resource_type="episode",
        resource_id=episode.id,
        task_kwargs={"refresh": True},
    )
    show = episode.show
    operation = create_operation(
        s,
        kind="episode.refresh_metadata",
        resource_type="episode",
        resource_id=episode.id,
        title=episode.title,
        targets=[target],
        context={
            "episode_slug": episode.slug,
            "episode_title": episode.title,
            "show_id": episode.show_id,
            "show_slug": show.slug if show is not None else None,
            "show_title": show.title if show is not None else None,
        },
    )
    if queue_operation_target_dispatch(s, operation.id, target.resolved_slot_key()):
        episode.metadata_is_final = False
    s.flush()
    return {
        "queued": True,
        "episode_id": episode.id,
        "operation_id": operation.id,
    }


def request_episode_early_delete(
        s: Session,
        episode_slug: str,
) -> dict[str, bool | str]:
    """Queue an immediate no-usable-media verification for a confirmed missing episode."""
    episode = (
        s.query(Episode)
        .filter_by(slug=episode_slug)
        .one_or_none()
    )
    if episode is None:
        raise HTTPException(status_code=404, detail="Episode not found")
    if not episode.early_delete_available:
        raise HTTPException(
            status_code=409,
            detail="Early Delete is only available after Daily Wire has returned 404 for this episode",
        )

    show = episode.show
    target = OperationTargetSpec(
        task_key=_EARLY_DELETE_TASK_KEY,
        resource_type="show",
        resource_id=episode.show_id,
        task_kwargs={
            "episode_id": episode.id,
            "force": True,
        },
        slot_key=f"{_EARLY_DELETE_TASK_KEY}:episode:{episode.id}:force",
    )
    operation = create_operation(
        s,
        kind="episode.early_delete",
        resource_type="episode",
        resource_id=episode.id,
        title=episode.title,
        targets=[target],
        context={
            "episode_slug": episode.slug,
            "episode_title": episode.title,
            "show_id": episode.show_id,
            "show_slug": show.slug if show is not None else None,
            "show_title": show.title if show is not None else None,
        },
    )
    queue_operation_target_dispatch(s, operation.id, target.resolved_slot_key())
    s.flush()
    return {
        "queued": True,
        "operation_id": operation.id,
    }


def create_episode(s: Session, body: EpisodeAPICreate) -> EpisodeAPIRead:
    episode = create_database_fields(Episode, body)
    s.add(episode)
    s.flush()

    record_publication_lifecycle_observation(
        episode,
        old_status=None,
        new_status=EpisodePublishStatus(episode.publish_status),
    )

    queue_event(s, "episode.added", {
        "resource_id": episode.id,
        "id": episode.id,
        "slug": episode.slug,
        "show_id": episode.show_id,
        "status": episode.publish_status
    })
    request_show_custom_index_reconciliation(s, episode.show_id)

    return _episode_api_read(episode)


def update_episode(s: Session, episode_slug: str, body: EpisodeAPIUpdate) -> EpisodeAPIRead:
    episode: Optional[Episode] = (
        s.query(Episode)
        .filter_by(slug=episode_slug)
        .one_or_none()
    )
    if episode is None:
        raise HTTPException(status_code=404, detail="Episode not found")

    old_status = episode.publish_status

    # Apply updates and flush; commit in router
    update_database_fields(episode, body)
    s.flush()

    # Emit status-specific events if status changed
    if hasattr(body, 'publish_status') and body.publish_status is not None and body.publish_status != old_status:
        new_status = EpisodePublishStatus(body.publish_status)
        record_publication_lifecycle_observation(
            episode,
            old_status=old_status,
            new_status=new_status,
        )

        event_data = {
            "old_status": old_status,
            "status": body.publish_status,
            "resource_id": episode.id,
            "id": episode.id,
            "slug": episode.slug,
            "show_id": episode.show_id,
        }
        queue_event(s, "episode.status_updated", event_data)

        if new_status is EpisodePublishStatus.PUBLISHED_FINAL:
            queue_event(s, "episode.published_final", event_data)
        elif new_status is EpisodePublishStatus.PUBLISHED_WITH_COUNTDOWN:
            queue_event(s, "episode.published_with_countdown", event_data)

    request_show_custom_index_reconciliation(s, episode.show_id)
    return _episode_api_read(episode)


def delete_episode(s: Session, episode_slug: str) -> EpisodeAPIRead:
    episode = (
        s.query(Episode)
        .filter_by(slug=episode_slug)
        .one_or_none()
    )
    if episode is None:
        raise HTTPException(status_code=404, detail="Episode not found")

    payload = _episode_api_read(episode)

    media_download = s.scalar(
        select(EpisodeMediaDownload.id).where(
            EpisodeMediaDownload.media_item_id == episode.id,
        ).limit(1)
    )
    if media_download is not None:
        raise HTTPException(
            status_code=409,
            detail="This episode owns persistent download history and can only be removed with its show",
        )

    queue_event(s, "episode.deleted", {
        "resource_id": episode.id,
        "id": episode.id,
        "slug": episode.slug,
        "show_id": episode.show_id
    })
    request_show_custom_index_reconciliation(s, episode.show_id)

    s.delete(episode)
    s.flush()
    return payload
