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
        sharing_url=f"https://example.test/show/{slug}",
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
        description="",
        duration=100.0,
        publish_status="published_final",
        sharing_url=f"https://example.test/episode/{slug}",
    )
    profile = LocalMediaProfile(
        slug=f"{slug}-audio",
        name=f"Audio {slug}",
        output_template=f"/downloads/{slug}/{{ show }}/{{ episode }}.ext",
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


def _session(*, autoflush: bool = True):
    import backend.db.models  # noqa: F401
    import task_manager.scheduler.db  # noqa: F401
    from backend.db import Base
    from task_manager.scheduler.db import TaskDefinition

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine, autoflush=autoflush)
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
    from backend.db.models.media_download import MediaDownloadHistory
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

        history = (
            session.query(MediaDownloadHistory)
            .filter_by(media_download_id=download.id)
            .order_by(MediaDownloadHistory.id)
            .all()
        )
        assert [entry.action for entry in history] == ["queued", "prioritized"]
        assert history[0].event_metadata["operation_id"] == operation.id
        assert history[1].event_metadata["operation_id"] == operation.id

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


def test_episode_api_delay_readiness_and_manual_redownload_intent_use_safe_delay(monkeypatch):
    from backend.api.endpoints.episodes.service import _episode_api_read
    from backend.api.endpoints.media_downloads.service import create_episode_download
    from backend.api.models.media_download import EpisodeDownloadAPICreate
    from backend.db.models import Episode
    from backend.utils.episode_publication_timing import record_published_final_observation
    from config import get_settings

    session, engine = _session()
    try:
        settings = get_settings().download_settings
        monkeypatch.setattr(settings, "automatic_episode_download_delay_minutes", 10)
        monkeypatch.setattr(settings, "ensure_safe_delay", True)

        download = _make_download(session, slug="manual-safe-delay")
        episode = session.get(Episode, download.media_item_id)
        assert episode is not None
        episode.published_date = datetime.now(timezone.utc) - timedelta(hours=1)
        record_published_final_observation(
            episode,
            observed_at=datetime.now(timezone.utc) - timedelta(minutes=2),
        )
        session.flush()

        assert _episode_api_read(episode).download_delay_passed is False

        requested = create_episode_download(
            session,
            episode.slug,
            EpisodeDownloadAPICreate(
                local_media_profile_id=download.local_media_profile_id,
                redownload_when_delay_passed=True,
            ),
        )
        assert requested.id == download.id
        assert requested.redownload_when_delay_passed is True

        record_published_final_observation(
            episode,
            observed_at=datetime.now(timezone.utc) - timedelta(minutes=20),
        )
        # The first observation is durable, so advance it explicitly to model an
        # episode whose delay has already elapsed.
        from backend.utils.episode_publication_timing import (
            RECORDED_PUBLISHED_FINAL_META_KEY,
            encode_recorded_published_final,
        )
        episode.set_meta(
            RECORDED_PUBLISHED_FINAL_META_KEY,
            encode_recorded_published_final(
                datetime.now(timezone.utc) - timedelta(minutes=20)
            ),
        )
        requested.redownload_when_delay_passed = False
        session.flush()

        assert _episode_api_read(episode).download_delay_passed is True
        requested = create_episode_download(
            session,
            episode.slug,
            EpisodeDownloadAPICreate(
                local_media_profile_id=download.local_media_profile_id,
                redownload_when_delay_passed=True,
            ),
        )
        assert requested.redownload_when_delay_passed is False
    finally:
        session.close()
        engine.dispose()


def test_manual_unsafe_download_followup_waits_until_delay_passes(monkeypatch):
    from backend.db.models import Episode
    from backend.utils.episode_publication_timing import record_published_final_observation
    from config import get_settings
    from task_manager.scheduler.operations import operation_admission_wait_state
    from task_manager.scheduler.types import OperationStatus
    from task_manager.tasks.media_download_operations import (
        get_active_media_download_operation,
        queue_episode_redownload_if_ready,
    )

    session, engine = _session()
    try:
        settings = get_settings().download_settings
        monkeypatch.setattr(settings, "automatic_episode_download_delay_minutes", 10)
        monkeypatch.setattr(settings, "ensure_safe_delay", True)

        download = _make_download(session, slug="manual-safe-delay-followup")
        episode = session.get(Episode, download.media_item_id)
        assert episode is not None
        observed_final = datetime.now(timezone.utc) - timedelta(minutes=2)
        record_published_final_observation(episode, observed_at=observed_final)
        download.redownload_when_delay_passed = True
        session.flush()

        assert queue_episode_redownload_if_ready(session, download.id) is True

        operation = get_active_media_download_operation(session, download.id)
        assert operation is not None
        assert operation.status == OperationStatus.WAITING.value
        wait_state = operation_admission_wait_state(operation)
        assert wait_state is not None
        assert wait_state["reason"] == "publication_delay"
        assert wait_state["until"] == observed_final + timedelta(minutes=10)
        assert download.redownload_when_delay_passed is False
    finally:
        session.close()
        engine.dispose()


def test_system_download_operation_waits_without_reserving_capacity(monkeypatch):
    from config import get_settings
    from backend.db.models.media_download import MediaDownloadHistory
    from task_manager.scheduler.db import TaskRun
    from task_manager.scheduler.operations import operation_admission_wait_state
    from task_manager.scheduler.types import OperationSource, OperationStatus
    from task_manager.tasks import media_download_operations

    session, engine = _session(autoflush=False)
    try:
        download = _make_download(session, slug="publication-wait")
        ready_at = datetime.now(timezone.utc) + timedelta(minutes=10)
        operation = media_download_operations.create_media_download_operation(
            session,
            download,
            source=OperationSource.SYSTEM.value,
            not_before=ready_at,
        )

        scheduled: list[tuple[str, datetime]] = []
        monkeypatch.setattr(
            media_download_operations,
            "_schedule_delayed_media_download_dispatch",
            lambda operation_id, *, run_at: scheduled.append((operation_id, run_at)),
        )

        dispatched = media_download_operations.dispatch_queued_media_download_operations(session)

        assert operation.status == OperationStatus.WAITING.value
        assert operation_admission_wait_state(operation)["reason"] == "publication_delay"
        assert session.query(TaskRun).count() == 0
        assert dispatched == 0
        assert scheduled == [(operation.id, ready_at)]
        history = session.query(MediaDownloadHistory).filter_by(
            media_download_id=download.id,
            action="queued",
        ).one()
        assert history.event_metadata["publication_delay_not_before"] == ready_at.isoformat()
        assert media_download_operations.remaining_media_download_budget(session) == (
            get_settings().download_settings.max_concurrent_downloads
        )
        session.commit()
    finally:
        session.close()
        engine.dispose()


def test_expired_publication_wait_enters_normal_download_queue(monkeypatch):
    from task_manager.scheduler.db import TaskRun
    from task_manager.scheduler.types import OperationSource, OperationStatus, TaskStatus
    from task_manager.tasks import media_download_operations

    session, engine = _session()
    try:
        download = _make_download(session, slug="publication-ready")
        operation = media_download_operations.create_media_download_operation(
            session,
            download,
            source=OperationSource.SYSTEM.value,
            not_before=datetime.now(timezone.utc) + timedelta(minutes=10),
        )
        media_download_operations.set_media_download_operation_not_before(
            session,
            download.id,
            datetime.now(timezone.utc) - timedelta(seconds=1),
        )
        monkeypatch.setattr(
            media_download_operations,
            "queue_task_after_commit",
            lambda *args, **kwargs: None,
        )

        dispatched = media_download_operations.dispatch_queued_media_download_operations(session)

        assert operation.status == OperationStatus.QUEUED.value
        assert dispatched == 1
        run = session.query(TaskRun).one()
        assert run.status == TaskStatus.SCHEDULED
        session.commit()
    finally:
        session.close()
        engine.dispose()


def test_explicit_download_releases_automatic_publication_wait(monkeypatch):
    from config import get_settings
    from task_manager.scheduler.operations import operation_admission_wait_state
    from task_manager.scheduler.types import OperationSource, OperationStatus
    from task_manager.tasks.media_download_operations import create_media_download_operation

    monkeypatch.setattr(
        get_settings().download_settings,
        "ensure_safe_delay",
        True,
    )
    session, engine = _session()
    try:
        download = _make_download(session, slug="manual-bypass")
        background = create_media_download_operation(
            session,
            download,
            source=OperationSource.SYSTEM.value,
            not_before=datetime.now(timezone.utc) + timedelta(minutes=10),
        )
        assert background.status == OperationStatus.WAITING.value

        manual = create_media_download_operation(
            session,
            download,
            source=OperationSource.UI.value,
        )

        assert manual.id == background.id
        assert manual.status == OperationStatus.QUEUED.value
        assert manual.prioritized_at is not None
        assert operation_admission_wait_state(manual) is None

        # A concurrent automatic profile reconciliation cannot re-apply the
        # safety delay after the user explicitly chose to start the download.
        create_media_download_operation(
            session,
            download,
            source=OperationSource.SYSTEM.value,
            not_before=datetime.now(timezone.utc) + timedelta(minutes=10),
        )
        assert manual.status == OperationStatus.QUEUED.value
        assert operation_admission_wait_state(manual) is None
    finally:
        session.close()
        engine.dispose()


def test_operation_restart_bypasses_publication_wait(monkeypatch):
    from task_manager.scheduler.operations import OperationSnapshot, operation_admission_wait_state
    from task_manager.scheduler.types import OperationSource, OperationStatus
    from task_manager.tasks import media_download_operations

    session, engine = _session()
    try:
        download = _make_download(session, slug="restart-bypass")
        operation = media_download_operations.create_media_download_operation(
            session,
            download,
            source=OperationSource.SYSTEM.value,
            not_before=datetime.now(timezone.utc) + timedelta(minutes=10),
        )
        operation_id = operation.id
        session.commit()

        restarted = OperationSnapshot(
            id=operation_id,
            kind="media.download",
            source="SYSTEM",
            resource_type="media_download",
            resource_id=download.id,
            title=operation.title,
            status=OperationStatus.QUEUED.value,
            progress=0,
            completion_progress=0,
            progress_current=0,
            progress_total=1,
            message="Restarting",
            result=None,
            context=operation.context,
            progress_meta=None,
            error=None,
            notification_seen_at=None,
            started_at=None,
            finished_at=None,
            created_at=None,
            updated_at=None,
        )
        monkeypatch.setattr(
            media_download_operations,
            "get_session",
            lambda: Session(engine),
        )
        monkeypatch.setattr(
            media_download_operations,
            "restart_task_operation",
            lambda _operation_id: restarted,
        )

        media_download_operations.restart_media_download_operation(operation_id)

        session.expire_all()
        operation = session.get(type(operation), operation_id)
        assert operation is not None
        assert operation_admission_wait_state(operation) is None
        assert operation.context["publication_delay_bypassed"] is True
    finally:
        session.close()
        engine.dispose()


def test_operation_history_dedupes_per_task_run_not_forever():
    from backend.db.models.media_download import MediaDownloadHistory
    from backend.services.media_download_history import (
        record_media_download_operation_history_once,
    )
    from backend.types.media_download_history_types import MediaDownloadHistoryAction

    session, engine = _session()
    try:
        download = _make_download(session, slug="history-dedupe")
        session.commit()

        first = record_media_download_operation_history_once(
            session,
            download.id,
            MediaDownloadHistoryAction.CANCELLED,
            operation_ids=("operation-1",),
            metadata={"operation_id": "operation-1", "task_run_id": 10},
        )
        duplicate = record_media_download_operation_history_once(
            session,
            download.id,
            MediaDownloadHistoryAction.CANCELLED,
            operation_ids=("operation-1",),
            metadata={"operation_id": "operation-1", "task_run_id": 10},
        )
        second_attempt = record_media_download_operation_history_once(
            session,
            download.id,
            MediaDownloadHistoryAction.CANCELLED,
            operation_ids=("operation-1",),
            metadata={"operation_id": "operation-1", "task_run_id": 11},
        )
        session.commit()

        assert first is not None
        assert duplicate is not None
        assert second_attempt is not None
        assert duplicate.id == first.id
        assert second_attempt.id != first.id
        assert session.query(MediaDownloadHistory).filter_by(
            media_download_id=download.id,
            action=MediaDownloadHistoryAction.CANCELLED,
        ).count() == 2
    finally:
        session.close()
        engine.dispose()


def test_running_download_interrupted_by_restart_is_recorded_in_history():
    from backend.db.models.media_download import MediaDownloadHistory
    from backend.services.media_download_history import record_media_download_history
    from backend.types.media_download_history_types import MediaDownloadHistoryAction
    from task_manager.scheduler.db import TaskDefinition, TaskOperationRun, TaskRun
    from task_manager.scheduler.types import ResourceType, TaskStatus
    from task_manager.tasks.media_download_operations import (
        create_media_download_operation,
        record_interrupted_media_download_run_history,
    )

    session, engine = _session()
    try:
        download = _make_download(session, slug="restart-history")
        operation = create_media_download_operation(session, download)
        definition_id = session.scalar(
            select(TaskDefinition.id).where(TaskDefinition.key == "download_episode")
        )
        assert definition_id is not None

        started_at = datetime(2026, 9, 26, 0, 52, 44, tzinfo=timezone.utc)
        run = TaskRun(
            definition_id=definition_id,
            resource_type=ResourceType.MEDIA_DOWNLOAD,
            resource_id=download.id,
            status=TaskStatus.RUNNING,
            progress=26,
            attempt_count=1,
            max_retries=2,
            started_at=started_at,
            meta={"inputs": {"is_redownload": False}},
        )
        session.add(run)
        session.flush()
        session.add(TaskOperationRun(
            operation_id=operation.id,
            target_id=operation.targets[0].id,
            task_run_id=run.id,
        ))
        record_media_download_history(
            session,
            download.id,
            MediaDownloadHistoryAction.STARTED,
            metadata={
                "operation_ids": [operation.id],
                "task_run_id": run.id,
                "is_redownload": False,
            },
            occurred_at=started_at,
        )
        session.commit()

        interrupted_at = started_at + timedelta(minutes=8, seconds=23)
        assert record_interrupted_media_download_run_history(
            session,
            [run],
            occurred_at=interrupted_at,
        ) == 1
        session.commit()

        history = (
            session.query(MediaDownloadHistory)
            .filter_by(media_download_id=download.id)
            .order_by(MediaDownloadHistory.id)
            .all()
        )
        assert [entry.action for entry in history] == [
            MediaDownloadHistoryAction.QUEUED,
            MediaDownloadHistoryAction.STARTED,
            MediaDownloadHistoryAction.INTERRUPTED,
        ]
        interruption = history[-1]
        assert interruption.occurred_at == interrupted_at
        assert interruption.event_metadata["task_run_id"] == run.id
        assert interruption.event_metadata["operation_id"] == operation.id
        assert interruption.event_metadata["duration_ms"] == 503_000
        assert interruption.event_metadata["reason"] == "Canceled due to premature shutdown"
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


def test_dispatch_budget_cannot_exceed_configured_concurrency(monkeypatch):
    from types import SimpleNamespace

    from task_manager.tasks import media_download_operations

    session, engine = _session()
    try:
        first = _make_download(session, slug="budget-first")
        second = _make_download(session, slug="budget-second")
        media_download_operations.create_media_download_operation(session, first)
        media_download_operations.create_media_download_operation(session, second)
        session.commit()

        monkeypatch.setattr(
            media_download_operations,
            "get_settings",
            lambda: SimpleNamespace(
                download_settings=SimpleNamespace(max_concurrent_downloads=1),
            ),
        )

        dispatched: list[str] = []

        def capture_dispatch(_session: Session, operation) -> bool:
            dispatched.append(operation.id)
            return True

        monkeypatch.setattr(
            media_download_operations,
            "_reserve_target_dispatch",
            capture_dispatch,
        )

        assert media_download_operations.dispatch_queued_media_download_operations(
            session,
            budget=10,
        ) == 1
        assert len(dispatched) == 1
        session.commit()
    finally:
        session.close()
        engine.dispose()


def test_concurrent_dispatchers_cannot_double_reserve_download_slots(tmp_path, monkeypatch):
    import threading
    from types import SimpleNamespace

    import backend.db.models  # noqa: F401
    import task_manager.scheduler.db  # noqa: F401
    from backend.db import Base
    from task_manager.scheduler.db import TaskDefinition, TaskRun
    from task_manager.scheduler.types import TaskStatus
    from task_manager.tasks import media_download_operations

    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'download-dispatch.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)

    setup = Session(engine)
    try:
        setup.add_all([
            TaskDefinition(
                key="download_episode",
                title="Download episode media",
                description="",
                allowed_resource_types=["media_download"],
                default_max_retries=2,
            ),
            TaskDefinition(
                key="download_movie",
                title="Download movie media",
                description="",
                allowed_resource_types=["media_download"],
                default_max_retries=2,
            ),
        ])
        first = _make_download(setup, slug="concurrent-first")
        second = _make_download(setup, slug="concurrent-second")
        media_download_operations.create_media_download_operation(setup, first)
        media_download_operations.create_media_download_operation(setup, second)
        setup.commit()
    finally:
        setup.close()

    monkeypatch.setattr(
        media_download_operations,
        "get_settings",
        lambda: SimpleNamespace(
            download_settings=SimpleNamespace(max_concurrent_downloads=1),
        ),
    )
    monkeypatch.setattr(
        "task_manager.scheduler.scheduler.trigger_now",
        lambda **_kwargs: "download-job",
    )

    first_reserved = threading.Event()
    allow_first_commit = threading.Event()
    second_started = threading.Event()
    second_finished = threading.Event()
    results: list[tuple[str, int]] = []
    errors: list[BaseException] = []

    def first_dispatcher():
        session = Session(engine)
        try:
            results.append((
                "first",
                media_download_operations.dispatch_queued_media_download_operations(session),
            ))
            first_reserved.set()
            assert allow_first_commit.wait(2)
            session.commit()
        except BaseException as exc:
            errors.append(exc)
            session.rollback()
        finally:
            session.close()

    def second_dispatcher():
        assert first_reserved.wait(2)
        session = Session(engine)
        try:
            second_started.set()
            results.append((
                "second",
                media_download_operations.dispatch_queued_media_download_operations(session),
            ))
            session.commit()
        except BaseException as exc:
            errors.append(exc)
            session.rollback()
        finally:
            session.close()
            second_finished.set()

    first_thread = threading.Thread(target=first_dispatcher)
    second_thread = threading.Thread(target=second_dispatcher)
    first_thread.start()
    second_thread.start()

    assert first_reserved.wait(2)
    assert second_started.wait(2)
    # The second dispatcher must remain blocked until the transaction containing
    # the first reservation commits; otherwise both can observe the same slot.
    assert not second_finished.wait(0.1)
    allow_first_commit.set()

    first_thread.join(2)
    second_thread.join(2)
    assert not first_thread.is_alive()
    assert not second_thread.is_alive()
    assert errors == []
    assert sorted(results) == [("first", 1), ("second", 0)]

    session = Session(engine)
    try:
        active_runs = session.query(TaskRun).filter(
            TaskRun.status.in_(
                (
                    TaskStatus.SCHEDULED,
                    TaskStatus.QUEUED,
                    TaskStatus.RUNNING,
                    TaskStatus.RETRY_SCHEDULED,
                )
            )
        ).count()
        assert active_runs == 1
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


def test_deleting_parent_show_cascades_download_and_operation_graph():
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
        download_id = download.id
        show = download.media.show
        session.commit()

        assert session.get(TaskOperation, operation_id) is not None
        assert session.query(TaskOperationTarget).filter_by(operation_id=operation_id).count() == 1

        session.delete(show)
        session.commit()

        assert session.get(type(download), download_id) is None
        assert session.get(TaskOperation, operation_id) is None
        assert session.query(TaskOperationTarget).filter_by(operation_id=operation_id).count() == 0
    finally:
        session.close()
        engine.dispose()


def test_deleting_parent_show_releases_reserved_download_queue_slot(monkeypatch):
    from task_manager.tasks import load_all_tasks

    load_all_tasks()
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
            session.delete(download.media.show)
            session.commit()
            assert callbacks == [True]
        finally:
            task_meta.terminal_callback = original_callback
    finally:
        session.close()
        engine.dispose()


def test_episode_with_any_media_download_can_only_be_removed_with_show():
    import pytest
    from fastapi import HTTPException

    from backend.api.endpoints.episodes.service import delete_episode
    from backend.db.models.media_download import MediaDownloadBase

    session, engine = _session()
    try:
        download = _make_download(session, slug="persistent-history")
        download_id = download.id
        episode_slug = download.media.slug
        show = download.media.show
        session.commit()

        with pytest.raises(HTTPException) as exc_info:
            delete_episode(session, episode_slug)
        assert exc_info.value.status_code == 409
        assert session.get(MediaDownloadBase, download_id) is not None

        session.delete(show)
        session.commit()
        assert session.get(MediaDownloadBase, download_id) is None
    finally:
        session.close()
        engine.dispose()


def test_redownload_dependencies_freeze_weights_and_preserve_child_ownership(monkeypatch):
    from backend.types.download_profile_types import MediaDownloadArtifactStatus
    from task_manager.scheduler.operations import create_operation
    from task_manager.scheduler.types import OperationDependencyCancelPolicy
    from task_manager.tasks import media_download_operations

    session, engine = _session()
    try:
        first = _make_download(session, slug="dependency-existing")
        second = _make_download(session, slug="dependency-new-known")
        third = _make_download(session, slug="dependency-new-unknown")
        first.artifact_status = MediaDownloadArtifactStatus.AVAILABLE.value
        second.artifact_status = MediaDownloadArtifactStatus.AVAILABLE.value
        third.artifact_status = MediaDownloadArtifactStatus.AVAILABLE.value
        first.downloaded_bytes = 100
        second.downloaded_bytes = 300
        third.downloaded_bytes = None
        first.downloaded_at = datetime.now(timezone.utc)
        second.downloaded_at = datetime.now(timezone.utc)
        third.downloaded_at = datetime.now(timezone.utc)

        existing = media_download_operations.create_media_download_operation(
            session,
            first,
        )
        parent = create_operation(
            session,
            kind="media_download.bulk_retry",
            resource_type="media_download",
            resource_id=None,
            title="Downloads",
            targets=[],
            context={"downloads_requested": 3},
        )
        monkeypatch.setattr(
            media_download_operations,
            "dispatch_queued_media_download_operations",
            lambda _session: 0,
        )

        children = media_download_operations.attach_redownload_dependencies(
            session,
            parent,
            (first, second, third),
        )

        assert children[0].id == existing.id
        assert len(children) == 3
        dependencies = list(parent.dependencies)
        assert [dependency.weight for dependency in dependencies] == [100.0, 300.0, 200.0]
        assert dependencies[0].cancel_policy == OperationDependencyCancelPolicy.DETACH.value
        assert all(
            dependency.cancel_policy == OperationDependencyCancelPolicy.CANCEL_IF_EXCLUSIVE.value
            for dependency in dependencies[1:]
        )
        assert children[0].context["prepare_existing_artifact"] is False
        assert all(
            child.context["prepare_existing_artifact"] is True
            for child in children[1:]
        )
        assert third.downloaded_bytes is None
        assert third.artifact_status == MediaDownloadArtifactStatus.AVAILABLE.value
    finally:
        session.close()
        engine.dispose()


def test_delete_unavailable_media_download_removes_record():
    from backend.services.download_actions import delete_unavailable_media_download
    from backend.db.models.media_download import MediaDownloadBase
    from backend.types.download_profile_types import MediaDownloadArtifactStatus

    session, engine = _session()
    try:
        download = _make_download(session, slug="delete-missing")
        download.artifact_status = MediaDownloadArtifactStatus.MISSING.value
        download.file_path = "/definitely/not/present/delete-missing.m4a"
        download_id = download.id
        session.commit()

        delete_unavailable_media_download(session, download_id)
        session.commit()

        assert session.get(MediaDownloadBase, download_id) is None
    finally:
        session.close()
        engine.dispose()


def test_delete_unavailable_media_download_removes_not_downloaded_record():
    from backend.services.download_actions import delete_unavailable_media_download
    from backend.db.models.media_download import MediaDownloadBase

    session, engine = _session()
    try:
        download = _make_download(session, slug="delete-not-downloaded")
        download.file_path = "/definitely/not/present/delete-not-downloaded.m4a"
        download_id = download.id
        session.commit()

        delete_unavailable_media_download(session, download_id)
        session.commit()

        assert session.get(MediaDownloadBase, download_id) is None
    finally:
        session.close()
        engine.dispose()


def test_delete_unavailable_media_download_removes_cancelled_record():
    from backend.services.download_actions import delete_unavailable_media_download
    from backend.db.models.media_download import MediaDownloadBase

    session, engine = _session()
    try:
        download = _make_download(session, slug="delete-cancelled")
        download.file_path = "/definitely/not/present/delete-cancelled.m4a"
        download.automatic_retry_suppressed = True
        download_id = download.id
        session.commit()

        delete_unavailable_media_download(session, download_id)
        session.commit()

        assert session.get(MediaDownloadBase, download_id) is None
    finally:
        session.close()
        engine.dispose()


def test_delete_unavailable_media_download_rejects_not_downloaded_record_with_artifact(tmp_path):
    import pytest

    from backend.services.download_actions import DownloadActionError, delete_unavailable_media_download
    from backend.db.models.media_download import MediaDownloadBase

    session, engine = _session()
    try:
        artifact = tmp_path / "not-downloaded-but-present.m4a"
        artifact.write_bytes(b"media")

        download = _make_download(session, slug="delete-not-downloaded-present")
        download.file_path = str(artifact)
        download_id = download.id
        session.commit()

        with pytest.raises(DownloadActionError) as exc_info:
            delete_unavailable_media_download(session, download_id)

        assert exc_info.value.kind == "conflict"
        assert session.get(MediaDownloadBase, download_id) is not None
    finally:
        session.close()
        engine.dispose()


def test_delete_unavailable_media_download_rejects_available_record():
    import pytest

    from backend.services.download_actions import DownloadActionError, delete_unavailable_media_download
    from backend.db.models.media_download import MediaDownloadBase
    from backend.types.download_profile_types import MediaDownloadArtifactStatus

    session, engine = _session()
    try:
        download = _make_download(session, slug="delete-available")
        download.artifact_status = MediaDownloadArtifactStatus.AVAILABLE.value
        download_id = download.id
        session.commit()

        with pytest.raises(DownloadActionError) as exc_info:
            delete_unavailable_media_download(session, download_id)

        assert exc_info.value.kind == "conflict"
        assert session.get(MediaDownloadBase, download_id) is not None
    finally:
        session.close()
        engine.dispose()


def test_delete_unavailable_media_download_rejects_restored_file(tmp_path):
    import pytest

    from backend.services.download_actions import DownloadActionError, delete_unavailable_media_download
    from backend.db.models.media_download import MediaDownloadBase
    from backend.types.download_profile_types import MediaDownloadArtifactStatus

    session, engine = _session()
    try:
        restored = tmp_path / "restored.m4a"
        restored.write_bytes(b"restored media")

        download = _make_download(session, slug="delete-restored")
        download.artifact_status = MediaDownloadArtifactStatus.MISSING.value
        download.file_path = str(restored)
        download_id = download.id
        session.commit()

        with pytest.raises(DownloadActionError) as exc_info:
            delete_unavailable_media_download(session, download_id)

        assert exc_info.value.kind == "conflict"
        assert session.get(MediaDownloadBase, download_id) is not None
        assert download.artifact_status == MediaDownloadArtifactStatus.AVAILABLE.value
    finally:
        session.close()
        engine.dispose()
