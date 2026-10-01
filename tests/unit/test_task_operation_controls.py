from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace


def _definition(session, key: str):
    from task_manager.scheduler.db import TaskDefinition

    definition = TaskDefinition(
        key=key,
        title="Operation control test worker",
        description=None,
        allowed_resource_types=["episode"],
        default_max_retries=0,
    )
    session.add(definition)
    session.flush()
    return definition


def _run(session, definition, *, resource_id: int, status, progress: int | None, inputs: dict | None = None):
    from task_manager.scheduler.db import TaskRun
    from task_manager.scheduler.types import ResourceType

    run = TaskRun(
        schedule_id=None,
        definition_id=definition.id,
        resource_type=ResourceType.EPISODE,
        resource_id=resource_id,
        status=status,
        progress=progress,
        message="Running",
        meta={"inputs": inputs} if inputs else None,
        result=None,
        attempt_count=1,
        max_retries=0,
        last_error=None,
        next_retry_at=None,
        started_at=datetime.now(timezone.utc),
        finished_at=datetime.now(timezone.utc) if str(status).endswith("SUCCEEDED") else None,
        runtime_ms=None,
    )
    session.add(run)
    session.flush()
    return run


def _restart_scenario(task_database, monkeypatch):
    from task_manager.scheduler.operation_control import restart_operation
    from task_manager.scheduler.operations import (
        OperationTargetSpec,
        create_operation,
        link_run_to_operations,
        refresh_operations_for_run,
    )
    from task_manager.scheduler.types import TaskStatus
    import task_manager.scheduler.scheduler as scheduler_module

    session = task_database()
    definition = _definition(session, "test_restart_operation_worker")
    operation = create_operation(
        session,
        kind="show.test_restart",
        resource_type="show",
        resource_id=5,
        title="Test Show",
        targets=[
            OperationTargetSpec(
                task_key=definition.key,
                resource_type="episode",
                resource_id=101,
                slot_key="episode:101",
            ),
            OperationTargetSpec(
                task_key=definition.key,
                resource_type="episode",
                resource_id=102,
                slot_key="episode:102",
            ),
        ],
    )
    operation_id = operation.id
    definition_key = definition.key

    completed_run = _run(
        session,
        definition,
        resource_id=101,
        status=TaskStatus.SUCCEEDED,
        progress=100,
    )
    completed_run_id = completed_run.id
    running_run = _run(
        session,
        definition,
        resource_id=102,
        status=TaskStatus.RUNNING,
        progress=37,
    )
    running_run_id = running_run.id

    link_run_to_operations(
        session,
        run=completed_run,
        task_key=definition.key,
        operation_ids=(operation_id,),
        operation_slot="episode:101",
    )
    link_run_to_operations(
        session,
        run=running_run,
        task_key=definition.key,
        operation_ids=(operation_id,),
        operation_slot="episode:102",
    )
    refresh_operations_for_run(session, completed_run_id)
    refresh_operations_for_run(session, running_run_id)
    session.commit()
    session.close()

    canceled_jobs: list[tuple[str, set[int]]] = []
    dispatched: list[dict] = []
    monkeypatch.setattr(
        scheduler_module,
        "cancel_pending_operation_jobs",
        lambda *, operation_id, run_ids=(): canceled_jobs.append((operation_id, set(run_ids))) or 0,
    )
    monkeypatch.setattr(
        scheduler_module,
        "trigger_now",
        lambda **kwargs: dispatched.append(kwargs) or "job-id",
    )
    monkeypatch.setattr(
        "task_manager.scheduler.registry.get_task",
        lambda key: (
            SimpleNamespace(recovery_dispatcher=None),
            None,
        ) if key == definition_key else (_ for _ in ()).throw(KeyError(key)),
    )

    payload = restart_operation(operation_id)
    return {
        "payload": payload,
        "operation_id": operation_id,
        "definition_key": definition_key,
        "completed_run_id": completed_run_id,
        "running_run_id": running_run_id,
        "canceled_jobs": canceled_jobs,
        "dispatched": dispatched,
    }


def test_cancel_operation_is_durable_and_requests_running_worker_stop(task_database, monkeypatch):
    from task_manager.scheduler.db import TaskOperation, TaskRun
    from task_manager.scheduler.operation_control import (
        RUN_CANCEL_REQUESTED_META_KEY,
        cancel_operation,
    )
    from task_manager.scheduler.operations import (
        OperationTargetSpec,
        create_operation,
        get_operation,
        link_run_to_operations,
        refresh_operations_for_run,
    )
    from task_manager.scheduler.types import OperationStatus, TaskStatus
    import task_manager.scheduler.scheduler as scheduler_module

    session = task_database()
    definition = _definition(session, "test_cancel_operation_worker")
    operation = create_operation(
        session,
        kind="episode.test_cancel",
        resource_type="episode",
        resource_id=17,
        title="Episode 17",
        targets=[
            OperationTargetSpec(
                task_key=definition.key,
                resource_type="episode",
                resource_id=17,
            )
        ],
    )
    operation_id = operation.id
    run = _run(
        session,
        definition,
        resource_id=17,
        status=TaskStatus.RUNNING,
        progress=42,
    )
    run_id = run.id
    link_run_to_operations(
        session,
        run=run,
        task_key=definition.key,
        operation_ids=(operation_id,),
    )
    refresh_operations_for_run(session, run_id)
    session.commit()
    session.close()

    canceled_jobs: list[tuple[str, set[int]]] = []
    monkeypatch.setattr(
        scheduler_module,
        "cancel_pending_operation_jobs",
        lambda *, operation_id, run_ids=(): canceled_jobs.append((operation_id, set(run_ids))) or 0,
    )

    payload = cancel_operation(operation_id)
    assert payload is not None
    assert payload.status == OperationStatus.CANCELED.value
    assert payload.progress == 42
    assert canceled_jobs == [(operation_id, {run_id})]

    # Refreshing the operation must not resurrect it from linked RUNNING state.
    refreshed = get_operation(operation_id)
    assert refreshed is not None
    assert refreshed.status == OperationStatus.CANCELED.value

    session = task_database()
    try:
        stored_operation = session.get(TaskOperation, operation_id)
        stored_run = session.get(TaskRun, run_id)
        assert stored_operation is not None
        assert stored_operation.finished_at is not None
        assert stored_operation.context is not None
        assert stored_operation.context["cancel_requested"] is True
        assert stored_run is not None
        assert stored_run.meta is not None
        assert stored_run.meta[RUN_CANCEL_REQUESTED_META_KEY] is True
    finally:
        session.close()


def test_cancel_operation_does_not_stop_run_shared_with_another_active_operation(task_database, monkeypatch):
    from task_manager.scheduler.db import TaskOperation, TaskRun
    from task_manager.scheduler.operation_control import (
        RUN_CANCEL_REQUESTED_META_KEY,
        cancel_operation,
    )
    from task_manager.scheduler.operations import (
        OperationTargetSpec,
        create_operation,
        link_run_to_operations,
        refresh_operations_for_run,
    )
    from task_manager.scheduler.types import OperationStatus, TaskStatus
    import task_manager.scheduler.scheduler as scheduler_module

    session = task_database()
    definition = _definition(session, "test_shared_cancel_worker")
    target = OperationTargetSpec(
        task_key=definition.key,
        resource_type="episode",
        resource_id=23,
    )
    first = create_operation(
        session,
        kind="episode.test_cancel.first",
        resource_type="episode",
        resource_id=23,
        title="First request",
        targets=[target],
    )
    second = create_operation(
        session,
        kind="episode.test_cancel.second",
        resource_type="episode",
        resource_id=23,
        title="Second request",
        targets=[target],
    )
    first_id = first.id
    second_id = second.id
    run = _run(
        session,
        definition,
        resource_id=23,
        status=TaskStatus.RUNNING,
        progress=31,
    )
    run_id = run.id
    link_run_to_operations(
        session,
        run=run,
        task_key=definition.key,
        operation_ids=(first_id, second_id),
    )
    refresh_operations_for_run(session, run_id)
    session.commit()
    session.close()

    canceled_jobs: list[tuple[str, set[int]]] = []
    monkeypatch.setattr(
        scheduler_module,
        "cancel_pending_operation_jobs",
        lambda *, operation_id, run_ids=(): canceled_jobs.append((operation_id, set(run_ids))) or 0,
    )

    payload = cancel_operation(first_id)
    assert payload is not None
    assert payload.status == OperationStatus.CANCELED.value
    assert canceled_jobs == [(first_id, set())]

    session = task_database()
    try:
        shared_run = session.get(TaskRun, run_id)
        assert shared_run is not None
        assert shared_run.status == TaskStatus.RUNNING
        assert not isinstance(shared_run.meta, dict) or RUN_CANCEL_REQUESTED_META_KEY not in shared_run.meta
        still_active = session.get(TaskOperation, second_id)
        assert still_active is not None
        assert still_active.status == OperationStatus.RUNNING.value
    finally:
        session.close()


def test_restart_operation_reports_restarted_progress(task_database, monkeypatch):
    from task_manager.scheduler.types import OperationStatus

    scenario = _restart_scenario(task_database, monkeypatch)
    payload = scenario["payload"]
    assert payload is not None
    assert payload.status in {OperationStatus.QUEUED.value, OperationStatus.RUNNING.value}
    assert payload.progress == 50


def test_restart_single_non_progress_operation_stays_indeterminate(task_database, monkeypatch):
    import task_manager.scheduler.registry as registry_module
    import task_manager.scheduler.scheduler as scheduler_module
    from task_manager.scheduler.operation_control import restart_operation
    from task_manager.scheduler.operations import (
        OperationTargetSpec,
        create_operation,
        link_run_to_operations,
        refresh_operations_for_run,
    )
    from task_manager.scheduler.types import OperationStatus, TaskStatus

    monkeypatch.setattr(registry_module, "_REGISTRY", {})

    async def worker(*, resource_id=None, progress=None):
        return None

    registry_module.task(
        key="opaque_restart_worker",
        title="Opaque restart worker",
        allowed_resource_types=("episode",),
        tracks_progress=False,
    )(worker)

    session = task_database()
    definition = _definition(session, "opaque_restart_worker")
    operation = create_operation(
        session,
        kind="episode.opaque_restart",
        resource_type="episode",
        resource_id=17,
        title="Opaque restart",
        targets=[
            OperationTargetSpec(
                task_key=definition.key,
                resource_type="episode",
                resource_id=17,
            )
        ],
    )
    operation_id = operation.id
    run = _run(
        session,
        definition,
        resource_id=17,
        status=TaskStatus.RUNNING,
        progress=None,
    )
    link_run_to_operations(
        session,
        run=run,
        task_key=definition.key,
        operation_ids=(operation_id,),
    )
    refresh_operations_for_run(session, run.id)
    assert operation.progress is None
    session.commit()
    session.close()

    monkeypatch.setattr(
        scheduler_module,
        "cancel_pending_operation_jobs",
        lambda **_kwargs: 0,
    )
    monkeypatch.setattr(
        scheduler_module,
        "trigger_now",
        lambda **_kwargs: "job-id",
    )

    payload = restart_operation(operation_id)
    assert payload is not None
    assert payload.status == OperationStatus.QUEUED.value
    assert payload.progress is None
    assert payload.completion_progress == 0


def test_restart_operation_cancels_old_and_dispatches_unfinished(task_database, monkeypatch):
    scenario = _restart_scenario(task_database, monkeypatch)
    assert scenario["canceled_jobs"] == [
        (scenario["operation_id"], {scenario["running_run_id"]})
    ]
    assert scenario["dispatched"] == [
        {
            "def_key": scenario["definition_key"],
            "resource_type": "episode",
            "resource_id": 102,
            "operation_ids": (scenario["operation_id"],),
            "operation_slot": "episode:102",
        }
    ]


def test_restart_operation_replaces_unfinished_link(task_database, monkeypatch):
    from task_manager.scheduler.db import TaskOperationRun, TaskRun
    from task_manager.scheduler.operation_control import RUN_CANCEL_REQUESTED_META_KEY

    scenario = _restart_scenario(task_database, monkeypatch)
    session = task_database()
    try:
        running = session.get(TaskRun, scenario["running_run_id"])
        assert running is not None
        assert running.meta is not None
        assert running.meta[RUN_CANCEL_REQUESTED_META_KEY] is True

        links = session.query(TaskOperationRun).filter_by(
            operation_id=scenario["operation_id"]
        ).all()
        assert len(links) == 1
        assert links[0].task_run_id == scenario["completed_run_id"]
    finally:
        session.close()


def test_executor_skips_retry_run_after_cancellation_request(task_database):
    from task_manager.scheduler.db import TaskDefinition, TaskRun
    from task_manager.scheduler.executor import execute_task
    from task_manager.scheduler.operation_control import RUN_CANCEL_REQUESTED_META_KEY
    from task_manager.scheduler.registry import sync_registry_to_db, task
    from task_manager.scheduler.types import ResourceType, TaskStatus

    calls: list[int | None] = []
    task_key = "test_canceled_retry_worker"

    @task(
        key=task_key,
        title="Canceled retry worker",
        allowed_resource_types=("episode",),
        default_max_retries=0,
    )
    async def canceled_retry_worker(*, resource_id=None, progress=None):
        calls.append(resource_id)

    sync_registry_to_db()

    session = task_database()
    definition = session.query(TaskDefinition).filter_by(key=task_key).one()
    run = TaskRun(
        schedule_id=None,
        definition_id=definition.id,
        resource_type=ResourceType.EPISODE,
        resource_id=55,
        status=TaskStatus.RETRY_SCHEDULED,
        progress=20,
        message="Retry scheduled",
        meta={RUN_CANCEL_REQUESTED_META_KEY: True},
        result=None,
        attempt_count=1,
        max_retries=1,
        last_error="temporary failure",
        next_retry_at=datetime.now(timezone.utc),
        started_at=datetime.now(timezone.utc),
        finished_at=None,
        runtime_ms=None,
    )
    session.add(run)
    session.commit()
    run_id = run.id
    session.close()

    execute_task(
        def_key=task_key,
        resource_type="episode",
        resource_id=55,
        run_id=run_id,
    )

    assert calls == []
    session = task_database()
    try:
        canceled = session.get(TaskRun, run_id)
        assert canceled is not None
        assert canceled.status == TaskStatus.CANCELED
        assert canceled.finished_at is not None
    finally:
        session.close()



def _dependency_cancel_scenario(task_database, monkeypatch, *, shared_parent: bool):
    from task_manager.scheduler.operation_control import cancel_operation
    from task_manager.scheduler.operations import (
        OperationDependencySpec,
        OperationTargetSpec,
        add_operation_dependencies,
        create_operation,
        link_run_to_operations,
        refresh_operations_for_run,
    )
    from task_manager.scheduler.types import (
        OperationDependencyCancelPolicy,
        TaskStatus,
    )
    import task_manager.scheduler.scheduler as scheduler_module

    session = task_database()
    definition = _definition(session, "test_dependency_cancel_worker")
    child = create_operation(
        session,
        kind="media.download",
        resource_type="media_download",
        resource_id=77,
        title="Child download",
        targets=[
            OperationTargetSpec(
                task_key=definition.key,
                resource_type="episode",
                resource_id=77,
            )
        ],
    )
    run = _run(
        session,
        definition,
        resource_id=77,
        status=TaskStatus.RUNNING,
        progress=31,
    )
    link_run_to_operations(
        session,
        run=run,
        task_key=definition.key,
        operation_ids=(child.id,),
    )
    refresh_operations_for_run(session, run.id)

    parent = create_operation(
        session,
        kind="media_download.bulk_retry",
        resource_type="media_download",
        resource_id=None,
        title="Parent batch",
        targets=[],
    )
    add_operation_dependencies(
        session,
        parent.id,
        [OperationDependencySpec(
            child.id,
            cancel_policy=OperationDependencyCancelPolicy.CANCEL_IF_EXCLUSIVE.value,
        )],
    )

    other = None
    if shared_parent:
        other = create_operation(
            session,
            kind="movie.redownload_media",
            resource_type="movie",
            resource_id=5,
            title="Other parent",
            targets=[],
        )
        add_operation_dependencies(
            session,
            other.id,
            [OperationDependencySpec(
                child.id,
                cancel_policy=OperationDependencyCancelPolicy.DETACH.value,
            )],
        )

    parent_id, child_id, run_id = parent.id, child.id, run.id
    other_id = other.id if other is not None else None
    session.commit()
    session.close()

    canceled_jobs = []
    monkeypatch.setattr(
        scheduler_module,
        "cancel_pending_operation_jobs",
        lambda *, operation_id, run_ids=(): canceled_jobs.append(
            (operation_id, set(run_ids))
        ) or 0,
    )
    cancel_operation(parent_id)
    return parent_id, child_id, run_id, canceled_jobs, other_id


def test_canceling_parent_cancels_exclusive_owned_child_dependency(task_database, monkeypatch):
    from task_manager.scheduler.db import TaskOperation, TaskRun
    from task_manager.scheduler.operation_control import RUN_CANCEL_REQUESTED_META_KEY
    from task_manager.scheduler.types import OperationStatus

    parent_id, child_id, run_id, canceled_jobs, _ = _dependency_cancel_scenario(
        task_database,
        monkeypatch,
        shared_parent=False,
    )

    session = task_database()
    try:
        parent = session.get(TaskOperation, parent_id)
        child = session.get(TaskOperation, child_id)
        run = session.get(TaskRun, run_id)
        assert parent.status == OperationStatus.CANCELED.value
        # A running media.download remains active while its worker cooperatively
        # cleans up. The durable cancellation request prevents further work and
        # the child becomes CANCELED when that worker exits.
        assert child.status == OperationStatus.RUNNING.value
        assert child.context["cancel_requested"] is True
        assert run.meta[RUN_CANCEL_REQUESTED_META_KEY] is True
        assert (parent_id, set()) in canceled_jobs
        assert (child_id, {run_id}) in canceled_jobs
    finally:
        session.close()


def test_canceling_parent_does_not_cancel_child_shared_with_another_active_parent(task_database, monkeypatch):
    from task_manager.scheduler.db import TaskOperation, TaskRun
    from task_manager.scheduler.operation_control import RUN_CANCEL_REQUESTED_META_KEY
    from task_manager.scheduler.types import OperationStatus

    parent_id, child_id, run_id, canceled_jobs, other_id = _dependency_cancel_scenario(
        task_database,
        monkeypatch,
        shared_parent=True,
    )

    session = task_database()
    try:
        parent = session.get(TaskOperation, parent_id)
        child = session.get(TaskOperation, child_id)
        other = session.get(TaskOperation, other_id)
        run = session.get(TaskRun, run_id)
        assert parent.status == OperationStatus.CANCELED.value
        assert child.status == OperationStatus.RUNNING.value
        assert other.status == OperationStatus.RUNNING.value
        assert not (run.meta or {}).get(RUN_CANCEL_REQUESTED_META_KEY, False)
        assert (parent_id, set()) in canceled_jobs
        assert all(operation_id != child_id for operation_id, _ in canceled_jobs)
    finally:
        session.close()


def test_composite_operation_restart_requires_a_new_parent(task_database):
    import pytest

    from task_manager.scheduler.operation_control import restart_operation
    from task_manager.scheduler.operations import (
        OperationDependencySpec,
        add_operation_dependencies,
        create_operation,
    )

    session = task_database()
    child = create_operation(
        session,
        kind="child",
        resource_type="episode",
        resource_id=1,
        title="Child",
        targets=[],
    )
    parent = create_operation(
        session,
        kind="parent",
        resource_type="show",
        resource_id=1,
        title="Parent",
        targets=[],
    )
    add_operation_dependencies(
        session,
        parent.id,
        [OperationDependencySpec(child.id)],
    )
    parent_id = parent.id
    session.commit()
    session.close()

    with pytest.raises(ValueError, match="new operation"):
        restart_operation(parent_id)


def test_cancel_intent_survives_stale_active_status(task_database, monkeypatch):
    from sqlalchemy import update

    from task_manager.scheduler.db import TaskOperation
    from task_manager.scheduler.operation_control import (
        cancel_operation,
        operation_ids_allow_execution,
    )
    from task_manager.scheduler.operations import (
        OperationTargetSpec,
        create_operation,
        get_operation,
    )
    from task_manager.scheduler.types import OperationStatus
    import task_manager.scheduler.scheduler as scheduler_module

    session = task_database()
    definition = _definition(session, "test_cancel_intent_worker")
    operation = create_operation(
        session,
        kind="show.test_cancel_intent",
        resource_type="show",
        resource_id=91,
        title="Show 91",
        targets=[
            OperationTargetSpec(
                task_key=definition.key,
                resource_type="episode",
                resource_id=901,
            )
        ],
    )
    operation_id = operation.id
    session.commit()
    session.close()

    monkeypatch.setattr(
        scheduler_module,
        "cancel_pending_operation_jobs",
        lambda **_kwargs: 0,
    )

    payload = cancel_operation(operation_id)
    assert payload is not None
    assert payload.status == OperationStatus.CANCELED.value

    # Simulate an aggregate refresh that loaded RUNNING before cancellation and
    # committed that stale state after the cancel transaction.
    session = task_database()
    session.execute(
        update(TaskOperation)
        .where(TaskOperation.id == operation_id)
        .values(
            status=OperationStatus.RUNNING.value,
            completion_progress=0,
            message="Stale running state",
            finished_at=None,
        )
    )
    session.commit()
    assert operation_ids_allow_execution(session, (operation_id,)) is False
    session.close()

    refreshed = get_operation(operation_id)
    assert refreshed is not None
    assert refreshed.status == OperationStatus.CANCELED.value
    assert refreshed.completion_progress == 100
    assert refreshed.finished_at is not None


def test_progress_updater_honors_late_operation_cancellation(task_database):
    from task_manager.scheduler.executor import ProgressUpdater
    from task_manager.scheduler.operation_control import (
        OPERATION_CANCEL_REQUESTED_CONTEXT_KEY,
    )
    from task_manager.scheduler.operations import (
        OperationTargetSpec,
        create_operation,
        link_run_to_operations,
    )
    from task_manager.scheduler.types import TaskStatus

    session = task_database()
    definition = _definition(session, "test_late_cancel_owner_worker")
    operation = create_operation(
        session,
        kind="show.test_late_cancel_owner",
        resource_type="show",
        resource_id=92,
        title="Show 92",
        targets=[
            OperationTargetSpec(
                task_key=definition.key,
                resource_type="episode",
                resource_id=902,
            )
        ],
    )
    run = _run(
        session,
        definition,
        resource_id=902,
        status=TaskStatus.RUNNING,
        progress=0,
    )
    link_run_to_operations(
        session,
        run=run,
        task_key=definition.key,
        operation_ids=(operation.id,),
    )
    operation.context = {
        **(operation.context or {}),
        OPERATION_CANCEL_REQUESTED_CONTEXT_KEY: True,
    }
    # Leave both rows RUNNING to reproduce a worker that linked after the
    # cancellation traversal and therefore missed its TaskRun-level marker.
    session.commit()
    run_id = run.id
    session.close()

    updater = ProgressUpdater(run_id)
    assert updater() is True


def test_executor_rechecks_operation_ownership_after_link(task_database, monkeypatch):
    import task_manager.scheduler.executor as executor_module
    from task_manager.scheduler.db import TaskOperation, TaskRun
    from task_manager.scheduler.operation_control import OPERATION_CANCEL_REQUESTED_CONTEXT_KEY
    from task_manager.scheduler.operations import OperationTargetSpec, create_operation
    from task_manager.scheduler.registry import sync_registry_to_db, task
    from task_manager.scheduler.types import TaskStatus

    calls: list[int | None] = []
    task_key = "test_operation_handoff_cancel_worker"

    @task(
        key=task_key,
        title="Operation handoff cancellation worker",
        allowed_resource_types=("episode",),
        default_max_retries=0,
    )
    async def handoff_worker(*, resource_id=None, progress=None):
        calls.append(resource_id)

    sync_registry_to_db()

    session = task_database()
    operation = create_operation(
        session,
        kind="show.test_handoff_cancel",
        resource_type="show",
        resource_id=93,
        title="Show 93",
        targets=[
            OperationTargetSpec(
                task_key=task_key,
                resource_type="episode",
                resource_id=903,
            )
        ],
    )
    operation_id = operation.id
    session.commit()
    session.close()

    # The initial executor preflight happens before this hook. Persist the
    # cancellation only after the TaskRun has been linked, reproducing the
    # preflight -> durable-link race without thread timing.
    original_owner_check = executor_module._run_has_active_operation_owner

    def cancel_before_owner_check(session, run_id):
        operation = session.get(TaskOperation, operation_id)
        assert operation is not None
        operation.context = {
            **(operation.context or {}),
            OPERATION_CANCEL_REQUESTED_CONTEXT_KEY: True,
        }
        session.commit()
        return original_owner_check(session, run_id)

    monkeypatch.setattr(
        executor_module,
        "_run_has_active_operation_owner",
        cancel_before_owner_check,
    )

    executor_module.execute_task(
        def_key=task_key,
        resource_type="episode",
        resource_id=903,
        operation_ids=(operation_id,),
    )

    assert calls == []

    session = task_database()
    try:
        run = session.query(TaskRun).filter_by(resource_id=903).one()
        assert run.status == TaskStatus.CANCELED
        assert run.finished_at is not None
    finally:
        session.close()


def test_stale_canceled_parent_does_not_keep_exclusive_dependency_alive(task_database, monkeypatch):
    from sqlalchemy import update

    from task_manager.scheduler.db import TaskOperation, TaskRun
    from task_manager.scheduler.operation_control import (
        RUN_CANCEL_REQUESTED_META_KEY,
        cancel_operation,
    )
    from task_manager.scheduler.operations import (
        OperationDependencySpec,
        OperationTargetSpec,
        add_operation_dependencies,
        create_operation,
        link_run_to_operations,
        refresh_operations_for_run,
    )
    from task_manager.scheduler.types import (
        OperationDependencyCancelPolicy,
        OperationStatus,
        TaskStatus,
    )
    import task_manager.scheduler.scheduler as scheduler_module

    session = task_database()
    definition = _definition(session, "test_dependency_stale_parent_worker")
    child = create_operation(
        session,
        kind="media.download",
        resource_type="media_download",
        resource_id=94,
        title="Shared child",
        targets=[
            OperationTargetSpec(
                task_key=definition.key,
                resource_type="episode",
                resource_id=904,
            )
        ],
    )
    run = _run(
        session,
        definition,
        resource_id=904,
        status=TaskStatus.RUNNING,
        progress=10,
    )
    link_run_to_operations(
        session,
        run=run,
        task_key=definition.key,
        operation_ids=(child.id,),
    )
    refresh_operations_for_run(session, run.id)

    parents = []
    for kind in ("parent.first", "parent.second"):
        parent = create_operation(
            session,
            kind=kind,
            resource_type="show",
            resource_id=94,
            title=kind,
            targets=[],
        )
        add_operation_dependencies(
            session,
            parent.id,
            [OperationDependencySpec(
                child.id,
                cancel_policy=OperationDependencyCancelPolicy.CANCEL_IF_EXCLUSIVE.value,
            )],
        )
        parents.append(parent)

    first_id, second_id, child_id, run_id = (
        parents[0].id,
        parents[1].id,
        child.id,
        run.id,
    )
    session.commit()
    session.close()

    monkeypatch.setattr(
        scheduler_module,
        "cancel_pending_operation_jobs",
        lambda **_kwargs: 0,
    )

    # The first parent keeps the child shared while the second is canceled.
    second = cancel_operation(second_id)
    assert second is not None
    assert second.status == OperationStatus.CANCELED.value

    # Reproduce the stale-active write. Its durable marker must still make this
    # parent irrelevant to dependency exclusivity.
    session = task_database()
    session.execute(
        update(TaskOperation)
        .where(TaskOperation.id == second_id)
        .values(status=OperationStatus.RUNNING.value, finished_at=None)
    )
    session.commit()
    session.close()

    cancel_operation(first_id)

    session = task_database()
    try:
        child = session.get(TaskOperation, child_id)
        run = session.get(TaskRun, run_id)
        assert child is not None
        assert child.context is not None
        assert child.context["cancel_requested"] is True
        assert run is not None
        assert run.meta is not None
        assert run.meta[RUN_CANCEL_REQUESTED_META_KEY] is True
    finally:
        session.close()


def test_canceled_queued_media_download_does_not_resurrect(task_database, monkeypatch):
    from sqlalchemy import update

    from task_manager.scheduler.db import TaskOperation
    from task_manager.scheduler.operation_control import cancel_operation
    from task_manager.scheduler.operations import (
        OperationTargetSpec,
        create_operation,
        get_operation,
    )
    from task_manager.scheduler.types import OperationStatus
    import task_manager.scheduler.scheduler as scheduler_module

    session = task_database()
    definition = _definition(session, "test_queued_download_cancel_worker")
    operation = create_operation(
        session,
        kind="media.download",
        resource_type="media_download",
        resource_id=95,
        title="Queued download",
        targets=[
            OperationTargetSpec(
                task_key=definition.key,
                resource_type="episode",
                resource_id=905,
            )
        ],
    )
    operation_id = operation.id
    session.commit()
    session.close()

    monkeypatch.setattr(
        scheduler_module,
        "cancel_pending_operation_jobs",
        lambda **_kwargs: 0,
    )

    canceled = cancel_operation(operation_id)
    assert canceled is not None
    assert canceled.status == OperationStatus.CANCELED.value

    # A stale aggregate write can clear the terminal timestamp even though no
    # download worker ever started. The cancellation marker must still win.
    session = task_database()
    session.execute(
        update(TaskOperation)
        .where(TaskOperation.id == operation_id)
        .values(status=OperationStatus.QUEUED.value, finished_at=None)
    )
    session.commit()
    session.close()

    refreshed = get_operation(operation_id)
    assert refreshed is not None
    assert refreshed.status == OperationStatus.CANCELED.value
    assert refreshed.finished_at is not None
