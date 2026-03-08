# WireLoft Scheduling System - Quick Start

## What Changed

All your requested changes have been implemented:

1. ✅ **Removed `on_startup` decorator** - Replaced with `app.startup` event
2. ✅ **Events use pyventus** - All event handling through motherboard's pyventus integration
3. ✅ **Event emission for data changes** - Comprehensive event system for add/delete operations
4. ✅ **Workers moved to motherboard** - All tasks now in `wireloft_task_manager.tasks.workers`
5. ✅ **Direct cron values** - `on_cron` requires actual cron string, not settings reference

## Quick Reference

### Creating a Worker

```python
# In server/motherboard/src/wireloft_task_manager/tasks/workers/my_worker/entrypoint.py

from wireloft_config import get_settings
from wireloft_task_manager.db_utils import db_session
from wireloft_task_manager.scheduler.registry import task, on_cron, on_event
from .service import run_my_worker

@task(
    key="my_worker",
    title="My Worker",
    description="What this worker does",
)
@on_cron(
    cron=get_settings().my_setting.cron_expression,  # Actual value, not string!
    resource_type="show",
    resource_id=0,
)
@on_event(event_name="app.startup")  # Runs on startup
@on_event(event_name="my.custom.event")
async def my_worker(*, resource_id=None, progress=None):
    with db_session() as s:
        await run_my_worker(s, resource_id=resource_id, progress=progress)
```

### Emitting Events

```python
# In backend API endpoints
from wireloft_task_manager.events import emitters

# Show events
await emitters.emit_show_added(show_id, slug=show.slug)
await emitters.emit_show_deleted(show_id)

# Episode events
await emitters.emit_episode_added(episode_id, show_id=show_id)
await emitters.emit_episode_published(episode_id, show_id=show_id)
await emitters.emit_episode_published_countdown(episode_id, show_id=show_id)
await emitters.emit_episode_deleted(episode_id)

# Download profile events
await emitters.emit_download_profile_added(profile_id)
await emitters.emit_download_profile_deleted(profile_id)

# Custom event
await emitters.emit_event("custom.event", {"resource_id": 123})
```

### Available Events

**System:**
- `app.startup` - Application startup

**Shows:**
- `show.added` - Show created
- `show.deleted` - Show deleted

**Episodes:**
- `episode.added` - Episode created
- `episode.deleted` - Episode deleted
- `episode.published` - Episode fully published
- `episode.published_countdown` - Episode countdown started

**Download Profiles:**
- `download_profile.added` - Profile created
- `download_profile.deleted` - Profile deleted

**Seasons:**
- `season.added` - Season created
- `season.deleted` - Season deleted

**Files:**
- `file.changed` - Local file changed

## Current Workers

### fetch_new_episodes
**Location**: `server/motherboard/src/wireloft_task_manager/tasks/workers/fetch_new_episodes/`

**Triggers**:
- Cron: `get_settings().new_episode_schedule.find_episodes_cron`
- Event: `app.startup`
- Event: `show.added`

**Purpose**: Finds new episodes for all shows or a specific show

### download_profile_worker
**Location**: `server/motherboard/src/wireloft_task_manager/tasks/workers/download_profile_worker/`

**Triggers**:
- Cron: Every N minutes (`verify_downloads_interval_min` from settings)
- Event: `app.startup`
- Event: `episode.published_countdown`
- Event: `episode.published`
- Event: `show.added`

**Purpose**: Downloads episodes based on download profiles

### file_watcher
**Location**: `server/motherboard/src/wireloft_task_manager/tasks/workers/file_watcher/`

**Triggers**:
- Cron: `*/10 * * * *` (every 10 minutes)
- Event: `file.changed`

**Purpose**: Watches local files and syncs with database

## Testing

### 1. Syntax Test
```bash
python3 test_scheduling_system.py
```

### 2. Run Application
```bash
uv sync
uv run python -m backend.main
```

**What to expect:**
1. All tasks register successfully
2. Cron jobs created for scheduled tasks
3. Event listeners registered
4. `app.startup` event fires
5. Startup tasks execute

### 3. Manual Event Test
```python
import asyncio
from wireloft_task_manager.events import emitters

async def test():
    await emitters.emit_show_added(123, slug="test")

asyncio.run(test())
```

Check `task_runs` table for new entries.

## Integration Checklist

Backend API integration (emit events when data changes):

- [ ] Shows:
  - [ ] Emit `show.added` in create endpoint
  - [ ] Emit `show.deleted` in delete endpoint

- [ ] Episodes:
  - [ ] Emit `episode.added` in create endpoint
  - [ ] Emit `episode.deleted` in delete endpoint
  - [ ] Emit `episode.published` when status changes to PUBLISHED
  - [ ] Emit `episode.published_countdown` when status changes to PUBLISHED_WITH_COUNTDOWN

- [ ] Download Profiles:
  - [ ] Emit `download_profile.added` in create endpoint
  - [ ] Emit `download_profile.deleted` in delete endpoint

- [ ] Seasons:
  - [ ] Emit `season.added` in create endpoint
  - [ ] Emit `season.deleted` in delete endpoint

See `server/backend/EVENTS_INTEGRATION.md` for detailed integration guide.

## Documentation

- **README_SCHEDULING.md** (this file): Quick reference
- **FINAL_CHANGES.md**: Complete list of changes
- **server/backend/EVENTS_INTEGRATION.md**: Backend integration guide
- **test_scheduling_system.py**: Test script

## File Structure

```
server/motherboard/
├── src/wireloft_task_manager/
│   ├── __init__.py                    # Imports tasks to register them
│   ├── db_utils.py                    # Database session utility
│   ├── scheduler/
│   │   ├── registry.py                # @task, @on_cron, @on_event
│   │   ├── scheduler.py               # APScheduler integration
│   │   ├── executor.py                # Task execution engine
│   │   ├── types.py                   # TaskStatus, ResourceType
│   │   └── db/                        # Database models
│   ├── events/
│   │   ├── WireloftEventEmitter.py    # Pyventus emitter
│   │   ├── registry.py                # Event emitter singleton
│   │   └── emitters.py                # Convenience functions
│   └── tasks/
│       ├── __init__.py                # Imports all workers
│       └── workers/
│           ├── fetch_new_episodes/
│           ├── download_profile_worker/
│           ├── file_watcher/
│           └── ...

server/controller/
├── src/wireloft_controller/
│   └── app.py                         # Initializes scheduler, emits app.startup
```

## Common Patterns

### Worker with Cron Schedule from Settings

```python
from wireloft_config import get_settings

@task(key="my_worker", title="My Worker")
@on_cron(
    cron=get_settings().my_section.my_cron_field,  # Direct value!
    resource_type="show",
    resource_id=0,
)
async def my_worker(...):
    pass
```

### Worker with Interval from Settings (Minutes)

```python
@task(key="my_worker", title="My Worker")
@on_cron(
    cron=f"*/{get_settings().my_section.interval_minutes} * * * *",
    resource_type="show",
    resource_id=0,
)
async def my_worker(...):
    pass
```

### Worker Triggered by Multiple Events

```python
@task(key="my_worker", title="My Worker")
@on_event(event_name="show.added")
@on_event(event_name="episode.published")
@on_event(event_name="app.startup")
async def my_worker(...):
    pass
```

### Worker with Both Cron and Events

```python
@task(key="my_worker", title="My Worker")
@on_cron(cron="0 3 * * *")  # Daily at 3am
@on_event(event_name="app.startup")  # Also on startup
@on_event(event_name="custom.trigger")  # And on custom event
async def my_worker(...):
    pass
```

## Troubleshooting

### Workers Not Registered
- Check `wireloft_task_manager.tasks.__init__.py` imports the worker
- Verify worker file has no syntax errors
- Check logs for import errors

### Cron Jobs Not Running
- Verify cron expression is valid
- Check `get_settings().scheduler.enabled = true`
- Look in APScheduler logs

### Events Not Triggering Tasks
- Verify event name matches exactly (case-sensitive)
- Check event emitter is used (`from wireloft_task_manager.events import emitters`)
- Ensure event includes `resource_id` in data

### Startup Event Not Firing
- Check controller app initialization logs
- Verify no exceptions during startup
- Look for "Warning: Failed to emit startup event" in logs

## Tips

1. **Event naming**: Use format `{resource}.{action}` (e.g., `show.added`)
2. **Resource IDs**: Always include in event data for proper task targeting
3. **Error handling**: Event emission should not break main operations (use try/except)
4. **Testing**: Use the test script to verify setup before deployment
5. **Monitoring**: Watch task_runs table and APScheduler logs

## Need Help?

Check these files for details:
- Implementation details → `FINAL_CHANGES.md`
- Backend integration → `server/backend/EVENTS_INTEGRATION.md`
- System architecture → `SCHEDULING_SYSTEM.md` (may need update)
