from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def test_deleting_show_cascades_scheduler_work_and_exposes_relationships(tmp_path):
    import backend.db.models  # noqa: F401
    import task_manager.scheduler.db  # noqa: F401
    from backend.db import Base
    from backend.db.models import Show
    from task_manager.scheduler.db import (
        TaskDefinition,
        TaskOperation,
        TaskOperationTarget,
        TaskRun,
        TaskSchedule,
    )
    from task_manager.scheduler.types import OperationSource, OperationStatus, ResourceType, TaskStatus

    engine = create_engine(
        f"sqlite:///{(tmp_path / 'resource-task-relations.db').as_posix()}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)

    try:
        with Session(engine) as session:
            show = Show(
                uuid="show-uuid",
                slug="show-slug",
                title="Show title",
                description=None,
                sharing_url="https://example.test/show",
                membership_level="FREE",
                type="podcast",
                episode_identifier="numbered",
                author_name="Host",
                author_slug="host",
                author_headshot_path=None,
                background_image_path=None,
                logo_image_path=None,
                thumbnail_landscape_path=None,
                thumbnail_portrait_path=None,
                thumbnail_square_path=None,
            )
            session.add(show)
            session.flush()

            definition = TaskDefinition(
                key="resource_relationship_worker",
                title="Resource relationship worker",
                description=None,
                allowed_resource_types=["show"],
                default_max_retries=0,
            )
            session.add(definition)
            session.flush()

            schedule = TaskSchedule(
                definition_id=definition.id,
                resource_type=ResourceType.SHOW,
                resource_id=show.id,
                trigger="interval",
                trigger_args={"minutes": 5},
                active=True,
                max_retries=0,
            )
            run = TaskRun(
                schedule_id=None,
                definition_id=definition.id,
                resource_type=ResourceType.SHOW,
                resource_id=show.id,
                status=TaskStatus.RUNNING,
                progress=35,
                message="Working",
                meta=None,
                result=None,
                attempt_count=1,
                max_retries=0,
                last_error=None,
                next_retry_at=None,
                started_at=datetime.now(timezone.utc),
                finished_at=None,
                runtime_ms=None,
            )
            operation = TaskOperation(
                id="show-operation",
                kind="show.sync",
                source=OperationSource.UI.value,
                resource_type="show",
                resource_id=show.id,
                title=show.title,
                status=OperationStatus.RUNNING.value,
                progress=35,
                message="Working",
                result=None,
                context={},
                error=None,
                notification_seen_at=None,
                started_at=datetime.now(timezone.utc),
                finished_at=None,
            )
            target = TaskOperationTarget(
                operation=operation,
                task_key=definition.key,
                resource_type="show",
                resource_id=show.id,
                slot_key="show",
                task_kwargs={},
                recover_on_restart=True,
            )
            session.add_all([schedule, run, operation, target])
            session.commit()

            show_id = show.id
            schedule_id = schedule.id
            run_id = run.id
            operation_id = operation.id
            target_id = target.id

            assert [item.id for item in show.task_schedules] == [schedule_id]
            assert [item.id for item in show.task_runs] == [run_id]
            assert [item.id for item in show.task_operations] == [operation_id]
            assert [item.id for item in show.task_operation_targets] == [target_id]

            session.delete(show)
            session.commit()

            assert session.get(Show, show_id) is None
            assert session.get(TaskSchedule, schedule_id) is None
            assert session.get(TaskRun, run_id) is None
            assert session.get(TaskOperation, operation_id) is None
            assert session.get(TaskOperationTarget, target_id) is None
    finally:
        engine.dispose()
