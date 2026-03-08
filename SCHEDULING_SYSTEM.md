# WireLoft Flexible Scheduling System

## Overview

The WireLoft scheduling system has been redesigned to support flexible, declarative task scheduling using decorators. Tasks can now be triggered by:

1. **Cron schedules** - Recurring tasks based on cron expressions
2. **Events** - Tasks triggered by application events (e.g., show.added, episode.published)
3. **Manual triggers** - Tasks triggered via API or CLI

## Architecture

### Packages

- **wireloft_task_manager**: Central scheduling and event management
  - `scheduler.registry`: Task registration and trigger decorators
  - `scheduler.scheduler`: APScheduler integration
  - `scheduler.executor`: Task execution with retry logic
  - `events.registry`: Event emitter (pyventus)

- **wireloft_controller**: Task workers and business logic
  - `tasks.workers.*`: Individual worker implementations

### Key Components

1. **Task Registry** (`wireloft_task_manager.scheduler.registry`)
   - Stores all task definitions and their triggers
   - Provides decorators: `@task`, `@on_cron`, `@on_event`

2. **Trigger Setup** (`wireloft_controller.app.setup_triggers_from_registry()`)
   - Reads all triggers from registry on startup
   - Creates APScheduler jobs for cron triggers
   - Registers event handlers for event triggers

3. **Event System** (`wireloft_task_manager.events`)
   - Pyventus-based event emitter
   - Allows async event-driven task triggering

## Usage

### Defining a Task

```python
from wireloft_task_manager.scheduler.registry import task, on_cron, on_event

@task(
    key="my_task",
    title="My Task",
    description="Does something useful",
    allowed_resource_types=("show", "episode"),
    default_max_retries=5,
    tracks_progress=True,
)
@on_cron(
    cron="*/30 * * * *",  # Every 30 minutes
    resource_type="show",
    resource_id=0,  # 0 = all shows
    coalesce=True,  # Don't queue multiple if delayed
    run_on_startup=True,  # Also run immediately on startup
)
@on_event(
    event_name="show.added",
    resource_type="show",
)
async def my_task(*, resource_id=None, slug=None, progress=None):
    # Task implementation
    with db_session() as s:
        await do_work(s, resource_id=resource_id, progress=progress)
```

### Settings Integration

Cron expressions can reference settings using a special `settings:` prefix:

```python
@on_cron(
    cron="settings:new_episode_schedule.find_episodes_cron",
    # ...
)
```

For interval-based settings (minutes), the system automatically converts them to cron format:

```python
@on_cron(
    cron="settings:download_settings.verify_downloads_interval_min",
    # If verify_downloads_interval_min=120, becomes: */120 * * * *
)
```

### Multiple Triggers

Tasks can have multiple triggers of different types:

```python
@task(...)
@on_cron(cron="0 2 * * *")  # Daily at 2am
@on_cron(cron="*/15 * * * *")  # Also every 15 minutes
@on_event(event_name="show.added")
@on_event(event_name="episode.published")
async def multi_trigger_task(...):
    pass
```

## Implemented Workers

### 1. fetch_new_episodes

**Purpose**: Finds new episodes for shows

**Triggers**:
- Cron: Based on `settings.new_episode_schedule.find_episodes_cron`
- Event: `show.added` (when a new show is added)
- Startup: Runs immediately on application startup

**Resource**: `show` (resource_id=0 for all shows, or specific show ID)

### 2. download_profile_worker

**Purpose**: Implements download profiles by downloading requested episodes

**Triggers**:
- Cron: Based on `settings.download_settings.verify_downloads_interval_min`
- Event: `episode.published_countdown` (episode approaching publication)
- Event: `episode.published` (episode fully published)
- Event: `show.added` (download all episodes for new show)
- Startup: Runs immediately on application startup

**Resource**: `download_profile` or `episode` or `show` depending on trigger

### 3. file_watcher

**Purpose**: Watches local files and syncs with database

**Triggers**:
- Cron: `*/10 * * * *` (every 10 minutes)
- Event: `file.changed`

**Resource**: `show`

## Event System

### Emitting Events

To trigger tasks via events:

```python
from wireloft_task_manager.events.registry import get_wireloft_event_emitter

event_emitter = get_wireloft_event_emitter()

# Emit an event
await event_emitter.emit(
    "show.added",
    {"id": show_id, "slug": show_slug}
)
```

### Event Naming Convention

- Use dot notation: `resource.action`
- Examples: `show.added`, `episode.published`, `file.changed`

### Event Data

Event data should include:
- `id` or `resource_id`: The ID of the resource
- Other relevant metadata

## Configuration

### Settings Structure

```python
# In wireloft_config/settings/settings.py

class AppSettings(SettingsBase):
    scheduler: SchedulerSettings = Field(...)
    new_episode_schedule: TrackNewEpisodeSchedule = Field(...)
    download_settings: DownloadSettings = Field(...)
```

### Scheduler Settings

```python
scheduler:
  enabled: true
  max_workers: 5
  default_max_retries: 3
  retry_backoff_seconds: 5.0
```

### Episode Schedule Settings

```python
new_episode_schedule:
  find_episodes_cron: "*/30 * * * *"  # Every 30 minutes
  monitor_episode_cron: "*/1 * * * *"  # Every minute
```

### Download Settings

```python
download_settings:
  verify_downloads_interval_min: 120  # Every 2 hours
  max_concurrent_downloads: 5
```

## Preventing Concurrent Runs

The system handles concurrency in several ways:

1. **Coalescing**: Set `coalesce=True` on cron triggers to prevent queueing multiple runs
2. **APScheduler Job IDs**: Each cron trigger gets a unique job ID, preventing duplicates
3. **Task Status**: The executor tracks task status (RUNNING, SUCCEEDED, FAILED) in the database

### Example: fetch_new_episodes

When `fetch_new_episodes` is triggered:
- Via cron (every 30min) with `coalesce=True`
- Via event (`show.added`) for a specific show

The coalesce setting ensures that if the cron trigger fires while a previous run is still executing, it won't queue another global run. However, event-triggered runs for specific shows will still execute since they have different parameters.

## Manual Triggering

### Via API

```python
from wireloft_task_manager.scheduler.executor import trigger_now

# Trigger a task
job_id = trigger_now(
    def_key="fetch_new_episodes",
    resource_type="show",
    resource_id=123,  # Or None for all
    max_retries=3,
)
```

### Via CLI

```bash
python -m wireloft_controller.cli run fetch_new_episodes --resource-id=123
```

## Database Schema

### task_definitions
- Registered task metadata
- Created automatically from `@task` decorators

### task_schedules
- User-created or API-created schedules
- Not used by decorator-based triggers

### task_runs
- Execution history
- Status, progress, retry information

## Migration from Old System

### Before (Old System)

```python
# Hardcoded in controller/app.py
def _planned_startup_schedules():
    yield {
        "job_id": "auto-new-episode-finder",
        "task_key": "new_episode_finder",
        "cron": settings.new_episode_schedule.find_episodes_cron,
    }
```

### After (New System)

```python
# Declarative in worker entrypoint
@task(key="fetch_new_episodes", ...)
@on_cron(cron="settings:new_episode_schedule.find_episodes_cron", ...)
async def fetch_new_episodes(...):
    pass
```

## Benefits

1. **Declarative**: Triggers are defined next to the task code
2. **Flexible**: Multiple triggers per task, mix of cron and events
3. **Settings Integration**: Cron expressions can reference settings
4. **No Hardcoding**: No need to update app.py for new tasks
5. **Event-Driven**: React to application events in real-time
6. **Coalescing**: Built-in protection against concurrent runs

## Troubleshooting

### Tasks Not Running

1. Check scheduler is enabled: `settings.scheduler.enabled = true`
2. Check task is imported: All worker modules must be imported at startup
3. Check logs for trigger setup errors
4. Verify cron expression is valid

### Events Not Triggering Tasks

1. Verify event name matches exactly
2. Check event emitter is used: `get_wireloft_event_emitter()`
3. Ensure event data includes resource ID

### Settings Not Resolving

1. Verify settings path is correct: `settings:package.setting_name`
2. Check setting exists in `wireloft_config.settings.settings.AppSettings`
3. For intervals, ensure value is an integer (minutes)

## Future Enhancements

- [ ] Task dependencies (run task B after task A completes)
- [ ] Conditional triggers (only run if condition met)
- [ ] Task priority/queueing
- [ ] Better concurrency control (locks, semaphores)
- [ ] Task monitoring dashboard
