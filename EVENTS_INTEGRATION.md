# Event Emission Integration Guide

## Overview

This guide shows how to emit events when data is added, updated, or deleted in the WireLoft backend. These events trigger tasks defined in the task_manager package.

## Import

```python
# At the top of your service/endpoint file
from task_manager.events.emitters import emit_event
```

## Event Emission Pattern

All events should be emitted directly using `emit_event` with the event name string and data dictionary:

```python
await emit_event("event.name", {
    "resource_id": resource.id,
    "id": resource.id,
    # additional metadata as needed
})
```

## Common Patterns

### Shows

#### When Adding a Show

```python
from backend.db.models import Show
from task_manager.events.emitters import emit_event

async def create_show(session, show_data: dict):
    # Create the show
    show = Show(**show_data)
    session.add(show)
    session.flush()  # Get the ID

    # Emit event
    await emit_event("show.added", {
        "resource_id": show.id,
        "id": show.id,
        "slug": show.slug,
        "title": show.title
    })

    session.commit()
    return show
```

#### When Updating a Show

```python
async def update_show(session, show_slug: str, show_data: dict):
    show = session.query(Show).filter_by(slug=show_slug).one_or_none()
    # Update the show
    update_database_fields(show, show_data)
    session.flush()

    # Emit event
    await emit_event("show.updated", {
        "resource_id": show.id,
        "id": show.id,
        "slug": show.slug
    })

    session.commit()
    return show
```

#### When Deleting a Show

```python
async def delete_show(session, show_id: int):
    show = session.get(Show, show_id)
    if show:
        # Emit before deleting
        await emit_event("show.deleted", {
            "resource_id": show.id,
            "id": show.id,
            "slug": show.slug
        })

        session.delete(show)
        session.commit()
```

### Episodes

#### When Adding an Episode

```python
from backend.db.models import Episode
from task_manager.events.emitters import emit_event

async def create_episode(session, episode_data: dict):
    episode = Episode(**episode_data)
    session.add(episode)
    session.flush()

    await emit_event("episode.added", {
        "resource_id": episode.id,
        "id": episode.id,
        "slug": episode.slug,
        "show_id": episode.show_id,
        "status": episode.status
    })

    session.commit()
    return episode
```

#### When Episode Status Changes

```python
async def update_episode_status(session, episode_id: int, new_status: str):
    episode = session.get(Episode, episode_id)
    old_status = episode.status
    episode.status = new_status
    session.flush()

    # Emit specific events based on status change
    if new_status == "PUBLISHED":
        await emit_event("episode.published_final", {
            "resource_id": episode.id,
            "id": episode.id,
            "show_id": episode.show_id
        })
    elif new_status == "PUBLISHED_WITH_COUNTDOWN":
        await emit_event("episode.published_with_countdown", {
            "resource_id": episode.id,
            "id": episode.id,
            "show_id": episode.show_id
        })

    session.commit()
```

#### When Deleting an Episode

```python
async def delete_episode(session, episode_id: int):
    episode = session.get(Episode, episode_id)
    if episode:
        await emit_event("episode.deleted", {
            "resource_id": episode.id,
            "id": episode.id,
            "show_id": episode.show_id
        })
        session.delete(episode)
        session.commit()
```

### Download Profiles

#### When Adding a Download Profile

```python
from backend.db.models import DownloadProfile
from task_manager.events.emitters import emit_event

async def create_download_profile(session, profile_data: dict):
    profile = DownloadProfile(**profile_data)
    session.add(profile)
    session.flush()

    await emit_event("download_profile.added", {
        "resource_id": profile.id,
        "id": profile.id,
        "name": profile.name
    })

    session.commit()
    return profile
```

#### When Deleting a Download Profile

```python
async def delete_download_profile(session, profile_id: int):
    profile = session.get(DownloadProfile, profile_id)
    if profile:
        await emit_event("download_profile.deleted", {
            "resource_id": profile.id,
            "id": profile.id
        })
        session.delete(profile)
        session.commit()
```

### Seasons

```python
from task_manager.events.emitters import emit_event

async def create_season(session, season_data: dict):
    season = Season(**season_data)
    session.add(season)
    session.flush()

    await emit_event("season.added", {
        "resource_id": season.id,
        "id": season.id,
        "show_id": season.show_id
    })

    session.commit()
    return season

async def delete_season(session, season_id: int):
    season = session.get(Season, season_id)
    if season:
        await emit_event("season.deleted", {
            "resource_id": season.id,
            "id": season.id,
            "show_id": season.show_id
        })
        session.delete(season)
        session.commit()
```

## FastAPI Integration

For FastAPI endpoints, you need to handle async properly:

```python
from fastapi import APIRouter
from backend.db import get_session
from task_manager.events.emitters import emit_event

router = APIRouter()

@router.post("/shows")
async def create_show_endpoint(show_data: ShowCreate):
    session = get_session()
    try:
        show = Show(**show_data.dict())
        session.add(show)
        session.flush()

        # Emit event
        await emit_event("show.added", {
            "resource_id": show.id,
            "id": show.id,
            "slug": show.slug
        })

        session.commit()
        return {"id": show.id}
    finally:
        session.close()

@router.delete("/shows/{show_id}")
async def delete_show_endpoint(show_id: int):
    session = get_session()
    try:
        show = session.get(Show, show_id)
        if not show:
            raise HTTPException(404)

        # Emit before deleting
        await emit_event("show.deleted", {
            "resource_id": show.id,
            "id": show.id,
            "slug": show.slug
        })

        session.delete(show)
        session.commit()
        return {"ok": True}
    finally:
        session.close()
```

## Event Naming Convention

Follow this pattern: `{resource}.{action}`

Examples:
- `show.added`
- `show.updated`
- `show.deleted`
- `episode.added`
- `episode.published_final`
- `episode.published_with_countdown`
- `episode.deleted`
- `download_profile.added`
- `download_profile.deleted`
- `season.added`
- `season.deleted`
- `file.changed`
- `app.startup` (special system event)

## Available Events

### Show Events
- `show.added` - When a show is created
- `show.updated` - When a show is updated
- `show.deleted` - When a show is deleted

### Episode Events
- `episode.added` - When an episode is created
- `episode.deleted` - When an episode is deleted
- `episode.published_final` - When episode status becomes PUBLISHED
- `episode.published_with_countdown` - When episode status becomes PUBLISHED_WITH_COUNTDOWN

### Download Profile Events
- `download_profile.added` - When a download profile is created
- `download_profile.deleted` - When a download profile is deleted

### Season Events
- `season.added` - When a season is created
- `season.deleted` - When a season is deleted

### System Events
- `app.startup` - Emitted once when the application starts
- `file.changed` - When local files change

## Implementation Checklist

To fully integrate events into your backend:

- [x] Import emit_event in show service/endpoints
- [x] Emit `show.added` in create_show
- [x] Emit `show.updated` in update_show
- [x] Emit `show.deleted` in delete_show
- [x] Import emit_event in episode service/endpoints
- [x] Emit `episode.added` in create_episode
- [x] Emit `episode.published_final` when status changes to PUBLISHED
- [x] Emit `episode.published_with_countdown` when status changes to PUBLISHED_WITH_COUNTDOWN
- [x] Emit `episode.deleted` in delete_episode
- [x] Import emit_event in download_profile service/endpoints
- [x] Emit `download_profile.added` in create_download_profile
- [x] Emit `download_profile.deleted` in delete_download_profile
- [x] Import emit_event in season service/endpoints
- [x] Emit `season.added` in create_season
- [x] Emit `season.deleted` in delete_season

## Testing Events

To test if events are working:

```python
# In a test or debug script
import asyncio
from task_manager.events.emitters import emit_event

async def test_events():
    # This should trigger fetch_new_episodes worker
    await emit_event("show.added", {
        "resource_id": 123,
        "id": 123,
        "slug": "test-show"
    })

    # This should trigger download_profile_worker
    await emit_event("episode.published_final", {
        "resource_id": 456,
        "id": 456,
        "show_id": 123
    })

# Run it
asyncio.run(test_events())
```

Check the `task_runs` table to see if tasks were triggered.

## Error Handling

Event emission failures should not break the main operation:

```python
try:
    show = Show(**data)
    session.add(show)
    session.flush()

    try:
        await emit_event("show.added", {
            "resource_id": show.id,
            "id": show.id
        })
    except Exception as e:
        # Log but don't fail the operation
        logger.warning(f"Failed to emit show.added event: {e}")

    session.commit()
except Exception as e:
    session.rollback()
    raise
```

## Notes

- Events are emitted asynchronously using pyventus
- Event handlers run in separate tasks and don't block the main operation
- Multiple tasks can listen to the same event
- Event data is passed to the task's resource_id parameter
- Tasks can filter events by resource_type if needed
- All event emissions use the `emit_event` function directly with event name strings
