from __future__ import annotations

import pytest
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def _make_download(session: Session, *, slug: str):
    import backend.db.models  # noqa: F401
    import task_manager.scheduler.db  # noqa: F401
    from backend.db.models import Episode, LocalMediaProfile, Season, Show
    from backend.db.models.media_download import EpisodeMediaDownload
    from backend.types.download_profile_types import MediaDownloadArtifactStatus
    from backend.types.media_types import MediaType
    from backend.types.show_types import EpisodeIdentifier, ShowType
    from backend.utils.helpers import generate_uuid

    show = Show(
        uuid=f"{slug}-show-uuid",
        slug=f"{slug}-show",
        title="Queue Show",
        description=None,
        sharing_url="https://example.test/show",
        membership_level="FREE",
        type=ShowType.PODCAST.value,
        episode_identifier=EpisodeIdentifier.NUMBERED.value,
        author_name="Host",
        author_slug="host",
    )
    season = Season(show=show, index=1, slug=f"{slug}-season", name="One")
    episode = Episode(
        uuid=generate_uuid(),
        type=MediaType.EPISODE.value,
        show=show,
        season=season,
        index=1,
        episode_identifier="ep.1",
        slug=slug,
        title="Queue Episode",
        duration=100.0,
        publish_status="published_final",
        sharing_url="https://example.test/episode",
    )
    profile = LocalMediaProfile(
        slug=f"{slug}-audio",
        name="Audio",
        output_template="/downloads/{show}/{episode}.ext",
        preferred_format="format_audio_only",
    )
    session.add_all([show, season, episode, profile])
    session.flush()
    download = EpisodeMediaDownload(
        type=MediaType.EPISODE.value,
        media_item_id=episode.id,
        local_media_profile_id=profile.id,
        artifact_status=MediaDownloadArtifactStatus.ABSENT.value,
        file_path=f"/downloads/{slug}.m4a",
    )
    session.add(download)
    session.flush()
    return download


def _session():
    import backend.db.models  # noqa: F401
    import task_manager.scheduler.db  # noqa: F401
    from backend.db import Base
    from task_manager.scheduler.db import TaskDefinition

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    session.add(TaskDefinition(
        key="download_episode",
        title="Download episode media",
        description="",
        allowed_resource_types=["media_download"],
        default_max_retries=2,
    ))
    session.commit()
    return session, engine


def test_queue_positions_use_the_dispatcher_order():
    from task_manager.tasks.media_download_operations import (
        create_media_download_operation,
        get_media_download_queue_positions,
    )

    session, engine = _session()
    try:
        normal_download = _make_download(session, slug="normal")
        first_download = _make_download(session, slug="priority-first")
        second_download = _make_download(session, slug="priority-second")

        create_media_download_operation(session, normal_download)
        first = create_media_download_operation(session, first_download)
        second = create_media_download_operation(session, second_download)

        first_click = datetime(2026, 9, 10, 0, 15, tzinfo=timezone.utc)
        first.prioritized_at = first_click
        second.prioritized_at = first_click + timedelta(seconds=1)
        session.commit()

        assert get_media_download_queue_positions(session) == {
            second_download.id: 1,
            first_download.id: 2,
            normal_download.id: 3,
        }
    finally:
        session.close()
        engine.dispose()



def test_reprioritizing_a_queued_download_moves_it_to_front_of_dispatch_order():
    from task_manager.tasks.media_download_operations import (
        _ordered_queued_media_download_operations,
        create_media_download_operation,
        get_media_download_queue_positions,
        prioritize_media_download_operation,
    )

    session, engine = _session()
    try:
        ordinary = _make_download(session, slug="reprioritize-ordinary")
        first_download = _make_download(session, slug="reprioritize-first")
        second_download = _make_download(session, slug="reprioritize-second")

        create_media_download_operation(session, ordinary)
        first = create_media_download_operation(session, first_download)
        second = create_media_download_operation(session, second_download)

        first.prioritized_at = datetime(2026, 9, 10, 1, 0, tzinfo=timezone.utc)
        second.prioritized_at = first.prioritized_at + timedelta(seconds=1)
        session.flush()

        assert [operation.resource_id for operation in
                _ordered_queued_media_download_operations(session)] == [
            second_download.id, first_download.id, ordinary.id,
        ]

        # Clicking an earlier priority again moves it ahead of the most recent.
        prioritize_media_download_operation(session, first_download.id)
        session.commit()

        assert get_media_download_queue_positions(session) == {
            first_download.id: 1,
            second_download.id: 2,
            ordinary.id: 3,
        }
        assert [operation.resource_id for operation in
                _ordered_queued_media_download_operations(session)] == [
            first_download.id, second_download.id, ordinary.id,
        ]
    finally:
        session.close()
        engine.dispose()


def test_scoped_collection_queue_positions_preserve_global_positions():
    from backend.services.media_download_collection import (
        media_download_queue_positions,
    )
    from task_manager.tasks.media_download_operations import (
        create_media_download_operation,
    )

    session, engine = _session()
    try:
        first_download = _make_download(session, slug="scoped-first")
        second_download = _make_download(session, slug="scoped-second")
        third_download = _make_download(session, slug="scoped-third")

        create_media_download_operation(session, first_download)
        create_media_download_operation(session, second_download)
        create_media_download_operation(session, third_download)
        session.commit()

        assert media_download_queue_positions(
            session,
            [second_download.id, third_download.id],
        ) == {
            second_download.id: 2,
            third_download.id: 3,
        }
    finally:
        session.close()
        engine.dispose()


def test_queue_positions_preserve_creation_order_when_timestamps_tie():
    from task_manager.tasks.media_download_operations import (
        create_media_download_operation,
        get_media_download_queue_positions,
    )

    session, engine = _session()
    try:
        first_download = _make_download(session, slug="bulk-first")
        second_download = _make_download(session, slug="bulk-second")
        third_download = _make_download(session, slug="bulk-third")

        first = create_media_download_operation(session, first_download)
        second = create_media_download_operation(session, second_download)
        third = create_media_download_operation(session, third_download)

        # Dependency fan-out creates all children in one transaction. On SQLite,
        # the server-side created_at values can therefore be identical.
        same_time = datetime(2026, 9, 10, 0, 30, tzinfo=timezone.utc)
        first.created_at = same_time
        second.created_at = same_time
        third.created_at = same_time
        session.commit()

        assert get_media_download_queue_positions(session) == {
            first_download.id: 1,
            second_download.id: 2,
            third_download.id: 3,
        }
    finally:
        session.close()
        engine.dispose()



def test_download_page_uses_dispatcher_queue_order_and_paginates():
    from fastapi import HTTPException

    from backend.api.endpoints.media_downloads.service import get_media_downloads_page
    from task_manager.tasks.media_download_operations import create_media_download_operation

    session, engine = _session()
    try:
        normal_download = _make_download(session, slug="page-normal")
        first_download = _make_download(session, slug="page-priority-first")
        second_download = _make_download(session, slug="page-priority-second")

        create_media_download_operation(session, normal_download)
        first = create_media_download_operation(session, first_download)
        second = create_media_download_operation(session, second_download)

        first_click = datetime(2026, 9, 10, 1, 0, tzinfo=timezone.utc)
        first.prioritized_at = first_click
        second.prioritized_at = first_click + timedelta(seconds=1)
        session.commit()

        first_page = get_media_downloads_page(
            session,
            statuses=["pending"],
            order="workflow",
            cursor=None,
            limit=2,
        )
        assert first_page.total == 3
        assert first_page.facets["pending"] == 3
        assert first_page.actions["cancel"] == 3
        assert first_page.actions["retry"] == 0
        assert first_page.actions["delete-unavailable"] == 3
        assert first_page.has_more is True
        assert first_page.next_cursor is not None
        with pytest.raises(HTTPException, match="Cursor does not match this download collection"):
            get_media_downloads_page(
                session,
                statuses=["downloaded"],
                order="workflow",
                cursor=first_page.next_cursor,
                limit=2,
            )
        assert [item.id for item in first_page.items] == [
            second_download.id,
            first_download.id,
        ]
        assert [item.queue_position for item in first_page.items] == [1, 2]

        second_page = get_media_downloads_page(
            session,
            statuses=["pending"],
            order="workflow",
            cursor=first_page.next_cursor,
            limit=2,
        )
        assert second_page.total == 3
        assert second_page.has_more is False
        assert [item.id for item in second_page.items] == [normal_download.id]
        assert second_page.items[0].queue_position == 3
        assert second_page.revision
    finally:
        session.close()
        engine.dispose()


def test_download_page_filters_status_before_applying_limit():
    from backend.api.endpoints.media_downloads.service import get_media_downloads_page
    from backend.types.download_profile_types import MediaDownloadArtifactStatus

    session, engine = _session()
    try:
        older = _make_download(session, slug="page-downloaded-old")
        newer = _make_download(session, slug="page-not-downloaded-new")
        older.artifact_status = MediaDownloadArtifactStatus.AVAILABLE.value
        session.commit()

        page = get_media_downloads_page(
            session,
            statuses=["downloaded"],
            order="recent",
            cursor=None,
            limit=1,
        )

        assert page.total == 1
        assert page.facets["downloaded"] == 1
        assert page.facets["not_downloaded"] == 1
        assert [item.id for item in page.items] == [older.id]
        assert newer.id not in {item.id for item in page.items}
    finally:
        session.close()
        engine.dispose()


def test_download_page_only_hydrates_requested_rows():
    from sqlalchemy import event

    from backend.api.endpoints.media_downloads.service import get_media_downloads_page
    from backend.db.models.media_download import MediaDownloadBase

    session, engine = _session()
    loaded_download_ids: list[int] = []

    def record_loaded(_session, instance):
        if isinstance(instance, MediaDownloadBase):
            loaded_download_ids.append(instance.id)

    try:
        for index in range(20):
            _make_download(session, slug=f"bounded-page-{index}")
        session.commit()
        session.expunge_all()
        event.listen(session, "loaded_as_persistent", record_loaded)

        page = get_media_downloads_page(
            session,
            statuses=["not_downloaded"],
            order="workflow",
            cursor=None,
            limit=3,
        )

        assert page.total == 20
        assert len(page.items) == 3
        assert set(loaded_download_ids) == {item.id for item in page.items}
    finally:
        event.remove(session, "loaded_as_persistent", record_loaded)
        session.close()
        engine.dispose()


def test_download_page_filters_live_progress_status_in_sql():
    from sqlalchemy import select

    from backend.api.endpoints.media_downloads.service import get_media_downloads_page
    from task_manager.scheduler.db import TaskDefinition, TaskRun
    from task_manager.scheduler.operations import link_run_to_operations, refresh_operation
    from task_manager.scheduler.types import ResourceType, TaskStatus
    from task_manager.tasks.media_download_operations import create_media_download_operation

    session, engine = _session()
    try:
        download = _make_download(session, slug="page-live-progress")
        operation = create_media_download_operation(session, download)
        definition_id = session.scalar(
            select(TaskDefinition.id).where(
                TaskDefinition.key == "download_episode"
            )
        )
        assert definition_id is not None

        run = TaskRun(
            schedule_id=None,
            definition_id=definition_id,
            resource_type=ResourceType.MEDIA_DOWNLOAD,
            resource_id=download.id,
            status=TaskStatus.RUNNING,
            progress=25,
            message="Downloading",
            meta={
                "_progress_meta": {
                    "download": {
                        "phase": "transferring",
                        "main_activity": "media",
                        "primary_transfer_complete": False,
                    },
                },
            },
            result=None,
            attempt_count=1,
            max_retries=2,
            last_error=None,
            next_retry_at=None,
            started_at=datetime.now(timezone.utc),
            finished_at=None,
            runtime_ms=None,
        )
        session.add(run)
        session.flush()
        link_run_to_operations(
            session,
            run=run,
            task_key="download_episode",
            operation_ids=(operation.id,),
            operation_slot=operation.targets[0].slot_key,
        )
        refresh_operation(session, operation.id)
        session.commit()

        downloading = get_media_downloads_page(
            session,
            statuses=["downloading"],
            order="workflow",
            cursor=None,
            limit=3,
        )
        assert [item.id for item in downloading.items] == [download.id]

        run.meta = {
            "_progress_meta": {
                "download": {
                    "phase": "finishing",
                    "main_activity": "embed",
                    "primary_transfer_complete": True,
                },
            },
        }
        session.commit()

        processing = get_media_downloads_page(
            session,
            statuses=["local_processing"],
            order="workflow",
            cursor=None,
            limit=3,
        )
        assert [item.id for item in processing.items] == [download.id]

        run.meta = {
            "_progress_meta": {
                "download": {
                    "phase": "transferring",
                    "main_activity": "media",
                    "primary_transfer_complete": False,
                    "stages": [
                        {
                            "id": "media",
                            "wait": {
                                "reason": "daily_wire_request_cooldown",
                            },
                        },
                    ],
                },
            },
        }
        session.commit()

        waiting = get_media_downloads_page(
            session,
            statuses=["waiting"],
            order="workflow",
            cursor=None,
            limit=3,
        )
        assert [item.id for item in waiting.items] == [download.id]
    finally:
        session.close()
        engine.dispose()



def test_filtered_bulk_action_ids_do_not_depend_on_loaded_pages():
    from backend.api.endpoints.media_downloads.service import (
        get_media_download_bulk_action_ids,
    )
    from backend.types.download_profile_types import MediaDownloadArtifactStatus
    from task_manager.tasks.media_download_operations import create_media_download_operation

    session, engine = _session()
    try:
        queued_one = _make_download(session, slug="bulk-filter-queued-one")
        queued_two = _make_download(session, slug="bulk-filter-queued-two")
        downloaded = _make_download(session, slug="bulk-filter-downloaded")
        create_media_download_operation(session, queued_one)
        create_media_download_operation(session, queued_two)
        downloaded.artifact_status = MediaDownloadArtifactStatus.AVAILABLE.value
        session.commit()

        assert set(get_media_download_bulk_action_ids(
            session,
            statuses=["pending"],
            action="cancel",
        )) == {queued_one.id, queued_two.id}

        assert get_media_download_bulk_action_ids(
            session,
            statuses=["pending"],
            action="retry",
        ) == []

        assert get_media_download_bulk_action_ids(
            session,
            statuses=["downloaded"],
            action="retry",
        ) == [downloaded.id]
    finally:
        session.close()
        engine.dispose()



def test_download_cursor_restarts_when_workflow_revision_changes():
    from backend.api.endpoints.media_downloads.service import get_media_downloads_page
    from backend.types.download_profile_types import MediaDownloadArtifactStatus

    session, engine = _session()
    try:
        oldest = _make_download(session, slug="cursor-oldest")
        boundary = _make_download(session, slug="cursor-boundary")
        newest = _make_download(session, slug="cursor-newest")
        for download, when in (
            (oldest, datetime(2026, 9, 10, 1, 0, tzinfo=timezone.utc)),
            (boundary, datetime(2026, 9, 10, 2, 0, tzinfo=timezone.utc)),
            (newest, datetime(2026, 9, 10, 3, 0, tzinfo=timezone.utc)),
        ):
            download.artifact_status = MediaDownloadArtifactStatus.AVAILABLE.value
            download.downloaded_at = when
        session.commit()

        first = get_media_downloads_page(
            session,
            statuses=["downloaded"],
            order="recent",
            cursor=None,
            limit=2,
        )
        assert [item.id for item in first.items] == [newest.id, boundary.id]
        assert first.next_cursor is not None

        session.delete(newest)
        inserted = _make_download(session, slug="cursor-inserted")
        inserted.artifact_status = MediaDownloadArtifactStatus.AVAILABLE.value
        inserted.downloaded_at = datetime(2026, 9, 10, 4, 0, tzinfo=timezone.utc)
        session.commit()

        changed = get_media_downloads_page(
            session,
            statuses=["downloaded"],
            order="recent",
            cursor=first.next_cursor,
            limit=2,
        )

        # Downloads has mutable workflow state, so any collection revision
        # change deliberately restarts from the head. The frontend sees the
        # revision mismatch and replaces the old page chain.
        assert changed.revision != first.revision
        assert [item.id for item in changed.items] == [inserted.id, boundary.id]
    finally:
        session.close()
        engine.dispose()


def test_download_cursor_ignores_progress_only_updates():
    from sqlalchemy import select

    from backend.api.endpoints.media_downloads.service import get_media_downloads_page
    from task_manager.scheduler.db import TaskDefinition, TaskRun
    from task_manager.scheduler.operations import link_run_to_operations, refresh_operation
    from task_manager.scheduler.types import ResourceType, TaskStatus
    from task_manager.tasks.media_download_operations import create_media_download_operation

    session, engine = _session()
    try:
        active_download = _make_download(session, slug="cursor-progress-active")
        newer = _make_download(session, slug="cursor-progress-newer")
        older = _make_download(session, slug="cursor-progress-older")
        operation = create_media_download_operation(session, active_download)
        definition_id = session.scalar(
            select(TaskDefinition.id).where(TaskDefinition.key == "download_episode")
        )
        assert definition_id is not None

        run = TaskRun(
            schedule_id=None,
            definition_id=definition_id,
            resource_type=ResourceType.MEDIA_DOWNLOAD,
            resource_id=active_download.id,
            status=TaskStatus.RUNNING,
            progress=10,
            message="Downloading",
            meta={"_progress_meta": {"download": {
                "phase": "transferring",
                "main_activity": "media",
                "primary_transfer_complete": False,
            }}},
            result=None,
            attempt_count=1,
            max_retries=2,
            last_error=None,
            next_retry_at=None,
            started_at=datetime.now(timezone.utc),
            finished_at=None,
            runtime_ms=None,
        )
        session.add(run)
        session.flush()
        link_run_to_operations(
            session,
            run=run,
            task_key="download_episode",
            operation_ids=(operation.id,),
            operation_slot=operation.targets[0].slot_key,
        )
        refresh_operation(session, operation.id)
        session.commit()

        def page(cursor=None):
            return get_media_downloads_page(
                session, order="workflow", cursor=cursor, limit=2,
            )

        first_page = page()
        assert first_page.next_cursor is not None
        assert [item.id for item in first_page.items] == [active_download.id, older.id]

        # Both timestamps advance on normal progress reports without changing
        # the status, queue order, or start time of this execution.
        updated = datetime.now(timezone.utc) + timedelta(days=1)
        run.progress = 55
        run.updated_at = updated
        operation.progress = 55
        operation.updated_at = updated
        session.commit()

        next_page = page(first_page.next_cursor)
        assert next_page.revision == first_page.revision
        assert [item.id for item in next_page.items] == [newer.id]
        assert next_page.next_cursor is None

        # A real queue-order change must still invalidate the old cursor.
        queued_operation = create_media_download_operation(session, newer)
        queued_operation.prioritized_at = updated
        session.commit()
        changed = page(first_page.next_cursor)
        assert changed.revision != first_page.revision
        assert [item.id for item in changed.items] == [active_download.id, newer.id]
    finally:
        session.close()
        engine.dispose()


def test_workflow_downloaded_order_uses_latest_download_time_across_pages():
    from backend.api.endpoints.media_downloads.service import get_media_downloads_page
    from backend.types.download_profile_types import MediaDownloadArtifactStatus

    session, engine = _session()
    try:
        old = _make_download(session, slug="workflow-originally-old")
        middle = _make_download(session, slug="workflow-middle")
        new = _make_download(session, slug="workflow-new")
        for download, hour in ((old, 1), (middle, 2), (new, 3)):
            download.artifact_status = MediaDownloadArtifactStatus.AVAILABLE.value
            download.downloaded_at = datetime(2026, 9, 10, hour, tzinfo=timezone.utc)
        session.commit()

        def page(cursor=None):
            return get_media_downloads_page(
                session, statuses=["downloaded"], order="workflow",
                cursor=cursor, limit=2,
            )

        first = page()
        assert [item.id for item in first.items] == [new.id, middle.id]
        assert first.next_cursor is not None
        second = page(first.next_cursor)
        assert [item.id for item in second.items] == [old.id]

        # Re-downloading the oldest record must move it above newer records
        # even though its original ID does not change.
        old.downloaded_at = datetime(2026, 9, 10, 4, tzinfo=timezone.utc)
        session.commit()
        first = page()
        assert [item.id for item in first.items] == [old.id, new.id]
        second = page(first.next_cursor)
        assert [item.id for item in second.items] == [middle.id]
    finally:
        session.close()
        engine.dispose()



def test_workflow_orders_active_downloads_by_execution_start_across_pages():
    from sqlalchemy import select

    from backend.api.endpoints.media_downloads.service import get_media_downloads_page
    from backend.types.download_profile_types import MediaDownloadArtifactStatus
    from task_manager.scheduler.db import TaskDefinition, TaskRun
    from task_manager.scheduler.operations import link_run_to_operations, refresh_operation
    from task_manager.scheduler.types import ResourceType, TaskStatus
    from task_manager.tasks.media_download_operations import create_media_download_operation

    session, engine = _session()
    try:
        # Creation order deliberately disagrees with execution start order.
        last_started = _make_download(session, slug="active-start-last")
        first_started = _make_download(session, slug="active-start-first")
        middle_started = _make_download(session, slug="active-start-middle")
        queued = _make_download(session, slug="active-start-queued")
        completed = _make_download(session, slug="active-start-completed")
        completed.artifact_status = MediaDownloadArtifactStatus.AVAILABLE.value
        completed.downloaded_at = datetime(2026, 9, 10, 5, tzinfo=timezone.utc)

        definition_id = session.scalar(select(TaskDefinition.id).where(
            TaskDefinition.key == "download_episode"
        ))
        assert definition_id is not None

        def start_download(download, hour: int):
            operation = create_media_download_operation(session, download)
            run = TaskRun(
                schedule_id=None,
                definition_id=definition_id,
                resource_type=ResourceType.MEDIA_DOWNLOAD,
                resource_id=download.id,
                status=TaskStatus.RUNNING,
                progress=25,
                message="Downloading",
                meta={"_progress_meta": {"download": {
                    "phase": "transferring",
                    "main_activity": "media",
                    "primary_transfer_complete": False,
                }}},
                result=None,
                attempt_count=1,
                max_retries=2,
                last_error=None,
                next_retry_at=None,
                started_at=datetime(2026, 9, 10, hour, tzinfo=timezone.utc),
                finished_at=None,
                runtime_ms=None,
            )
            session.add(run)
            session.flush()
            link_run_to_operations(
                session,
                run=run,
                task_key="download_episode",
                operation_ids=(operation.id,),
                operation_slot=operation.targets[0].slot_key,
            )
            refresh_operation(session, operation.id)

        start_download(last_started, 4)
        start_download(first_started, 1)
        start_download(middle_started, 2)
        create_media_download_operation(session, queued)
        session.commit()

        def page(cursor=None):
            return get_media_downloads_page(
                session, order="workflow", cursor=cursor, limit=2,
            )

        first_page = page()
        assert [row.id for row in first_page.items] == [
            first_started.id, middle_started.id,
        ]
        second_page = page(first_page.next_cursor)
        assert [row.id for row in second_page.items] == [
            last_started.id, queued.id,
        ]
        final_page = page(second_page.next_cursor)
        assert [row.id for row in final_page.items] == [completed.id]

        # A queued download that begins now joins the end of the active group,
        # regardless of when its media record was created.
        start_download(queued, 6)
        session.commit()
        first_page = page()
        second_page = page(first_page.next_cursor)
        final_page = page(second_page.next_cursor)
        assert [row.id for row in first_page.items] == [
            first_started.id, middle_started.id,
        ]
        assert [row.id for row in second_page.items] == [
            last_started.id, queued.id,
        ]
        assert [row.id for row in final_page.items] == [completed.id]
    finally:
        session.close()
        engine.dispose()
