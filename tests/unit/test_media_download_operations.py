from __future__ import annotations

from sqlalchemy import create_engine
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


def test_system_download_operation_is_live_visible_but_preacknowledged():
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
        assert operation.notification_seen_at is not None
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
    from task_manager.scheduler.db import TaskRun
    from task_manager.scheduler.types import OperationSource, TaskStatus
    from task_manager.tasks import media_download_operations

    session, engine = _session()
    try:
        first = _make_download(session, slug="reserved-delete")
        second = _make_download(session, slug="waiting-delete")
        first_operation = media_download_operations.create_media_download_operation(
            session,
            first,
            source=OperationSource.SYSTEM.value,
        )
        second_operation = media_download_operations.create_media_download_operation(
            session,
            second,
            source=OperationSource.SYSTEM.value,
        )

        # Avoid touching a real APScheduler instance in this relationship test.
        monkeypatch.setattr(
            "task_manager.scheduler.scheduler.cancel_pending_resource_jobs",
            lambda resources: 0,
        )
        dispatched = []
        monkeypatch.setattr(
            media_download_operations,
            "on_media_download_task_terminal",
            lambda **_: dispatched.append(True),
        )

        # The relationship listener resolves callbacks from the registry, whose
        # registered callback object predates the monkeypatch above. Replace the
        # task metadata callback directly for this test.
        from task_manager.scheduler.registry import get_task
        task_meta, _ = get_task("download_episode")
        original_callback = task_meta.terminal_callback
        task_meta.terminal_callback = lambda **_: dispatched.append(True)
        try:
            run = TaskRun(
                definition_id=session.scalar(
                    __import__("sqlalchemy").select(
                        __import__("task_manager.scheduler.db", fromlist=["TaskDefinition"]).TaskDefinition.id
                    ).where(
                        __import__("task_manager.scheduler.db", fromlist=["TaskDefinition"]).TaskDefinition.key
                        == "download_episode"
                    )
                ),
                resource_type="media_download",
                resource_id=first.id,
                status=TaskStatus.SCHEDULED,
                progress=0,
                attempt_count=0,
                max_retries=2,
            )
            session.add(run)
            session.flush()
            first_operation.targets[0].run_links.append(
                __import__("task_manager.scheduler.db", fromlist=["TaskOperationRun"]).TaskOperationRun(
                    operation_id=first_operation.id,
                    target_id=first_operation.targets[0].id,
                    task_run_id=run.id,
                )
            )
            session.commit()

            assert second_operation.status == "QUEUED"
            session.delete(first)
            session.commit()
            assert dispatched
        finally:
            task_meta.terminal_callback = original_callback
    finally:
        session.close()
        engine.dispose()
