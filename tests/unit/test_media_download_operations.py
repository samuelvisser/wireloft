from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session


def _make_download(session: Session, *, slug: str = "episode-1"):
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
        title="Operation Show",
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
        title="Operation Episode",
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
    session.add(TaskDefinition(
        key="download_movie",
        title="Download movie media",
        description="",
        allowed_resource_types=["media_download"],
        default_max_retries=2,
    ))
    session.commit()
    return session, engine


def test_media_download_operation_is_the_live_execution_owner():
    from task_manager.scheduler.types import OperationSource
    from task_manager.tasks.media_download_operations import create_media_download_operation

    session, engine = _session()
    try:
        download = _make_download(session)
        operation = create_media_download_operation(
            session,
            download,
            source=OperationSource.UI.value,
        )
        session.commit()

        assert operation.kind == "media.download"
        assert operation.resource_type == "media_download"
        assert operation.resource_id == download.id
        assert operation.source == "UI"
        assert operation.progress == 0
        assert operation.prioritized_at is not None
        assert operation.context["media_download_id"] == download.id
        assert operation.context["episode_slug"] == download.media.slug
        assert len(operation.targets) == 1
        target = operation.targets[0]
        assert target.task_key == "download_episode"
        assert target.resource_type == "media_download"
        assert target.resource_id == download.id
        assert target.recover_on_restart is False

        # MediaDownload is pure domain/artifact state; none of the worker
        # lifecycle fields that TaskRun owns remain on the mapped model.
        for legacy_field in (
            "download_status",
            "progress",
            "error_message",
            "started_at",
            "finished_at",
            "attempt_generation",
        ):
            assert not hasattr(download, legacy_field)
    finally:
        session.close()
        engine.dispose()


def test_system_download_operation_uses_durable_completion_acknowledgement():
    from task_manager.scheduler.types import OperationSource
    from task_manager.tasks.media_download_operations import create_media_download_operation

    session, engine = _session()
    try:
        download = _make_download(session, slug="system-episode")
        operation = create_media_download_operation(
            session,
            download,
            source=OperationSource.SYSTEM.value,
        )
        session.commit()

        assert operation.status == "QUEUED"
        assert operation.prioritized_at is None
        # System/API work does not need a toast, but its terminal state must stay
        # discoverable until a frontend invalidates the ordinary domain queries.
        assert operation.notification_seen_at is None
    finally:
        session.close()
        engine.dispose()


def test_ui_request_promotes_existing_system_queued_download():
    from task_manager.scheduler.db import TaskOperation
    from task_manager.scheduler.types import OperationSource
    from task_manager.tasks.media_download_operations import create_media_download_operation

    session, engine = _session()
    try:
        download = _make_download(session, slug="promoted")
        background = create_media_download_operation(
            session,
            download,
            source=OperationSource.SYSTEM.value,
        )
        assert background.prioritized_at is None

        manual = create_media_download_operation(
            session,
            download,
            source=OperationSource.UI.value,
        )

        assert manual.id == background.id
        assert manual.prioritized_at is not None
        assert session.query(TaskOperation).count() == 1
    finally:
        session.close()
        engine.dispose()


def test_manual_download_jumps_ahead_of_background_queue(monkeypatch):
    from task_manager.scheduler.types import OperationSource
    from task_manager.tasks import media_download_operations

    session, engine = _session()
    try:
        background_download = _make_download(session, slug="background")
        manual_download = _make_download(session, slug="manual")
        background = media_download_operations.create_media_download_operation(
            session,
            background_download,
            source=OperationSource.SYSTEM.value,
        )
        manual = media_download_operations.create_media_download_operation(
            session,
            manual_download,
            source=OperationSource.UI.value,
        )
        session.commit()

        dispatched: list[str] = []

        def capture_dispatch(_session: Session, operation) -> bool:
            dispatched.append(operation.id)
            return True

        monkeypatch.setattr(media_download_operations, "_reserve_target_dispatch", capture_dispatch)

        assert media_download_operations.dispatch_queued_media_download_operations(session, budget=2) == 2
        assert dispatched == [manual.id, background.id]
    finally:
        session.close()
        engine.dispose()


def test_prioritize_queued_download_records_the_click_time():
    from task_manager.tasks.media_download_operations import (
        create_media_download_operation,
        prioritize_media_download_operation,
    )

    session, engine = _session()
    try:
        download = _make_download(session, slug="priority-time")
        operation = create_media_download_operation(session, download)
        before = datetime.now(timezone.utc)

        prioritized = prioritize_media_download_operation(session, download.id)
        after = datetime.now(timezone.utc)

        assert prioritized.id == operation.id
        assert prioritized.prioritized_at is not None
        assert before <= prioritized.prioritized_at <= after

        first_click = prioritized.prioritized_at
        prioritize_media_download_operation(session, download.id)
        assert prioritized.prioritized_at is not None
        assert prioritized.prioritized_at >= first_click
    finally:
        session.close()
        engine.dispose()


def test_prioritized_downloads_dispatch_first_in_click_order(monkeypatch):
    from task_manager.tasks import media_download_operations

    session, engine = _session()
    try:
        normal_download = _make_download(session, slug="normal")
        first_download = _make_download(session, slug="priority-first")
        second_download = _make_download(session, slug="priority-second")
        normal = media_download_operations.create_media_download_operation(session, normal_download)
        first = media_download_operations.create_media_download_operation(session, first_download)
        second = media_download_operations.create_media_download_operation(session, second_download)

        first_click = datetime(2026, 9, 10, 0, 15, tzinfo=timezone.utc)
        first.prioritized_at = first_click
        second.prioritized_at = first_click + timedelta(seconds=1)
        session.commit()

        dispatched: list[str] = []

        def capture_dispatch(_session: Session, operation) -> bool:
            dispatched.append(operation.id)
            return True

        monkeypatch.setattr(media_download_operations, "_reserve_target_dispatch", capture_dispatch)

        assert media_download_operations.dispatch_queued_media_download_operations(session, budget=3) == 3
        assert dispatched == [first.id, second.id, normal.id]
    finally:
        session.close()
        engine.dispose()


def test_deleting_media_download_cascades_its_operation_graph():
    from task_manager.scheduler.db import TaskOperation, TaskOperationTarget
    from task_manager.scheduler.types import OperationSource
    from task_manager.tasks.media_download_operations import create_media_download_operation

    session, engine = _session()
    try:
        download = _make_download(session, slug="delete-episode")
        operation = create_media_download_operation(
            session,
            download,
            source=OperationSource.UI.value,
        )
        operation_id = operation.id
        session.commit()

        assert session.get(TaskOperation, operation_id) is not None
        assert session.query(TaskOperationTarget).filter_by(operation_id=operation_id).count() == 1

        session.delete(download)
        session.commit()

        assert session.get(TaskOperation, operation_id) is None
        assert session.query(TaskOperationTarget).filter_by(operation_id=operation_id).count() == 0
    finally:
        session.close()
        engine.dispose()


def test_deleting_reserved_download_releases_its_queue_slot(monkeypatch):
    import task_manager.tasks  # noqa: F401 - register download task metadata
    from task_manager.scheduler.db import TaskDefinition, TaskOperationRun, TaskRun
    from task_manager.scheduler.registry import get_task
    from task_manager.scheduler.types import OperationSource, ResourceType, TaskStatus
    from task_manager.tasks.media_download_operations import create_media_download_operation

    session, engine = _session()
    try:
        download = _make_download(session, slug="reserved-delete")
        operation = create_media_download_operation(
            session,
            download,
            source=OperationSource.SYSTEM.value,
        )
        definition_id = session.scalar(
            select(TaskDefinition.id).where(TaskDefinition.key == "download_episode")
        )
        assert definition_id is not None

        run = TaskRun(
            definition_id=definition_id,
            resource_type=ResourceType.MEDIA_DOWNLOAD,
            resource_id=download.id,
            status=TaskStatus.SCHEDULED,
            progress=0,
            attempt_count=0,
            max_retries=2,
        )
        session.add(run)
        session.flush()
        session.add(TaskOperationRun(
            operation_id=operation.id,
            target_id=operation.targets[0].id,
            task_run_id=run.id,
        ))
        session.commit()

        monkeypatch.setattr(
            "task_manager.scheduler.scheduler.cancel_pending_resource_jobs",
            lambda resources: 0,
        )
        callbacks: list[bool] = []
        task_meta, _ = get_task("download_episode")
        original_callback = task_meta.terminal_callback
        task_meta.terminal_callback = lambda **_: callbacks.append(True)
        try:
            session.delete(download)
            session.commit()
            assert callbacks == [True]
        finally:
            task_meta.terminal_callback = original_callback
    finally:
        session.close()
        engine.dispose()
