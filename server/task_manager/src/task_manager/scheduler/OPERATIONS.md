# Task operations

`TaskRun` and `TaskOperation` deliberately represent different things:

- A **TaskRun** is one execution attempt of one registered worker.
- A **TaskOperation** is one durable high-level unit of work, such as a user action or a system-created download.
- A **TaskOperationTarget** describes a logical worker result required to satisfy an operation.
- **TaskOperationRun** links a logical target to the concrete TaskRun(s) that can satisfy it.

Keeping those concepts separate is what allows one UI action to fan out over many workers, one already-running automatic worker to satisfy a UI action, and retries/recovery to remain implementation details rather than UI concerns.

## Execution state versus library state

Anything that is still happening belongs to `TaskRun`/`TaskOperation`: queued/running state, progress, retry state, cancellation, execution errors and timing. Domain models must not duplicate that lifecycle state.

Anything that has happened and is now part of WireLoft's library belongs to ordinary domain data. `MediaDownload` is the canonical example: it stores the desired/current artifact path, whether the artifact is available/missing/corrupt, downloaded size/format/time and immutable attempt history. It does not store a live download status or live progress percentage. The UI combines the persistent artifact with an active `media.download` TaskOperation when it needs a presentation such as "Queued" or "Downloading 63%".

This boundary is intentional. A backend restart can reconstruct unfinished execution entirely from scheduler state without guessing from domain rows, while completed library facts remain useful even after the operation that produced them is no longer active.

## Adding a UI-triggered worker action

1. Create an operation in the API service with `create_operation()` and one or more `OperationTargetSpec` values.
2. For work owned directly by the operation, call `queue_operation_target_dispatch()` for each target. It schedules the target only after the API transaction commits and skips targets already satisfied by compatible work. A domain event can still be used when the action genuinely represents a domain event; use `operation_target_needs_dispatch()` to avoid duplicate work in that case.
3. Return an API response containing `operation_id`. Do not create a separate manual request/correlation ID.
4. Have the worker report ordinary progress through its `progress` object and return a `TaskResult` with structured facts when it completes.
5. In the frontend, start the request through the generic operation helper. `FrontendPuller` owns discovery/progress polling, while `OperationNotifier` owns final notifications and operation-driven cache refreshes. Components that need live status can use `useActiveOperation()`.

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

A progress update emitted anywhere inside the worker call stack is persisted on the `TaskRun`. `TaskOperation` prefers a non-zero worker percentage while the worker is active. This preserves purpose-built progress trackers such as the granular `fetch_new_episodes` mapper/indexing progress instead of replacing them with a coarse operation-level estimate.

When none of an operation's active workers reports granular progress, `TaskOperation` falls back to logical target completion. For example, a 200-episode metadata refresh whose individual workers do not publish percentages advances as targets finish. Terminal targets count as complete and the operation reaches 100% when every target is terminal.

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

## Resource ownership and deletion

Domain resources that can own scheduler work use `HasTaskResourcesMixin`. It exposes generic `task_schedules`, `task_runs`, `task_operations`, and `task_operation_targets` relationships over the scheduler's `resource_type` + `resource_id` key.

Deleting a resource through SQLAlchemy therefore deletes the scheduler rows owned by that resource through normal ORM cascade semantics. Once the transaction commits, matching in-memory APScheduler jobs are removed as well. A retry whose TaskRun has already been deleted is ignored rather than recreating an orphaned run. If deletion removes a pending reservation from a constrained task lane, the task definition's generic terminal callback may refill the released slot; a still-running worker waits until its cooperative cancellation actually exits before releasing its slot.

This is intentionally generic. Show, season, episode, movie, movie-extra, download-profile and media-download deletion should not need action-specific scheduler cleanup code.

## Retries, restarts and cancellation

Retries reuse the same TaskRun, so their target association survives automatically.

Logical targets are durable. APScheduler's jobs are process-local, so on backend restart every non-terminal TaskRun from the previous process (`SCHEDULED`, `QUEUED`, `RUNNING`, or `RETRY_SCHEDULED`) is marked interrupted and detached from its operation targets. Recoverable incomplete targets are then requeued from their persisted task key, resource and worker inputs.

Some task types use a constrained operation queue. Media downloads, for example, reserve a `SCHEDULED` TaskRun before dispatch so the configured download concurrency limit cannot be exceeded merely because APScheduler has not started the job yet. Such targets register a recovery dispatcher: generic recovery restores the operation to `QUEUED`, then the dispatcher refills only the available slots instead of bypassing the queue policy.

A user-requested operation restart uses the same durable targets. Targets already satisfied by a successful TaskRun remain satisfied; only unfinished targets are detached and requeued. Queue-managed tasks are returned through their registered dispatcher rather than being triggered directly. This means restarting a large fan-out action does not repeat completed work or bypass a task-specific concurrency lane.

Cancellation immediately marks the TaskOperation canceled and removes exclusively owned queued/retry jobs. APScheduler cannot safely terminate an arbitrary Python function that is already executing in a worker thread, so running work is canceled cooperatively: `ProgressUpdater.set()` is a cancellation checkpoint, long-running download helpers use the same updater as a cancellation callback, and the executor checks again before accepting a worker result or scheduling a retry. A TaskRun that is still needed by another active TaskOperation is not canceled.

This is why recovery and control state must live in scheduler infrastructure rather than in React state or worker-specific request IDs.

## Stalled-work watchdog

APScheduler can limit concurrent jobs and decide how to handle late/misfired jobs, but it cannot decide whether WireLoft's application-level progress percentage has stopped changing. WireLoft installs a lightweight watchdog job for that purpose.

Once per minute, the watchdog samples `RUNNING` TaskOperation percentages and standalone `RUNNING` TaskRun percentages. If a percentage remains unchanged for `scheduler.stalledTaskTimeoutMinutes` (20 minutes by default), the work is canceled with a durable reason. A progress change resets the timer. Work that is merely queued/scheduled or waiting for retry backoff is not treated as stalled execution.

TaskRuns attached to active operations are watched through the operation rather than independently. This preserves shared/coalesced-run behavior: an old stalled request cannot kill work that a newer active operation still needs.

Watchdog observations are process-local and reset on backend restart. The durable operation-recovery mechanism handles interrupted work first, then recovered work receives a fresh watchdog window.

## Frontend ownership

`FrontendPuller` is mounted once above the router and is the single recurring polling transport for changing execution state. Its `/api/pull` response contains active TaskOperations from every source plus terminal UI operations that still need a durable completion notification. The backend selects `fast` cadence whenever any operation is active and `slow` cadence otherwise.

Persistent library data does not ride the background-state poll. Downloads, episodes, movies and other domain resources remain ordinary React Query/REST data. When a non-UI operation disappears from the active pull, or when a UI operation finishes, `OperationNotifier` invalidates the affected domain queries so they refresh the facts produced by that work.

`OperationNotifier` is responsible for:

- exposing active operation status/progress to the rest of the UI;
- showing exactly one final notification for UI operations that require one;
- refreshing relevant non-polling React Query data after completion;
- acknowledging the durable notification only after it has been presented.

A page may disappear, the route may change, or the browser may reload while the worker runs. None of those should affect operation tracking. New background-state polling features should join `FrontendPuller` instead of adding their own interval.
