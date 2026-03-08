# Final System Changes - WireLoft Flexible Scheduling

## Summary of Changes

All requested changes have been implemented:

1. ✅ Removed `on_startup` decorator in favor of `app.startup` event
2. ✅ All events use pyventus package from motherboard
3. ✅ Event emission system created for data changes (add/delete)
4. ✅ All tasks (workers) moved to motherboard package
5. ✅ `on_cron` requires actual cron value, not string reference

## Architecture Changes

### 1. Package Structure

**Before:**
```
server/controller/tasks/workers/
server/motherboard/scheduler/
```

**After:**
```
server/motherboard/tasks/workers/     # All workers now here
server/motherboard/scheduler/         # Scheduling system
server/motherboard/events/            # Event system
server/motherboard/db_utils.py        # Database utilities
```

### 2. Worker Decorators

**Old System (Removed):**
```python
@task(...)
@on_cron(cron="settings:path.to.setting", run_on_startup=True)
@on_startup(resource_type="show")
async def my_worker(...):
    pass
```

**New System:**
```python
@task(...)
@on_cron(cron=get_settings().path.to.setting)  # Actual value!
@on_event(event_name="app.startup")             # Event instead of decorator
async def my_worker(...):
    pass
```

### 3. Event System

**Components:**
- **Emitter**: `wireloft_task_manager.events.WireloftEventEmitter` (pyventus-based)
- **Registry**: `wireloft_task_manager.events.registry.get_wireloft_event_emitter()`
- **Emitters**: `wireloft_task_manager.events.emitters` (convenience functions)

**Event Flow:**
1. Data change in backend → Emit event
2. Event emitter notifies all listeners
3. Task handlers trigger via scheduler
4. Tasks execute asynchronously

## Detailed Changes

### Registry Changes

**File**: `server/motherboard/src/wireloft_task_manager/scheduler/registry.py`

**Removed:**
- `on_startup` decorator
- `run_on_startup` parameter from `on_cron`
- Settings resolution logic

**Updated:**
- `TriggerMeta`: Removed `run_on_startup` field
- `on_cron`: Now requires actual cron expression string
  ```python
  # OLD: on_cron(cron="settings:new_episode_schedule.find_episodes_cron")
  # NEW: on_cron(cron=get_settings().new_episode_schedule.find_episodes_cron)
  ```

### Worker Updates

All workers moved to: `server/motherboard/src/wireloft_task_manager/tasks/workers/`

#### fetch_new_episodes

```python
from wireloft_config import get_settings
from wireloft_task_manager.db_utils import db_session
from wireloft_task_manager.scheduler.registry import task, on_cron, on_event

@task(key="fetch_new_episodes", ...)
@on_cron(
    cron=get_settings().new_episode_schedule.find_episodes_cron,  # Actual value
    resource_type="show",
    resource_id=0,
    coalesce=True,
)
@on_event(event_name="app.startup", resource_type="show")  # Event trigger
@on_event(event_name="show.added", resource_type="show")
async def fetch_new_episodes(...):
    with db_session() as s:
        await run_fetch_new_episodes(s, ...)
```

**Triggers:**
- Cron: Every N minutes (from settings)
- Event: `app.startup`
- Event: `show.added`

#### download_profile_worker

```python
@task(key="download_profile_worker", ...)
@on_cron(
    cron=f"*/{get_settings().download_settings.verify_downloads_interval_min} * * * *",
    resource_type="download_profile",
    resource_id=0,
    coalesce=True,
)
@on_event(event_name="app.startup", resource_type="download_profile")
@on_event(event_name="episode.published_countdown", resource_type="episode")
@on_event(event_name="episode.published", resource_type="episode")
@on_event(event_name="show.added", resource_type="show")
async def download_profile_worker(...):
    with db_session() as s:
        await run_download_profile_worker(s, ...)
```

**Triggers:**
- Cron: Every N minutes (from settings, converted to cron)
- Event: `app.startup`
- Event: `episode.published_countdown`
- Event: `episode.published`
- Event: `show.added`

#### file_watcher

```python
@task(key="file_watcher", ...)
@on_cron(cron="*/10 * * * *", resource_type="show", resource_id=0, coalesce=True)
@on_event(event_name="file.changed", resource_type="show")
async def file_watcher(...):
    with db_session() as s:
        await run_file_watcher(s)
```

**Triggers:**
- Cron: Every 10 minutes
- Event: `file.changed`

### Event Emission System

**File**: `server/motherboard/src/wireloft_task_manager/events/emitters.py`

**Convenience Functions:**
```python
# Import
from wireloft_task_manager.events import emitters

# Usage
await emitters.emit_show_added(show_id, slug="...", title="...")
await emitters.emit_show_deleted(show_id)
await emitters.emit_episode_added(episode_id, show_id=...)
await emitters.emit_episode_published(episode_id, show_id=...)
await emitters.emit_episode_published_countdown(episode_id, show_id=...)
await emitters.emit_episode_deleted(episode_id)
await emitters.emit_download_profile_added(profile_id)
await emitters.emit_download_profile_deleted(profile_id)
await emitters.emit_season_added(season_id, show_id=...)
await emitters.emit_season_deleted(season_id)
await emitters.emit_app_startup()  # System event

# Generic
await emitters.emit_event("custom.event", {"resource_id": 123, "data": ...})
```

### Controller App Integration

**File**: `server/controller/src/wireloft_controller/app.py`

**Removed:**
- `_resolve_cron_from_settings()` - No longer needed
- `_planned_startup_schedules()` - No longer needed
- `setup_startup_schedules()` - No longer needed

**Updated:**
- `setup_triggers_from_registry()`: Simplified (no settings resolution)
- `app()`: Emits `app.startup` event after initialization

**Startup Flow:**
1. Import `wireloft_task_manager.tasks` (registers all workers)
2. Sync task definitions to database
3. Start APScheduler
4. Setup cron triggers from registry
5. Setup event listeners from registry
6. **Emit `app.startup` event** (triggers startup tasks)

### Database Utilities

**File**: `server/motherboard/src/wireloft_task_manager/db_utils.py`

Simple context manager for database sessions:
```python
from wireloft_task_manager.db_utils import db_session

with db_session() as s:
    # Use session
    pass
```

## Integration Guide

### Backend API Integration

To trigger tasks when data changes, emit events in your API endpoints:

```python
# In backend/api/endpoints/shows/service.py
from wireloft_task_manager.events import emitters

async def create_show(session, data):
    show = Show(**data)
    session.add(show)
    session.flush()

    # Emit event to trigger fetch_new_episodes
    await emitters.emit_show_added(show.id, slug=show.slug)

    session.commit()
    return show

async def delete_show(session, show_id):
    show = session.get(Show, show_id)
    await emitters.emit_show_deleted(show_id)
    session.delete(show)
    session.commit()
```

### Episode Status Changes

```python
# In backend/api/endpoints/episodes/service.py
async def update_episode_status(session, episode_id, new_status):
    episode = session.get(Episode, episode_id)
    episode.status = new_status

    if new_status == "PUBLISHED":
        await emitters.emit_episode_published(episode_id, show_id=episode.show_id)
    elif new_status == "PUBLISHED_WITH_COUNTDOWN":
        await emitters.emit_episode_published_countdown(episode_id, show_id=episode.show_id)

    session.commit()
```

See `server/backend/EVENTS_INTEGRATION.md` for complete integration guide.

## Event Reference

### System Events
- `app.startup` - Emitted once when application starts

### Show Events
- `show.added` - When a show is created
- `show.deleted` - When a show is deleted

### Episode Events
- `episode.added` - When an episode is created
- `episode.deleted` - When an episode is deleted
- `episode.published` - When episode status becomes PUBLISHED
- `episode.published_countdown` - When episode status becomes PUBLISHED_WITH_COUNTDOWN

### Download Profile Events
- `download_profile.added` - When a download profile is created
- `download_profile.deleted` - When a download profile is deleted

### Season Events
- `season.added` - When a season is created
- `season.deleted` - When a season is deleted

### Custom Events
- `file.changed` - When local files change

## Testing

### 1. Syntax Check

```bash
python3 -m py_compile server/motherboard/src/wireloft_task_manager/scheduler/registry.py
python3 -m py_compile server/motherboard/src/wireloft_task_manager/tasks/__init__.py
python3 -m py_compile server/motherboard/src/wireloft_task_manager/events/emitters.py
python3 -m py_compile server/controller/src/wireloft_controller/app.py
```

### 2. Full System Test

```bash
uv sync
uv run python -m backend.main
```

**Expected on Startup:**
1. ✅ All task definitions registered
2. ✅ Cron jobs created for each @on_cron decorator
3. ✅ Event listeners registered for each @on_event decorator
4. ✅ `app.startup` event emitted
5. ✅ Startup tasks triggered (fetch_new_episodes, download_profile_worker)

### 3. Event Test

```python
# Test script
import asyncio
from wireloft_task_manager.events import emitters

async def test():
    # This should trigger fetch_new_episodes for show 123
    await emitters.emit_show_added(123, slug="test-show")

    # This should trigger download_profile_worker
    await emitters.emit_episode_published(456, show_id=123)

asyncio.run(test())
```

Check `task_runs` table for new entries.

## Migration Steps

### For Existing Deployments

1. **Update imports** in any custom code:
   ```python
   # OLD
   from wireloft_controller.tasks.workers.X import X

   # NEW
   from wireloft_task_manager.tasks.workers.X import X
   ```

2. **Add event emissions** to backend API (see EVENTS_INTEGRATION.md)

3. **Restart application** - Tasks will automatically register

### For New Workers

```python
# In server/motherboard/src/wireloft_task_manager/tasks/workers/my_worker/entrypoint.py

from wireloft_config import get_settings
from wireloft_task_manager.db_utils import db_session
from wireloft_task_manager.scheduler.registry import task, on_cron, on_event
from .service import run_my_worker

@task(
    key="my_worker",
    title="My Worker",
    description="Does something useful",
)
@on_cron(
    cron=get_settings().my_settings.cron_expression,  # Actual value!
    resource_type="show",
    resource_id=0,
)
@on_event(event_name="my.custom.event")
async def my_worker(*, resource_id=None, progress=None):
    with db_session() as s:
        await run_my_worker(s, resource_id=resource_id, progress=progress)
```

Then add to `server/motherboard/src/wireloft_task_manager/tasks/__init__.py`:
```python
from .workers.my_worker import my_worker

__all__ = [..., "my_worker"]
```

That's it! No other files need modification.

## Benefits

1. **Centralized Workers**: All tasks in one package (motherboard)
2. **True Event-Driven**: Uses pyventus for reliable event handling
3. **Explicit Cron Values**: No magic string resolution
4. **Startup Event**: Consistent with other events, more flexible
5. **Easy Integration**: Simple emit functions for backend
6. **Type-Safe**: Actual Python values instead of string references
7. **Discoverable**: All worker triggers in one file

## Breaking Changes

### From Previous Implementation

1. **`on_startup` decorator removed**
   - Replace with `@on_event(event_name="app.startup")`

2. **`on_cron` parameter change**
   - OLD: `on_cron(cron="settings:path.to.setting")`
   - NEW: `on_cron(cron=get_settings().path.to.setting)`

3. **Worker location changed**
   - OLD: `wireloft_controller.tasks.workers.*`
   - NEW: `wireloft_task_manager.tasks.workers.*`

4. **db_session import changed**
   - OLD: `from wireloft_controller.app import db_session`
   - NEW: `from wireloft_task_manager.db_utils import db_session`

## Next Steps

1. **Integrate Events in Backend**:
   - Add emit calls in show endpoints
   - Add emit calls in episode endpoints
   - Add emit calls in download_profile endpoints
   - See `server/backend/EVENTS_INTEGRATION.md`

2. **Test Thoroughly**:
   - Start application
   - Create a show → Verify fetch_new_episodes runs
   - Publish an episode → Verify download_profile_worker runs
   - Check task_runs table

3. **Monitor**:
   - Watch APScheduler logs
   - Check task execution times
   - Monitor for errors

4. **Cleanup** (if needed):
   - Remove old controller/tasks/workers directory
   - Update any custom scripts that import workers

## Files Modified

### New Files
- `server/motherboard/src/wireloft_task_manager/tasks/__init__.py`
- `server/motherboard/src/wireloft_task_manager/tasks/workers/*` (moved)
- `server/motherboard/src/wireloft_task_manager/db_utils.py`
- `server/motherboard/src/wireloft_task_manager/events/emitters.py`
- `server/backend/EVENTS_INTEGRATION.md`

### Modified Files
- `server/motherboard/src/wireloft_task_manager/scheduler/registry.py`
- `server/motherboard/src/wireloft_task_manager/__init__.py`
- `server/controller/src/wireloft_controller/app.py`
- All worker entrypoint files (updated decorators)

### Files to Remove (Optional)
- `server/controller/src/wireloft_controller/tasks/` (entire directory)
- `server/controller/src/wireloft_controller/app.py.bak` (backup file)

## Documentation

- **FINAL_CHANGES.md** (this file): Summary of all changes
- **SCHEDULING_SYSTEM.md**: Original system documentation (needs update)
- **CHANGES_SUMMARY.md**: Previous migration guide (superseded)
- **server/backend/EVENTS_INTEGRATION.md**: How to emit events in backend
