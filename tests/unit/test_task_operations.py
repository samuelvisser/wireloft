from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def _session() -> Session:
    # Import both model collections before create_all so every FK referenced by
    # the scheduler and operation tables is present in Base.metadata.
    import backend.db.models  # noqa: F401
    import task_manager.scheduler.db  # noqa: F401
    from backend.db import Base

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def _definition(session: Session, key: str = "test_worker"):
    from task_manager.scheduler.db import TaskDefinition

    definition = TaskDefinition(
        key=key,
        title="Test worker",
        description=None,
        allowed_resource_types=["show", "episode"],
        default_max_retries=0,
    )
    session.add(definition)
    session.flush()
    return definition


def _run(
        session: Session,
        definition,
        *,
        resource_type,
        resource_id: int,
        progress: int = 0,
        status=None,
        inputs: dict | None = None,
):
    from task_manager.scheduler.db import TaskRun
    from task_manager.scheduler.types import TaskStatus

    run = TaskRun(
        schedule_id=None,
        definition_id=definition.id,
        resource_type=resource_type,
        resource_id=resource_id,
        status=status or TaskStatus.RUNNING,
        progress=progress,
        message=None,
        meta={"inputs": inputs} if inputs else None,
        result=None,
        attempt_count=1,
        max_retries=0,
        last_error=None,
        next_retry_at=None,
        started_at=datetime.now(timezone.utc),
        finished_at=None,
        runtime_ms=None,
    )
    session.add(run)
    session.flush()
    return run


def test_operation_coalesces_onto_compatible_automatic_run():
    from task_manager.scheduler.operations import OperationTargetSpec, create_operation
    from task_manager.scheduler.types import OperationStatus, ResourceType

    session = _session()
    try:
        definition = _definition(session)
        run = _run(
            session,
            definition,
            resource_type=ResourceType.SHOW,
            resource_id=42,
            progress=41,
        )

        operation = create_operation(
            session,
            kind="show.sync",
            resource_type="show",
            resource_id=42,
            title="Test Show",
            targets=[
                OperationTargetSpec(
                    task_key=definition.key,
                    resource_type="show",
                    resource_id=42,
                )
            ],
        )
        session.flush()

        assert operation.status == OperationStatus.RUNNING.value
        assert operation.progress == 41

        from task_manager.scheduler.db import TaskOperationRun
        association = session.query(TaskOperationRun).one()
        assert association.operation_id == operation.id
        assert association.task_run_id == run.id
    finally:
        session.close()


def test_task_operation_models_expose_native_relationships():
    from task_manager.scheduler.operations import OperationTargetSpec, create_operation
    from task_manager.scheduler.types import ResourceType

    session = _session()
    try:
        definition = _definition(session)
        run = _run(
            session,
            definition,
            resource_type=ResourceType.SHOW,
            resource_id=42,
        )
        operation = create_operation(
            session,
            kind="show.sync",
            resource_type="show",
            resource_id=42,
            title="Test Show",
            targets=[
                OperationTargetSpec(
                    task_key=definition.key,
                    resource_type="show",
                    resource_id=42,
                )
            ],
        )
        session.flush()

        target = operation.targets[0]
        link = target.run_links[0]

        assert target.operation is operation
        assert link.target is target
        assert link.task_run is run
        assert link.operation is operation
        assert link in operation.run_links
        assert link in run.operation_links
    finally:
        session.close()


def test_one_task_run_can_satisfy_multiple_overlapping_operations():
    from task_manager.scheduler.operations import (
        OperationTargetSpec,
        create_operation,
        link_run_to_operations,
        refresh_operations_for_run,
    )
    from task_manager.scheduler.results import TaskResult
    from task_manager.scheduler.types import OperationStatus, ResourceType, TaskStatus

    session = _session()
    try:
        definition = _definition(session)
        target = OperationTargetSpec(
            task_key=definition.key,
            resource_type="show",
            resource_id=7,
        )
        first = create_operation(
            session,
            kind="show.index",
            resource_type="show",
            resource_id=7,
            title="Test Show",
            targets=[target],
        )
        second = create_operation(
            session,
            kind="show.sync",
            resource_type="show",
            resource_id=7,
            title="Test Show",
            targets=[target],
        )

        run = _run(
            session,
            definition,
            resource_type=ResourceType.SHOW,
            resource_id=7,
            progress=20,
        )
        linked = link_run_to_operations(
            session,
            run=run,
            task_key=definition.key,
        )

        assert set(linked) == {first.id, second.id}

        run.status = TaskStatus.SUCCEEDED
        run.progress = 100
        run.result = TaskResult(
            summary="Episode scan finished",
            data={"episodes_found": 3},
        ).as_dict()
        run.finished_at = datetime.now(timezone.utc)
        session.flush()
        refresh_operations_for_run(session, run.id)

        assert first.status == OperationStatus.SUCCEEDED.value
        assert second.status == OperationStatus.SUCCEEDED.value
        assert first.result == run.result
        assert second.result == run.result
    finally:
        session.close()


def test_multi_target_operation_aggregates_progress_and_structured_results():
    from task_manager.scheduler.operations import (
        OperationTargetSpec,
        create_operation,
        link_run_to_operations,
        refresh_operation,
    )
    from task_manager.scheduler.results import TaskResult
    from task_manager.scheduler.types import OperationStatus, ResourceType, TaskStatus

    session = _session()
    try:
        definition = _definition(session, "refresh_episode_metadata_worker")
        operation = create_operation(
            session,
            kind="show.refresh_metadata",
            resource_type="show",
            resource_id=5,
            title="Test Show",
            targets=[
                OperationTargetSpec(
                    task_key=definition.key,
                    resource_type="episode",
                    resource_id=101,
                    task_kwargs={"refresh": True},
                    slot_key="episode:101",
                ),
                OperationTargetSpec(
                    task_key=definition.key,
                    resource_type="episode",
                    resource_id=102,
                    task_kwargs={"refresh": True},
                    slot_key="episode:102",
                ),
            ],
        )

        first_run = _run(
            session,
            definition,
            resource_type=ResourceType.EPISODE,
            resource_id=101,
            progress=100,
            status=TaskStatus.SUCCEEDED,
            inputs={"refresh": True},
        )
        first_run.result = TaskResult(
            summary="Metadata refresh completed",
            data={"episodes_refreshed": 1},
        ).as_dict()
        first_run.finished_at = datetime.now(timezone.utc)
        link_run_to_operations(
            session,
            run=first_run,
            task_key=definition.key,
            operation_ids=(operation.id,),
            operation_slot="episode:101",
        )

        second_run = _run(
            session,
            definition,
            resource_type=ResourceType.EPISODE,
            resource_id=102,
            progress=50,
            inputs={"refresh": True},
        )
        link_run_to_operations(
            session,
            run=second_run,
            task_key=definition.key,
            operation_ids=(operation.id,),
            operation_slot="episode:102",
        )

        refresh_operation(session, operation.id)
        assert operation.status == OperationStatus.RUNNING.value
        assert operation.progress == 75

        second_run.status = TaskStatus.SUCCEEDED
        second_run.progress = 100
        second_run.result = TaskResult(
            summary="Metadata refresh completed",
            data={"episodes_refreshed": 1},
        ).as_dict()
        second_run.finished_at = datetime.now(timezone.utc)
        session.flush()
        refresh_operation(session, operation.id)

        assert operation.status == OperationStatus.SUCCEEDED.value
        assert operation.progress == 100
        assert operation.result is not None
        assert operation.result["data"]["episodes_refreshed"] == 2
        assert operation.result["data"]["completed"] == 2
        assert operation.result["data"]["total"] == 2
    finally:
        session.close()


def test_multi_target_operation_falls_back_to_completed_targets_without_worker_progress():
    from task_manager.scheduler.operations import (
        OperationTargetSpec,
        create_operation,
        link_run_to_operations,
        refresh_operation,
    )
    from task_manager.scheduler.types import OperationStatus, ResourceType, TaskStatus

    session = _session()
    try:
        definition = _definition(session, "refresh_episode_metadata_worker")
        operation = create_operation(
            session,
            kind="show.refresh_metadata",
            resource_type="show",
            resource_id=5,
            title="Test Show",
            targets=[
                OperationTargetSpec(
                    task_key=definition.key,
                    resource_type="episode",
                    resource_id=101,
                    task_kwargs={"refresh": True},
                    slot_key="episode:101",
                ),
                OperationTargetSpec(
                    task_key=definition.key,
                    resource_type="episode",
                    resource_id=102,
                    task_kwargs={"refresh": True},
                    slot_key="episode:102",
                ),
            ],
        )

        finished = _run(
            session,
            definition,
            resource_type=ResourceType.EPISODE,
            resource_id=101,
            progress=100,
            status=TaskStatus.SUCCEEDED,
            inputs={"refresh": True},
        )
        finished.finished_at = datetime.now(timezone.utc)
        link_run_to_operations(
            session,
            run=finished,
            task_key=definition.key,
            operation_ids=(operation.id,),
            operation_slot="episode:101",
        )

        active = _run(
            session,
            definition,
            resource_type=ResourceType.EPISODE,
            resource_id=102,
            progress=0,
            inputs={"refresh": True},
        )
        link_run_to_operations(
            session,
            run=active,
            task_key=definition.key,
            operation_ids=(operation.id,),
            operation_slot="episode:102",
        )

        refresh_operation(session, operation.id)

        assert operation.status == OperationStatus.RUNNING.value
        assert operation.progress == 50
    finally:
        session.close()


def test_operation_target_input_mismatch_does_not_coalesce():
    from task_manager.scheduler.operations import OperationTargetSpec, create_operation
    from task_manager.scheduler.types import OperationStatus, ResourceType

    session = _session()
    try:
        definition = _definition(session, "redownload_show_episodes_worker")
        _run(
            session,
            definition,
            resource_type=ResourceType.SHOW,
            resource_id=88,
            progress=33,
            inputs={"download_profile_id": 1},
        )

        operation = create_operation(
            session,
            kind="show.redownload_episodes",
            resource_type="show",
            resource_id=88,
            title="Test Show",
            targets=[
                OperationTargetSpec(
                    task_key=definition.key,
                    resource_type="show",
                    resource_id=88,
                    task_kwargs={"download_profile_id": 2},
                )
            ],
        )

        assert operation.status == OperationStatus.QUEUED.value
        assert operation.progress == 0
    finally:
        session.close()


def test_operation_target_dispatch_fans_out_after_commit(monkeypatch):
    import task_manager.scheduler.scheduler as scheduler_module
    from task_manager.scheduler.operations import (
        OperationTargetSpec,
        create_operation,
        queue_operation_target_dispatch,
    )

    session = _session()
    try:
        definition = _definition(session, "refresh_episode_metadata_worker")
        operation = create_operation(
            session,
            kind="show.refresh_metadata",
            resource_type="show",
            resource_id=5,
            title="Test Show",
            targets=[
                OperationTargetSpec(
                    task_key=definition.key,
                    resource_type="episode",
                    resource_id=episode_id,
                    task_kwargs={"refresh": True},
                    slot_key=f"episode:{episode_id}",
                )
                for episode_id in (101, 102, 103)
            ],
        )

        dispatched: list[dict] = []
        monkeypatch.setattr(
            scheduler_module,
            "trigger_now",
            lambda **kwargs: dispatched.append(kwargs) or "job-id",
        )

        for episode_id in (101, 102, 103):
            assert queue_operation_target_dispatch(
                session,
                operation.id,
                f"episode:{episode_id}",
            ) is True

        assert dispatched == []
        session.commit()

        assert [item["resource_id"] for item in dispatched] == [101, 102, 103]
        assert [item["operation_slot"] for item in dispatched] == [
            "episode:101",
            "episode:102",
            "episode:103",
        ]
        assert all(item["operation_ids"] == (operation.id,) for item in dispatched)
        assert all(item["refresh"] is True for item in dispatched)
    finally:
        session.close()


def test_refresh_operation_eager_loads_target_run_graph_without_n_plus_one_queries():
    from sqlalchemy import event
    from task_manager.scheduler.operations import OperationTargetSpec, create_operation, refresh_operation

    session = _session()
    try:
        definition = _definition(session, "refresh_episode_metadata_worker")
        operation = create_operation(
            session,
            kind="show.refresh_metadata",
            resource_type="show",
            resource_id=5,
            title="Test Show",
            targets=[
                OperationTargetSpec(
                    task_key=definition.key,
                    resource_type="episode",
                    resource_id=episode_id,
                    task_kwargs={"refresh": True},
                    slot_key=f"episode:{episode_id}",
                )
                for episode_id in range(1, 51)
            ],
        )
        operation_id = operation.id
        session.expire_all()

        statements: list[str] = []

        def count_statement(*args):
            statements.append(args[2])

        engine = session.get_bind()
        event.listen(engine, "before_cursor_execute", count_statement)
        try:
            refresh_operation(session, operation_id)
        finally:
            event.remove(engine, "before_cursor_execute", count_statement)

        # Operation + targets + association rows are loaded in a bounded number
        # of SELECTs regardless of the number of logical targets.
        assert len(statements) <= 4
    finally:
        session.close()
