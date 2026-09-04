# Task operations

`TaskRun` and `TaskOperation` deliberately represent different things:

- A **TaskRun** is one execution attempt of one registered worker.
- A **TaskOperation** is one durable high-level action a user asked WireLoft to perform.
- A **TaskOperationTarget** describes a logical worker result required to satisfy an operation.
- **TaskOperationRun** links a logical target to the concrete TaskRun(s) that can satisfy it.

Keeping those concepts separate is what allows one UI action to fan out over many workers, one already-running automatic worker to satisfy a UI action, and retries/recovery to remain implementation details rather than UI concerns.

## Adding a UI-triggered worker action

1. Create an operation in the API service with `create_operation()` and one or more `OperationTargetSpec` values.
2. For work owned directly by the operation, call `queue_operation_target_dispatch()` for each target. It schedules the target only after the API transaction commits and skips targets already satisfied by compatible work. A domain event can still be used when the action genuinely represents a domain event; use `operation_target_needs_dispatch()` to avoid duplicate work in that case.
3. Return an API response containing `operation_id`. Do not create a separate manual request/correlation ID.
4. Have the worker report ordinary progress through its `progress` object and return a `TaskResult` with structured facts when it completes.
5. In the frontend, start the request through the generic operation helper and let `OperationNotifier` own polling, final notifications and cache refreshes. Components that need live status can use `useActiveOperation()`.

Workers must not accept `operation_id`, `manual_request_id`, or similar UI-only parameters. Operation correlation belongs to the scheduler infrastructure.

For large fan-out actions, dispatch the durable targets directly instead of translating every target into an in-memory event. This keeps correlation explicit in scheduler infrastructure and avoids depending on a transient event queue for hundreds of sibling tasks.

## Worker results

A worker can return:

```python
return TaskResult(
    summary="Episode scan finished",
    data={
        "episodes_found": 3,
        "shows_scanned": 1,
    },
)
```

`summary` is a generic human-readable fallback. `data` contains facts, not UI prose. The frontend may present those facts differently depending on the operation kind.

For fan-out operations, numeric result fields from successful targets are aggregated automatically. Operation status becomes `PARTIAL` when only part of the target set succeeds.

## Progress

Workers and worker services continue to use the normal progress updater:

```python
progress.set(50, "Refreshing episode 10/20")
```

A progress update emitted anywhere inside the worker call stack is persisted on the `TaskRun`. Active TaskRuns start at zero and scheduler infrastructure does not increment their percentage, so a non-zero active percentage means the worker/service itself supplied granular progress. `TaskOperation` prefers that percentage. This preserves purpose-built progress trackers such as the granular `fetch_new_episodes` mapper/indexing progress instead of replacing them with a coarse operation-level estimate.

When none of an operation's active workers reports progress, `TaskOperation` falls back to logical target completion. For example, a 200-episode metadata refresh whose individual workers do not publish percentages advances as targets finish. Terminal targets count as complete and the operation reaches 100% when every target is terminal.

Operation targets and their run associations are loaded through SQLAlchemy relationships with eager loading when aggregate state is calculated. Aggregate progress must remain a bounded-query operation as target counts grow; do not reintroduce per-target TaskRun queries.

There must not be a worker-specific frontend polling loop for progress.

## Coalescing

When an operation is created, its targets are matched against compatible active TaskRuns by:

- task key;
- resource type and ID;
- the target's declared worker inputs.

A compatible automatic TaskRun can therefore satisfy a later UI operation without starting duplicate work. Conversely, when a TaskRun starts, it attaches itself to every compatible active operation.

A target can be associated with multiple equivalent runs. Once any linked run succeeds, that logical target is satisfied even if another duplicate run later fails.

Target inputs should contain every value that changes the semantics of the requested work. For example, an explicit metadata refresh includes `scheduled_offset_seconds=None`, so it cannot be confused with a timed post-publication check.

## Child work and events

Operation IDs are held in an internal execution `ContextVar`. `trigger_now()` inherits that context automatically. The domain-event executor also copies Python context variables into its worker thread, so a task started by an event emitted from another task retains the operation context without putting an ID in the event payload.

A child task only becomes part of completion accounting when the operation has a matching logical target. A master worker can alternatively aggregate its child work itself and expose one target, as the show re-download worker does.

## Retries, restarts and cancellation

Retries reuse the same TaskRun, so their target association survives automatically.

Logical targets are durable. On backend restart, in-process `RUNNING` and `RETRY_SCHEDULED` executions from the previous process are marked interrupted and detached from their operation targets. Recoverable incomplete targets are then requeued from their persisted task key, resource and worker inputs.

A user-requested operation restart uses the same durable targets. Targets already satisfied by a successful TaskRun remain satisfied; only unfinished targets are detached and requeued. This means restarting a large fan-out action does not repeat work that already completed.

Cancellation immediately marks the TaskOperation canceled and removes exclusively owned queued/retry jobs. APScheduler cannot safely terminate an arbitrary Python function that is already executing in a worker thread, so running work is canceled cooperatively: `ProgressUpdater.set()` is a cancellation checkpoint, and the executor checks again before accepting a worker result or scheduling a retry. A TaskRun that is still needed by another active TaskOperation is not canceled.

This is why recovery and control state must live in scheduler infrastructure rather than in React state or worker-specific request IDs.

## Frontend ownership

`OperationNotifier` is mounted once above the router. It is responsible for:

- discovering UI operations;
- polling more frequently while work is active;
- exposing active operation status/progress to the rest of the UI;
- showing exactly one final notification per acknowledged operation;
- refreshing relevant React Query data after completion;
- acknowledging the durable notification only after it has been presented.

A page may disappear, the route may change, or the browser may reload while the worker runs. None of those should affect operation tracking.
