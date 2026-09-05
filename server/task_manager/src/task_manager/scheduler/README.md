# WireLoft Scheduler

A lightweight, APScheduler-powered task scheduler integrated into the WireLoft backend. It lets you:
- Register internal tasks bound to a resource (show/season/episode/movie)
- Schedule tasks via cron/interval/date triggers
- Trigger ad-hoc runs immediately
- Track task runs, progress, status, retries, and errors via the API
    
This package is designed to feel native with the existing FastAPI + SQLAlchemy stack and is configured via wireloft_config.get_settings().


## Contents
- What’s included
- Configuration
- Database and initialization
- Defining a task (with retries and progress)
- Scheduling a task (via REST)
- Triggering a task immediately (via REST)
- Listing schedules and runs (via REST)
- Retry policy and backoff
- Status lifecycle and progress
- Tips and best practices
- Troubleshooting


## What’s included
- SQLAlchemy models to persist:
  - TaskDefinition: catalog of available tasks (key, title, description, allowed resource types, default max retries)
  - TaskSchedule: user-created schedules (cron/interval/date) bound to a resource
  - TaskRun: every execution attempt with progress, status, retries and timings
- Task registry decorator to register functions as schedulable tasks
- Executor that runs tasks, updates progress, and performs retries with exponential backoff
- APScheduler lifecycle and jobstore wiring (SQLite by default; can use your DB URL)
- Backend API endpoints under /api/tasks to manage definitions, schedules, and runs


## Configuration
All settings are centralized in wireloft_config. Relevant fields (wireloft_config.settings.submodels.SchedulerSettings):
- enabled: bool (default: True) — Turn the scheduler on/off
- timezone: str (default: "UTC") — Scheduler timezone
- jobstore_url: Optional[str] — SQLAlchemy URL used by APScheduler; defaults to the main app DB if None
- max_workers: int (default: 5) — Thread pool size used by APScheduler
- default_max_retries: int (default: 3) — Global default max retries if not set by task or schedule
- retry_backoff_seconds: float (default: 5.0) — Base delay for exponential backoff between retries

## How settings are loaded:
- The backend calls get_settings().scheduler to read these values.
- If jobstore_url is not set, the scheduler uses the main SQLite database path in WIRELOFT_DB_PATH, defaulting to data/wireloft.db when not set.

Example (Python):
from wireloft_config import get_settings
print(get_settings().scheduler.enabled)
print(get_settings().scheduler.default_max_retries)


## Database and initialization
- Scheduler tables that belong to WireLoft are part of the shared SQLAlchemy metadata and are created or upgraded by the backend's Alembic migrations. APScheduler alone owns its separate `apscheduler_jobs` table.
- During the FastAPI application lifespan, if the scheduler is enabled:
  1) `task_manager.scheduler.registry.sync_registry_to_db()` synchronizes registered tasks into `TaskDefinition`.
  2) `task_manager.scheduler.scheduler.start_scheduler()` starts APScheduler on the ASGI event loop.
  3) Application shutdown drains domain events, removes subscriptions, and shuts down APScheduler.

Constructing the FastAPI application does not start background work. This keeps
CLI inspection and tests free of scheduler side effects.

Important: Your task modules must be importable before sync_registry_to_db() runs so that the @task decorator has executed and definitions exist to be synced.


## Defining a task (with retries and progress)
Define your task in any importable module. The function can be async or sync and must accept resource_id and progress arguments.

Example:
from wireloft_scheduler.registry import task
from wireloft_scheduler.executor import ProgressUpdater

@task(
    key="refresh_episode_metadata",
    title="Refresh Episode Metadata",
    description="Fetches and updates metadata for an episode",
    allowed_resource_types=("episode",),
    default_max_retries=5,  # optional: per-task default override
)
async def refresh_episode_metadata(resource_id: int, progress: ProgressUpdater):
    progress.set(5, "Starting")
    # ... your logic here ...
    # periodically report progress and messages:
    progress.set(50, "Halfway there", meta={"step": "fetch"})
    # ... finish work ...
    progress.set(100, "Done")

Notes:
- allowed_resource_types controls what resource kinds can bind to this task ("show", "season", "episode", "movie").
- default_max_retries sets a task-level default retry limit. Precedence is covered in Retry policy.
- ProgressUpdater.set(percent, message=None, meta=None) clamps percent to [0..100] and persists message/meta for the UI.
- Ensure the module containing the task is imported during app startup (e.g., import it in your backend app module) so the decorator registers the definition.


## Scheduling a task (via REST)
Create a schedule bound to a specific resource with a cron, interval, or date trigger.
Endpoint: POST /api/tasks/schedules
Body (camelCase):
{
  "definitionKey": "refresh_episode_metadata",
  "resourceType": "episode",
  "resourceId": 123,
  "trigger": "cron",                 // or "interval" | "date"
  "triggerArgs": {"minute": "0", "hour": "3"},
  "maxRetries": 2                      // optional override used by runs from this schedule
}

Examples of triggerArgs:
- Cron: {"minute": "0", "hour": "3"}  // every day at 03:00
- Interval: {"minutes": 15}              // every 15 minutes
- Date: {"run_date": "2025-10-12T03:00:00+00:00"}  // one-off at exact time

Response includes the created schedule with nextRunTime and maxRetries.

List schedules:
GET /api/tasks/schedules
GET /api/tasks/schedules?resource_type=episode&resource_id=123

Delete a schedule:
DELETE /api/tasks/schedules/{schedule_id}


## Triggering a task immediately (via REST)
You can run a task on demand without creating a schedule.
Endpoint: POST /api/tasks/runs/trigger
Query params:
- definition_key: string
- resource_type: show|season|episode|movie
- resource_id: int
- max_retries: int (optional)

Example:
curl -X POST "http://localhost:8000/api/tasks/runs/trigger?definition_key=refresh_episode_metadata&resource_type=episode&resource_id=123&max_retries=4"
Response: { "jobId": "..." }


## Listing schedules and runs (via REST)
- List available task definitions:
  GET /api/tasks/definitions
  → [{ id, key, title, description, allowedResourceTypes, defaultMaxRetries }]

- List schedules (optionally filtered by resource):
  GET /api/tasks/schedules
  GET /api/tasks/schedules?resource_type=episode&resource_id=123
  → [{ id, definitionKey, resourceType, resourceId, trigger, triggerArgs, active, nextRunTime, maxRetries }]

- List runs (optionally filtered by resource and status):
  GET /api/tasks/runs
  GET /api/tasks/runs?resource_type=episode&resource_id=123
  GET /api/tasks/runs?status=RUNNING
  → [{ id, definitionKey, resourceType, resourceId, status, progress, message, attemptCount, maxRetries, lastError, startedAt, finishedAt, runtimeMs }]


## Retry policy and backoff
### Retry precedence for a run:
1) max_retries passed to trigger_now (API or internal) if provided
2) TaskSchedule.max_retries if the run came from a schedule
3) TaskDefinition.default_max_retries if set on the task registry entry
4) Global default: get_settings().scheduler.default_max_retries

### Backoff timing between attempts is exponential:
- delay_seconds = retry_backoff_seconds * (2 ** (attempt - 1))
- retry_backoff_seconds comes from get_settings().scheduler.retry_backoff_seconds (default 5.0)
- attempt starts at 1 for the first retry

### When a failure occurs and a retry remains:
- The TaskRun status becomes RETRY_SCHEDULED
- nextRetryAt is set, and APScheduler enqueues a new run for the same TaskRun id at that time
- If retries are exhausted, status becomes FAILED and lastError/message are set


## Status lifecycle and progress
### Possible TaskRun.status values:
- RUNNING: The task is executing
- SUCCEEDED: Task finished successfully (progress is set to 100)
- FAILED: Task failed and has no retries left
- RETRY_SCHEDULED: Failed but a retry has been scheduled

### Additional statuses that may appear in the system:
- SCHEDULED/QUEUED/CANCELED are defined for completeness but primarily used for higher-level representations

### Progress reporting:
- Within your task function, call progress.set(percent, message=None, meta=None)
- The latest values are visible via GET /api/tasks/runs
- For live UIs, poll runs for the resource (or later add WebSocket updates if needed)


## Tips and best practices
- Idempotency: Design tasks to be safe to retry. Prefer computing desired state and upserts over destructive operations.
- Concurrency: This package doesn’t impose per-resource locks. If your task must not overlap for the same resource, add your own guard (e.g., DB advisory lock or check existing RUNNING runs).
- Long-running tasks: Prefer incremental progress updates so the UI can reflect activity. Use message/meta for user-friendly context.
- Task discovery: Ensure your task modules are imported before registry sync. A common pattern is to import the module in backend startup code.
- Timezones: Cron triggers run in the scheduler’s timezone (get_settings().scheduler.timezone). Date triggers accept timezone-aware ISO strings (e.g., +00:00).


## Troubleshooting
- I don’t see my task in /api/tasks/definitions:
  - Make sure the module that defines @task is imported before app startup calls sync_registry_to_db().
- My /api/tasks/schedules shows nextRunTime as null:
  - APScheduler computes next run times after start; ensure the scheduler is enabled and started (get_settings().scheduler.enabled = true).
- Date trigger rejected:
  - Use an ISO8601 string with explicit timezone offset, e.g., 2025-10-12T03:00:00+00:00.
- Progress never changes:
  - Call progress.set periodically inside your task. Ensure exceptions are handled or allowed to bubble so retries can schedule.


## Appendix: Internal APIs (if you need them)
- Programmatic trigger (internal):
  from wireloft_scheduler.executor import trigger_now
  trigger_now(def_key="refresh_episode_metadata", resource_type="episode", resource_id=123, max_retries=4)

- Manual APScheduler schedule (rarely needed; prefer REST + DB):
  from wireloft_scheduler.scheduler import schedule_job
  schedule_job(schedule_id=1, def_key="refresh_episode_metadata", resource_type="episode", resource_id=123, trigger="interval", trigger_args={"minutes": 15})

That’s it! Define your task, sync the registry, and use the /api/tasks endpoints to manage schedules and observe runs.
