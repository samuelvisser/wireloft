from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session


def test_deleting_show_removes_metadata_operation_with_episode_targets(tmp_path):
    import backend.db.models  # noqa: F401
    import task_manager.scheduler.db  # noqa: F401
    from backend.db import Base
    from backend.db.models import Show
    from task_manager.scheduler.db import TaskOperation, TaskOperationTarget
    from task_manager.scheduler.types import OperationSource, OperationStatus

    engine = create_engine(
        f"sqlite:///{(tmp_path / 'show-operation-cleanup.db').as_posix()}",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)

    try:
        with Session(engine) as session:
            show = Show(
                uuid="metadata-show-uuid",
                slug="metadata-show",
                title="Metadata Show",
                description=None,
                sharing_url="https://example.test/metadata-show",
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

            operation = TaskOperation(
                id="metadata-operation",
                kind="show.refresh_metadata",
                source=OperationSource.UI.value,
                resource_type="show",
                resource_id=show.id,
                title=show.title,
                status=OperationStatus.RUNNING.value,
                progress=42,
                message="86/207 tasks finished",
                result=None,
                context={},
                error=None,
                notification_seen_at=None,
                started_at=datetime.now(timezone.utc),
                finished_at=None,
            )
            target = TaskOperationTarget(
                operation=operation,
                task_key="refresh_episode_metadata_worker",
                resource_type="episode",
                resource_id=999,
                slot_key="episode:999",
                task_kwargs={"refresh": True},
                recover_on_restart=True,
            )
            session.add_all([operation, target])
            session.commit()

            operation_id = operation.id
            target_id = target.id
            assert operation in show.task_operations

            session.delete(show)
            session.commit()

            assert session.get(TaskOperation, operation_id) is None
            assert session.get(TaskOperationTarget, target_id) is None
    finally:
        engine.dispose()
